"""Independent verification of emitted schedules; intentionally separate from solver."""
VALUES={'A':4,'B':3,'C':2,'D':1,'F':0}

def satisfies(rule,grades,bundle,credits,exceptions,course,program):
    kind=rule.get('kind')
    if kind=='true':return True
    if kind=='and':return all(satisfies(r,grades,bundle,credits,exceptions,course,program) for r in rule['items'])
    if kind=='or':return any(satisfies(r,grades,bundle,credits,exceptions,course,program) for r in rule['items'])
    if kind=='course':
        grade=grades.get(rule['code'])
        minimum=rule.get('grade')
        completed=grade is not None and grade!='F' and (not minimum or grade in VALUES and VALUES[grade]>=VALUES[minimum])
        return completed or bool(rule.get('concurrent') and rule['code'] in bundle)
    if kind=='standing':return credits>={'Junior':60,'Senior':90}.get(rule['level'],999)
    if kind=='credits':return credits>=rule['minimum']
    if kind=='program':return program=='cs-bs-web-software'
    if kind=='unknown':return course in exceptions
    return False

def verify(snapshot,state,prefs,result):
    if result['status']!='valid':return []
    errors=[];courses=snapshot['courses'];grades=dict(state['completed'])
    grades.update({c:'C' for c in state['in_progress']})
    earned=state['applied_credits']+sum(prefs.get('variable_credits',{}).get(c,courses.get(c,{}).get('credits',0)) for c in state['in_progress'])
    scheduled={};seen={c for c,g in grades.items() if g!='F'}
    for semester in result['semesters']:
        index=semester['index'];items=semester['courses'];bundle={c['code'] for c in items}
        if len(bundle)!=len(items) or seen&bundle:errors.append('Duplicate or already-completed course in emitted schedule.')
        if not prefs['min_courses']<=len(items)<=prefs['max_courses']:errors.append('Semester course-count limit violated.')
        total=0
        for item in items:
            code=item['code'];course=courses.get(code)
            if course is None:errors.append('Unknown scheduled course.');continue
            amount=item['selected_credits'];low,high=course['credit_range']
            if not low<=amount<=high:errors.append('Scheduled credits outside catalog range.')
            if not satisfies(course['rule'],grades,bundle,earned,state.get('approved_exceptions',[]),code,snapshot['program']['id']):errors.append('Unsatisfied prerequisite, grade, standing or corequisite: '+code)
            if code in prefs['pinned'] and prefs['pinned'][code]!=index:errors.append('Pinned course placed in wrong semester.')
            scheduled[code]=index;total+=amount
        if total!=semester['credits'] or not prefs['min_credits']<=total<=prefs['max_credits']:errors.append('Semester credit limit or total violated.')
        actual_start=prefs['start_year']*2+(prefs['start_term']=='Fall');actual=actual_start+index
        expected=f"{'Fall' if actual%2 else 'Spring'} {actual//2}"
        if semester['term']!=expected:errors.append('Incorrect term sequence.')
        if prefs.get('target_year') and actual>prefs['target_year']*2+(prefs['target_term']=='Fall'):errors.append('Target graduation term exceeded.')
        grades.update({c:'C' for c in bundle});seen|=bundle;earned+=total
    if set(prefs['pinned'])-set(scheduled):errors.append('A pinned course is missing.')
    if earned<snapshot['program']['total_credits'] or abs(earned-result['projected_credits'])>.0001:errors.append('Degree credit total is inconsistent.')
    allocated=set()
    for group in snapshot['program']['groups']:
        entries=result['allocations'].get(group['id'],[])
        if entries==['student-confirmed']:
            if not group['external'] or group['id'] not in state['satisfied_groups']:errors.append('Invalid completion attestation.')
            continue
        if len(entries)!=len(set(entries)) or allocated&set(entries):errors.append('Requirement allocation double-counts a course.')
        allocated.update(entries)
        if set(entries)-set(group['options']) or len(entries)<group['count']:errors.append('Invalid requirement course choices.')
        amount=sum(prefs.get('variable_credits',{}).get(c,courses.get(c,{}).get('credits',0)) for c in entries)
        if amount<group['credits']:errors.append('Requirement credit shortfall.')
        for code in entries:
            if code not in seen:errors.append('Required course not completed or scheduled.')
            if group.get('grade') and (grades.get(code) not in VALUES or VALUES[grades[code]]<VALUES[group['grade']]):errors.append('Minimum degree grade not established.')
        if group.get('science_pairing'):
            lectures=[c for c in entries if not c.endswith('L')];labs=[c for c in entries if c.endswith('L')]
            if len(lectures)!=2 or not (set(lectures)&set(group['integrated_labs']) or any(l[:-1] in lectures for l in labs)):errors.append('Natural-science lab requirement not met.')
    if state.get('gpa') is None or state['gpa']<2:errors.append('Minimum GPA not confirmed.')
    return sorted(set(errors))
