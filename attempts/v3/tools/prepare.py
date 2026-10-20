"""Reproducible preparation from downloaded public files; no student input."""
import csv
import hashlib
import json
from pathlib import Path
import re
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw'
OUT = ROOT / 'data/prepared'
URL = 'https://catalog.charlotte.edu/mime/media/view/10/5658/2026-2027-Undergraduate-Catalog.pdf'
TARGETS = {'15-1252.00', '15-1253.00', '15-1212.00', '15-2051.00'}

def course(code, grade=None, concurrent=False):
    return {'kind': 'course', 'code': code, 'grade': grade, 'concurrent': concurrent}
def all_of(*rules):
    return {'kind': 'and', 'items': list(rules)}
def any_of(*rules):
    return {'kind': 'or', 'items': list(rules)}
def options(*codes, grade=None, concurrent=False):
    return any_of(*(course(c, grade, concurrent) for c in codes))
TRUE = {'kind': 'true'}
PROGRAM = {'kind': 'program'}

# Reviewed encodings of catalog rules. Permission alternatives are not assumed.
RULES = {
 'ITSC 1212': TRUE,
 'ITSC 1213': all_of(options('ITSC 1212', 'DTSC 1302', 'ENGR 1302', grade='C'), options('MATH 1100', 'MATH 1101', 'MATH 1103', 'MATH 1120', 'MATH 1241', concurrent=True)),
 'ITSC 1600': all_of(PROGRAM, {'kind': 'unknown', 'text': 'Freshman standing must be confirmed.'}),
 'ITSC 2600': PROGRAM,
 'ITSC 2175': all_of(options('ITSC 1212', 'DTSC 1302'), options('MATH 1120', 'MATH 1241')),
 'ITSC 2181': course('ITSC 1213', 'C'),
 'ITSC 2214': course('ITSC 1213', 'C'),
 'ITSC 3146': all_of(course('ITSC 2214', 'C'), course('ITSC 2181', 'C'), PROGRAM),
 'ITSC 3155': all_of(course('ITSC 2214', 'C'), PROGRAM),
 'ITSC 3160': course('ITSC 1213'),
 'ITSC 3688': all_of({'kind': 'standing', 'level': 'Junior'}, PROGRAM),
 'ITIS 3135': course('ITSC 2214', 'C'),
 'ITIS 3310': course('ITSC 2214'),
 'ITIS 4221': course('ITIS 3135'),
 'ITIS 3300': all_of(course('ITSC 3160'), course('ITIS 3135')),
 'ITIS 3320': all_of(course('ITIS 3200'), course('ITIS 3300')),
 'ITIS 4166': all_of(course('ITSC 2214', 'C'), course('ITSC 3160')),
 'ITIS 4180': course('ITSC 2214'),
 'ITIS 3200': course('ITSC 2214'),
 'ITIS 3130': {'kind': 'credits', 'minimum': 30},
 'ITIS 4350': {'kind': 'credits', 'minimum': 30},
 'MATH 1242': course('MATH 1241', 'C'),
 'MATH 2164': options('MATH 1120', 'MATH 1241', grade='C'),
 'STAT 2122': options('MATH 1242', 'MATH 2120'),
 # ITSC 4155 contains ITCS 2214/3155 in the printed catalog: preserve as unknown;
 # do not silently substitute prefixes.
 'ITSC 4155': {'kind': 'unknown', 'text': 'Printed ITCS prerequisite references require departmental confirmation.'},
 'CTCM 2530': all_of(options('WRDS 1103', 'WRDS 1104'), {'kind': 'credits', 'minimum': 30}),
 'BIOL 1110L': course('BIOL 1110', concurrent=True),
}

def group(gid, name, opts, count=1, credits=0, external=False, grade=None):
    return {'id': gid, 'name': name, 'options': opts, 'count': count, 'credits': credits,
            'external': external, 'grade': grade}

