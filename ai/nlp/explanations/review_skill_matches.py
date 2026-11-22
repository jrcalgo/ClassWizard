"""Prepare six paired explanation samples; never start or download a model.

Run in the backend: python3 -m ai.nlp.explanations.review_skill_matches --output /data/lake/skill_match_review.json
An unavailable configured Ollama model produces an explicit pending report.
Generated answers need human review against the included rubric; valid citation
IDs alone are not a factual-support judgment.
"""
import argparse
from datetime import datetime, timezone
import json
import os
import urllib.request

import psycopg

from ai.nlp.explanations.rag import build_messages, check_citations, generate, model_name, student_context
from ai.nlp.explanations.retrieval import retrieve_evidence
from ai.recommendations.ranking import recommend

RUBRIC = ['Every skill claim is supported by the cited excerpt and computed relationship.',
          'Quoted source content is distinguished from inferred concepts and semantic matches.',
          'Eligible examples explain a concrete course-career connection.',
          'Missing/weak evidence produces a supported, qualified answer, not invented connections.',
          'No weights, contribution arithmetic, student-skill claims, or job guarantees.',
          'Comparisons and multiple-career answers attribute evidence to the correct course and career.']


def local_model_available():
    model=model_name()
    if not model.startswith(('ollama/', 'ollama_chat/')):
        return False, 'Review is restricted to the existing local Ollama setup.'
    url=os.environ.get('OLLAMA_URL','http://host.docker.internal:11434').rstrip('/')+'/api/tags'
    try:
        with urllib.request.urlopen(url,timeout=3) as response:
            models=json.load(response).get('models',[])
        target=model.split('/',1)[1]
        if any(m.get('name')==target or m.get('model')==target for m in models):
            return True, None
        return False, f'Configured model {target} is not already installed.'
    except Exception as exc:
        return False, f'Existing Ollama service unavailable ({type(exc).__name__}); no setup attempted.'


