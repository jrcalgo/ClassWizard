"""Bounded, conservative, source-linked evidence selection without Spark."""
from ai.recommendations.skill_evidence import select_match_items, merge_match_items, SCHEMA_SQL
from ai.nlp.explanations.rag import check_citations, build_messages


def row(code='A',soc='career',identifier='skill:1',confidence=.9,similarity=.8,filename='source.pdf',quote='A source sentence.',term='Programming'):
    return (identifier,code,soc,'programming',term,'skill',confidence,similarity,.5,
            'triple-1',filename,3,'Objectives',quote)


def select(rows,courses=('A','B'),careers=('career','other')):
    return select_match_items(rows,courses,careers,{'career':'Developer','other':'Scientist'},lambda s:s[:100])


def test_quality_filters_and_deduplication():
    rows=[row(confidence=.79),row(similarity=.69),row(filename=''),row(quote=''),row(identifier='skill:good'),row(identifier='skill:duplicate')]
    items=select(rows)
    assert [i['id'] for i in items]==['skill:good']
    assert items[0]['provenance']['page_num']==3
    assert 'computed semantic match' in items[0]['text']
    assert 'source.pdf' in items[0]['text'] and 'Developer' in items[0]['label']


def test_round_robin_limits_and_distinct_careers():
    items=select([row(identifier='skill:a1'),row(identifier='skill:a2',term='SQL'),
                  row(code='B',identifier='skill:b1'),row(soc='other',identifier='skill:a-other')])
    assert [i['id'] for i in items]==['skill:a1','skill:a-other','skill:b1']
    assert len(items)==3


def test_protected_named_facts_and_budget():
    items=[{'id':str(n),'kind':'course','text':'facts'} for n in range(12)]
    matches=select([row()])
    merged=merge_match_items(items,matches,['9'],10)
    assert merged[0]['id']=='9' and merged[1]['kind']=='skill_match'
    assert len(merged)==10
    assert merge_match_items(items,matches,[str(n) for n in range(12)],10)==items[:10]


def test_match_citations_and_prompt_distinguish_inference():
    evidence=select([row()])
    assert check_citations('A connection [skill:1].',evidence)['grounded']
    assert not check_citations('A connection [skill:missing].',evidence)['grounded']
    system=build_messages('Why?',evidence,{})[0]['content']
    assert 'computed matches' in system and 'not a complete explanation' in system


def test_schema_definition_matches_initialization():
    from pathlib import Path
    assert SCHEMA_SQL.strip() in Path('backend/schema.sql').read_text()


def test_retrieval_queries_selected_catalog_and_careers_only():
    from ai.recommendations.skill_evidence import retrieve_match_items
    class Connection:
        def execute(self,sql,params=None):
            self.sql=sql
            self.params=params
            return self
        def fetchone(self): return ('course_career_match_publication',)
        def fetchall(self):
            assert self.params[2:5]==('UG',['A'],['career'])
            assert 'r.loaded_at=p.score_published_at' in self.sql
            assert 'p.evidence_version=%s' in self.sql
            return [row()]
    items=retrieve_match_items(Connection(),'UG',['A'],['career'],{},lambda s:s)
    assert items[0]['id']=='skill:1'


def test_exact_technology_match_is_identified():
    values=list(row(similarity=1))
    values[5]='technology'
    assert 'exact technology-name match' in select([values])[0]['text']


def test_retrieval_before_schema_initialization_returns_no_matches():
    from ai.recommendations.skill_evidence import retrieve_match_items
    class Missing:
        def execute(self,*args): return self
        def fetchone(self): return (None,)
    assert retrieve_match_items(Missing(),'UG',['A'],['career'],{},str)==[]


def test_skill_matches_cannot_reintroduce_staff_or_contact_details():
    assert select([row(quote='Instructor: Dr. Example. Reach x@example.edu.')])==[]
    values=list(row())
    values[3]='Office hours'
    assert select([values])==[]
    assert select([row(quote='Design and implement relational databases using SQL.')])