def run():
    OUT.mkdir(exist_ok=True)
    source = (RAW / 'catalog-raw.txt').read_text()
    # Header pattern is anchored to course description records, not program lists.
    header = re.compile(r'^([A-Z]{2,5})\s+(\d{4}[A-Z]?)\.\s+(.{1,180}?)\.?\s*\((\d+)(?:\s+to\s+(\d+))?\)', re.M | re.S)
    matches = list(header.finditer(source))
    courses, duplicates = {}, []
    for i, m in enumerate(matches):
        code = f'{m[1]} {m[2]}'
        # Avoid overmatching across unrelated paragraphs.
        title = re.sub(r'\s+', ' ', m[3]).strip().rstrip('.')
        if len(title) > 180 or '\f' in m[3]:
            continue
        end = matches[i+1].start() if i+1 < len(matches) else min(len(source), m.end()+2000)
        body = source[m.end():end]
        body = re.sub(r'[^\n]*2026-2027[^\n]*\n', '\n', body)
        body = re.sub(r'\s+', ' ', body).strip()[:5000]
        # Semicolons, glued words and Course(s) variants occur in the printed catalog.
        condition = re.search(r'(?:pre.?requisite|corequisite|permission|standing)',body[:600],re.I)
        rule = RULES.get(code, {'kind': 'unknown', 'text': body[:600]} if condition else TRUE)
        page = source[:m.start()].count('\f') + 1
        entry = {'code': code, 'title': title, 'credits': float(m[4]), 'credit_range': [float(m[4]), float(m[5] or m[4])],
                 'description': body, 'rule': rule, 'quarantined': False,
                 'review_reason': 'Prerequisite text needs review.' if rule.get('kind') == 'unknown' else None,
                 'evidence': {'url': URL, 'pdf_page': page, 'catalog_year': '2026-2027', 'section': code}}
        if code in courses:
            duplicates.append(code)
        else:
            courses[code] = entry
    # Catalog lists these options but has no corresponding description record.
    # Preserve their sourced titles/credits as quarantined placeholders, not invented rules.
    for code, title in [('MATH 1165', 'Introduction to Discrete Structures'), ('CHEM 1112', "Chemistry in Today's Society")]:
        if code not in courses:
            courses[code] = {'code': code, 'title': title, 'credits': 3.0, 'credit_range': [3.0,3.0],
                'description': 'Listed in program/general education requirements; course description unresolved.',
                'rule': {'kind': 'unknown'}, 'quarantined': True,
                'review_reason': 'No matching course description in this catalog.',
                'evidence': {'url': URL, 'catalog_year': '2026-2027', 'section': code}}
    core = ['ITSC 1212', 'ITSC 1213', 'ITSC 2181', 'ITSC 2214', 'ITSC 3146', 'ITSC 3155', 'ITSC 3688']
    groups = [group(c.replace(' ', '_').lower(), c, [c], grade='C') for c in core]
    groups += [group('professional', 'Computing professional identity', ['ITSC 1600', 'ITSC 2600'], grade='C'),
               group('logic', 'Logic and algorithms', ['ITSC 2175', 'MATH 1165'], grade='C')]
    for c in ['MATH 1241', 'MATH 1242', 'MATH 2164', 'STAT 2122']:
        groups.append(group(c.replace(' ', '_').lower(), c, [c]))
    for c in ['ITIS 3135', 'ITIS 3310', 'ITIS 4221', 'ITSC 3160']:
        groups.append(group(c.replace(' ', '_').lower(), c, [c]))
    groups += [group('concentration_electives', 'Concentration electives (three)', ['ITCS 3112', 'ITIS 3130', 'ITIS 4350', 'ITIS 3300', 'ITIS 3320', 'ITIS 4166', 'ITIS 4180'], count=3, credits=9),
               group('technical_electives', 'CCI technical electives (two)', [c for c in courses if c.startswith(('ITSC 3', 'ITSC 4', 'ITIS 3', 'ITIS 4', 'ITCS 3', 'ITCS 4', 'BINF 3', 'BINF 4', 'DTSC 3', 'DTSC 4'))], count=2, credits=6),
               group('capstone', 'Capstone', ['ITCS 4232', 'ITIS 4390', 'ITIS 4246', 'ITSC 4155', 'ITSC 4681', 'ITSC 4682', 'ITSC 4750', 'ITSC 4850', 'ITSC 4851', 'ITSC 4990', 'ITSC 4991'], credits=3, external=True),
               group('writing', 'First-year writing', ['WRDS 1103', 'WRDS 1104']),
               group('critical_thinking', 'Critical thinking and communication', ['CTCM 2530']),
               group('global_social', 'Global social science', [c for c in courses if c.endswith('1501') and 'Global Social Science' in courses[c]['title']]),
               group('global_arts', 'Global arts/humanities', [c for c in courses if c.endswith('1502') and 'Global Arts' in courses[c]['title']]),
               group('local_theme', 'Local theme', [c for c in courses if c.endswith(('1511','1512')) and 'Local ' in courses[c]['title']]),
               {**group('science', 'Natural sciences: two lectures and corresponding lab', ['BIOL 1110', 'BIOL 1110L', 'BIOL 1115', 'BINF 1101', 'CHEM 1111', 'CHEM 1111L', 'CHEM 1112', 'PHYS 1101', 'PHYS 1101L', 'PHYS 1102'], count=2, credits=7, external=True), 'science_pairing':True,'integrated_labs':['BINF 1101']},
               group('outside_electives', 'Other-discipline electives (15 credits, no double counting)', [c for c in courses if not c.startswith(('ITSC ', 'ITCS ', 'ITIS '))], count=0, credits=15, external=True),
               group('unrestricted', 'Unrestricted electives to reach 120 credits', list(courses), count=0, credits=0, external=True)]
    # Quantitative/data competency is covered by MATH 1241/1242, explicitly permitted by program text.
    program = {'id': 'cs-bs-web-software', 'title': 'Computer Science BS · Web/Mobile Development and Software Engineering',
               'catalog_year': '2026-2027', 'total_credits': 120, 'minimum_gpa': 2.0, 'groups': groups,
               'evidence': {'url': URL, 'printed_pages': [190, 191], 'pdf_pages': [source[:source.index('with Concentration in Web/Mobile Development')].count('\f')+1,source[:source.index('with Concentration in Web/Mobile Development')].count('\f')+2]},
               'review_notes': ['Mathematics courses also satisfy quantitative/data competency.',
                                'Capstone selection, science pairing, external electives and unrestricted credits need student/advisor review.',
                                'Course offerings are unavailable; prerequisite unknowns remain blocked.']}
    careers, skills, links = [], {}, {}
    for r in csv.DictReader((RAW/'occupation_data.csv').open()):
        if r['O*NET-SOC Code'] in TARGETS:
            careers.append({'soc': r['O*NET-SOC Code'], 'title': r['Title'], 'description': r['Description'],
                            'technologies': [], 'education': [], 'evidence': {'url': 'https://www.onetcenter.org/database.html', 'release': '31.0', 'soc': r['O*NET-SOC Code']}})
    by_soc = {o['soc']: o for o in careers}
    profile = {}
    for name in ['transferable_skills', 'essential_skills', 'knowledge']:
        path = RAW / f'{name}.csv'
        if not path.exists():
            continue
        rows = list(csv.DictReader(path.open()))
        profile[name] = {'records': len(rows), 'attributes': len(rows[0]), 'missing_cells': sum(not v for r in rows for v in r.values())}
        for r in rows:
            soc = r['O*NET-SOC Code']
            if soc not in TARGETS or r.get('Recommend Suppress') == 'Y':
                continue
            el = r['Element ID']
            skills[el] = {'element': el, 'name': r['Element Name'], 'category': name, 'description': r['Element Name'],
                          'evidence': {'url': f'https://www.onetcenter.org/dl_files/database/db_31_0_csv/{name}.csv', 'release': '31.0'}}
            link = links.setdefault((soc, el), {'soc': soc, 'element': el, 'scales': {}})
            value = float(r['Data Value'])
            link['scales'][r['Scale ID']] = {'value': value, 'scale': r['Scale Name'], 'date': r['Date']}
            if r['Scale ID'] == 'IM':
                link['importance'] = max(0, min(1, (value - 1) / 4))
    for r in csv.DictReader((RAW/'software_skills.csv').open()):
        if r['O*NET-SOC Code'] in TARGETS:
            by_soc[r['O*NET-SOC Code']]['technologies'].append({'name': r['Workplace Example'], 'category': r['Element Name'], 'hot': r['Hot Technology'], 'in_demand': r['In Demand']})
    education = RAW / 'education_training_experience.csv'
    if education.exists():
        for r in csv.DictReader(education.open()):
            if r.get('O*NET-SOC Code') in TARGETS:
                by_soc[r['O*NET-SOC Code']]['education'].append(r)
    # Transparent lexical aliases bootstrap mappings; semantic candidates supplement, not overwrite, evidence.
    aliases = {'Programming': ['programming', 'software development', 'python', 'java'],
               'Computers and Electronics': ['computer', 'database', 'network', 'software'],
               'Systems Analysis': ['requirements', 'system analysis', 'systems analysis'],
               'Systems Evaluation': ['evaluation', 'testing', 'quality assurance'],
               'Quality Control Analysis': ['testing', 'quality assurance', 'quality control'],
               'Technology Design': ['architecture', 'software design', 'design patterns'],
               'Complex Problem Solving': ['problem-solving', 'problem solving', 'algorithms'],
               'Mathematics': ['calculus', 'statistics', 'mathematics', 'linear algebra']}
    course_links = []
    for c in courses.values():
        text = (c['title'] + ' ' + c['description']).lower()
        for el, skill in skills.items():
            terms = aliases.get(skill['name'], [skill['name'].lower()])
            if any(re.search(r'\b'+re.escape(t)+r'\b', text) for t in terms):
                course_links.append({'code': c['code'], 'element': el, 'confidence': .75,
                                     'method': 'exact-or-reviewed-alias', 'evidence': c['evidence']})
    manifest = {'catalog_year': '2026-2027', 'onet_release': '31.0', 'retrieved': datetime.now(timezone.utc).isoformat(),
                'source_url': URL, 'sources': {p.name: {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size} for p in sorted(RAW.iterdir()) if p.is_file()},
                'attribution': 'O*NET 31.0 Database, U.S. Department of Labor, Employment and Training Administration; https://www.onetcenter.org/license_db.html'}
    payload = {'manifest': manifest, 'courses': list(courses.values()), 'program': program, 'careers': careers,
               'skills': list(skills.values()), 'occupation_skills': list(links.values()), 'course_skills': course_links}
    # Stable dataset identity ignores retrieval time but includes rules and transformed data.
    stable = {**payload, 'manifest': {k: v for k, v in manifest.items() if k != 'retrieved'}}
    payload['version'] = hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()[:20]
    (OUT/'dataset.json').write_text(json.dumps(payload, indent=2))
    missing = sorted({c for g in groups for c in g['options']} - set(courses))
    report = {'catalog': {'records': len(courses), 'attributes': len(next(iter(courses.values()))), 'duplicate_codes': duplicates,
                          'credits_distribution': {str(n): sum(c['credits']==n for c in courses.values()) for n in sorted({c['credits'] for c in courses.values()})},
                          'variable_credit_courses': sum(c['credit_range'][0]!=c['credit_range'][1] for c in courses.values()),
                          'unknown_prerequisite_rules': sum(c['rule']['kind']=='unknown' for c in courses.values()),
                          'missing_program_course_references': missing},
              'onet': profile, 'selected_occupations': len(careers), 'selected_skills': len(skills),
              'degreeworks': {'validation': 'synthetic only', 'real_records_inspected': 0},
              'version': payload['version']}
    (OUT/'profile.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    run()