def choose_cases(conn):
    """Choose real eligible and ineligible examples rather than assuming coverage."""
    careers=['15-1252.00','15-2051.00']
    eligible="""catalog_name='Undergraduate 2026-2027' AND soc_code=ANY(%s)
        AND confidence>=.8 AND similarity>=.7 AND btrim(coalesce(filename,''))<>''
        AND btrim(coalesce(source_text,''))<>'' AND btrim(coalesce(triple_id,''))<>''"""
    def pick(extra):
        return conn.execute('SELECT course_code,soc_code FROM course_career_match_evidence WHERE '+eligible+
            ' AND '+extra+' ORDER BY contribution DESC,id LIMIT 1',(careers,)).fetchone()
    semantic=pick("kind<>'technology' AND similarity<.99999")
    technology=pick("kind='technology' AND similarity=1")
    absent=conn.execute("""SELECT c.code FROM courses c WHERE c.catalog_name='Undergraduate 2026-2027'
        AND NOT EXISTS (SELECT 1 FROM course_career_match_evidence m
          WHERE m.catalog_name=c.catalog_name AND m.course_code=c.code AND m.soc_code=ANY(%s))
        ORDER BY c.code LIMIT 1""",(careers,)).fetchone()
    weak=conn.execute("""SELECT m.course_code,m.soc_code FROM course_career_match_evidence m
        WHERE m.catalog_name='Undergraduate 2026-2027' AND m.soc_code=ANY(%s)
        AND NOT EXISTS (SELECT 1 FROM course_career_match_evidence strong
          WHERE strong.catalog_name=m.catalog_name AND strong.course_code=m.course_code
          AND strong.soc_code=m.soc_code AND strong.confidence>=.8 AND strong.similarity>=.7
          AND btrim(coalesce(strong.filename,''))<>'' AND btrim(coalesce(strong.source_text,''))<>'')
        ORDER BY m.contribution DESC,m.id LIMIT 1""",(careers,)).fetchone()
    warnings=[]
    if not semantic: warnings.append('No eligible non-exact semantic example for the selected review careers.')
    if not technology: warnings.append('No eligible exact-technology example for the selected review careers.')
    if not absent: warnings.append('No entirely absent example found.')
    if not weak: warnings.append('No weak-only example found.')
    a,sa=semantic or ('ITSC 1212',careers[0])
    b,sb=technology or ('ITCS 3156',careers[1])
    empty=absent[0] if absent else 'MATH 1100'
    weak_code,weak_soc=weak or ('COMM 2100',careers[0])
    return [
        ('semantic',f'Why does {a} fit my selected career?', [a],[sa]),
        ('technology',f'What technology connection does {b} have to my selected career?', [b],[sb]),
        ('comparison',f'Compare {a} and {b} for my selected careers.',list(dict.fromkeys([a,b])),list(dict.fromkeys([sa,sb]))),
        ('multiple_careers',f'How does {a} support software development and data science?',[a],careers),
        ('absent',f'Why does {empty} have its career-fit rating?',[empty],[careers[0]]),
        ('weak',f'What concrete skills explain the rating for {weak_code}?',[weak_code],[weak_soc])], warnings


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args=parser.parse_args()
    available,reason=local_model_available()
    report={'created_at':datetime.now(timezone.utc).isoformat(), 'model':model_name(),
            'temperature':.1, 'source_limit':'Quotes are from stored evidence records; original PDF text was not independently re-extracted or verified.', 'status':'needs_human_review' if available else 'pending_model_review',
            'reason':reason,'rubric':RUBRIC,'samples':[]}
    with psycopg.connect(os.environ['DATABASE_URL']) as conn:
        cases,warnings=choose_cases(conn)
    report['case_coverage_warnings']=warnings
    report['baseline_policy']='Same model, prompt rules, audit, and ranking; prior retrieval budget with skill evidence disabled.'
    for name,question,codes,careers in cases:
        audit={'level':'Undergraduate','major':'Computer Science',
               'courses_not_taken':[{'block':'Synthetic review','course_codes':codes}]}
        with psycopg.connect(os.environ['DATABASE_URL']) as conn:
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            recommendation=recommend(conn,audit,careers,10)
            after=retrieve_evidence(conn,question,audit,recommendation,careers)
            # Re-run the existing retrieval with match injection disabled, rather
            # than subtracting items and accidentally shrinking the old budget.
            import ai.nlp.explanations.retrieval as retrieval
            original=retrieval.retrieve_match_items
            retrieval.retrieve_match_items=lambda *a,**kw: []
            try:
                before=retrieve_evidence(conn,question,audit,recommendation,careers)
            finally:
                retrieval.retrieve_match_items=original
        # Remove the new no-match qualification from the baseline prompt inputs.
        suffix=(' Strong, traceable evidence of individual scoring skill matches '
                'is unavailable here; use the course and career facts without '
                'claiming they explain the assigned rating.')
        before=[{**item,'text':item['text'].removesuffix(suffix)} for item in before]
        sample={'case':name,'question':question,'synthetic_audit':audit,
                'recommendation':recommendation,'before_evidence':before,'after_evidence':after,
                'match_count':sum(i['kind']=='skill_match' for i in after),
                'target_match_count':sum(i['kind']=='skill_match' and i.get('course_code') in codes for i in after),
                'review_findings':None}
        if available:
            for variant,evidence in [('before',before),('after',after)]:
                try:
                    answer=generate(build_messages(question,evidence,student_context(audit)))
                    sample[variant]={'answer':answer,**check_citations(answer,evidence)}
                except Exception as exc:
                    sample[variant]={'error':type(exc).__name__}
                    report['status']='incomplete_model_review'
        report['samples'].append(sample)
    from pathlib import Path
    output=Path(args.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2))
    print(json.dumps({'status':report['status'],'samples':len(report['samples']),'output':str(output),'reason':reason}))


if __name__=='__main__':
    main()
