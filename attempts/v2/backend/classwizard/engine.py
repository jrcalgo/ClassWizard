"""Deterministic recommendation and bounded semester constraint solving."""
import itertools
import time
from .models import GRADES

def passed(state):
    return {c for c, g in state['completed'].items() if g != 'F'}

def evaluate(rule, grades, concurrent, credits, exceptions=(), code='', context=None):
    context = context or {}
    kind = rule.get('kind', 'unknown')
    if kind == 'true':
        return True
    if kind == 'and':
        return all(evaluate(r, grades, concurrent, credits, exceptions, code, context) for r in rule['items'])
    if kind == 'or':
        return any(evaluate(r, grades, concurrent, credits, exceptions, code, context) for r in rule['items'])
    if kind == 'course':
        grade = grades.get(rule['code'])
        ok = grade is not None and grade != 'F' and (not rule.get('grade') or
            (GRADES.get(grade) is not None and GRADES[grade] >= GRADES[rule['grade']]))
        return ok or (rule.get('concurrent', False) and rule['code'] in concurrent)
    if kind == 'credits':
        return credits >= rule['minimum']
    if kind == 'standing':
        return credits >= {'Junior': 60, 'Senior': 90}.get(rule['level'], 999)
    if kind == 'program':
        return context.get('program') == 'cs-bs-web-software'
    if kind == 'unknown':
        return code in exceptions
    return False

def dependencies(rule, grades, courses):
    kind = rule.get('kind')
    if kind == 'course':
        if evaluate(rule, grades, set(), 0):
            return set()
        return {rule['code']}
    if kind == 'and':
        result = set()
        for r in rule['items']:
            result |= dependencies(r, grades, courses)
        return result
    if kind == 'or':
        options = [dependencies(r, grades, courses) for r in rule['items']]
        # Prefer already satisfied options, then available prerequisites.
        return min(options, key=lambda x: (len(x - set(courses)), len(x), sorted(x))) if options else set()
    return set()

def credits_for(course, prefs):
    value = prefs.get('variable_credits', {}).get(course['code'], course['credits'])
    low, high = course.get('credit_range', [course['credits'], course['credits']])
    if value < low or value > high:
        raise ValueError(f"Choose {low}–{high} credits for {course['code']}.")
    if low != high and course['code'] not in prefs.get('variable_credits', {}):
        raise ValueError(f"Select credit hours for variable-credit course {course['code']}.")
    return value

def career_for(snapshot, prefs):
    for career in snapshot['careers']:
        if career['soc'] == prefs['career']:
            return career
    raise ValueError('Select an available career.')

def relevance(course, career, covered):
    weights = {s: data.get('importance', 0) for s, data in career['skills'].items()}
    total = sum(weights.values()) or 1
    relevant = sum(weights.get(s, 0) * conf for s, conf in course.get('skills', {}).items()) / total
    gap = sum(weights.get(s, 0) * conf for s, conf in course.get('skills', {}).items() if s not in covered) / total
    return min(1, relevant), min(1, gap)

def required_codes(snapshot):
    return set(c for g in snapshot['program']['groups'] for c in g.get('options', []))

def recommend(snapshot, state, prefs):
    career = career_for(snapshot, prefs)
    courses = snapshot['courses']
    covered = {skill for code in passed(state) for skill in courses.get(code, {}).get('skills', {})}
    required, _, _ = select_requirements(snapshot, state, prefs)
    grades = dict(state['completed'])
    # Recommendations for next term are conditional on successful in-progress completion.
    grades.update({c: 'C' for c in state['in_progress']})
    credits = state['applied_credits'] + sum(courses.get(c, {}).get('credits', 0) for c in state['in_progress'])
    ranked, blocked = [], []
    for code, course in courses.items():
        if code in passed(state) or code in state['in_progress']:
            continue
        if course.get('quarantined') or not evaluate(course['rule'], grades, set(), credits, state.get('approved_exceptions', []), code, {'program': snapshot['program']['id']}):
            blocked.append({'code': code, 'reason': course.get('review_reason') or 'Prerequisites, corequisites, grade or standing requirements need resolution.'})
            continue
        rel, gap = relevance(course, career, covered)
        parts = {'degree_progress': float(code in required), 'career_relevance': rel, 'skill_gap': gap,
                 'preference': float(code in prefs.get('preferred', []))}
        score = .45 * parts['degree_progress'] + .30 * rel + .20 * gap + .05 * parts['preference']
        ranked.append({**course, 'score': round(score, 6), 'score_components': parts,
                       'conditional': bool(state['in_progress']), 'offering_verified': False})
    ranked.sort(key=lambda c: (-c['score'], c['code']))
    gaps = [{'element': s, 'name': snapshot['skills'][s]['name'], 'importance': data.get('importance', 0),
             'covered_by_coursework': s in covered} for s, data in career['skills'].items()]
    gaps.sort(key=lambda g: (-g['importance'], g['element']))
    return {'version': snapshot['version'], 'courses': ranked[:50], 'blocked': blocked,
            'skill_gaps': gaps, 'warnings': ['Skill coverage is an estimate from coursework, not a proficiency assessment.',
                                          'Term offerings are unverified.', 'In-progress completion is assumed at the required grade.']}

def select_requirements(snapshot, state, prefs):
    courses = snapshot['courses']
    grades = dict(state['completed'])
    grades.update({c: 'C' for c in state['in_progress']})
    finished = {c for c, g in grades.items() if g != 'F'}
    selected, used, allocations, issues = set(), set(), {}, []
    career = career_for(snapshot, prefs)
    covered = {s for c in finished for s in courses.get(c, {}).get('skills', {})}
    groups = snapshot['program']['groups']
    known_groups = {g['id'] for g in groups}
    if set(state.get('satisfied_groups', [])) - known_groups or set(state.get('requirement_choices', {})) - known_groups:
        issues.append('Unknown requirement group identifier.')
    for group in groups:
        gid = group['id']
        if gid in state.get('satisfied_groups', []) and group.get('external'):
            allocations[gid] = ['student-confirmed']
            continue
        options = group.get('options', [])
        choices = state.get('requirement_choices', {}).get(gid)
        if group.get('external') and choices is None:
            issues.append(f"Select courses or confirm completion for {group['name']}.")
            continue
        if choices is not None and (set(choices) - set(options) or len(choices) != len(set(choices))):
            issues.append(f"Invalid or duplicate choices for {group['name']}.")
            continue
        pool = list(choices if choices is not None else options)
        pool = [c for c in pool if c not in used and c in courses and not courses[c].get('quarantined')]
        pool.sort(key=lambda c: (c not in finished, -sum(relevance(courses[c], career, covered)), c))
        chosen, total = [], 0
        if group.get('count', 0) == 0 and group.get('credits', 0) == 0:
            pool = list(choices or [])
        for c in pool:
            # Core requirements mandate C; a D does not complete the group.
            complete = c in finished and (not group.get('grade') or
                (GRADES.get(grades[c]) is not None and GRADES[grades[c]] >= GRADES[group['grade']]))
            if c in finished and not complete:
                issues.append(f"{c} does not establish the {group.get('grade')} minimum grade; review retake or equivalency.")
                continue
            chosen.append(c)
            try:
                total += credits_for(courses[c], prefs)
            except ValueError as exc:
                issues.append(str(exc))
            if not complete:
                selected.add(c)
            if (group.get('count', 0) or group.get('credits', 0)) and len(chosen) >= group.get('count', 0) and total >= group.get('credits', 0):
                break
        if len(chosen) < group.get('count', 0) or total < group.get('credits', 0):
            issues.append(f"Insufficient eligible course choices for {group['name']}.")
        used.update(chosen)
        allocations[gid] = chosen
    selected.update(prefs.get('pinned', {}))
    unknown = (set(grades) | selected) - set(courses)
    if unknown:
        issues.append('Unmatched course codes require review: ' + ', '.join(sorted(unknown)))
    selected -= finished
    # Include prerequisite closure without inventing missing courses.
    for _ in range(40):
        added = set()
        for c in selected:
            if c in courses:
                added |= dependencies(courses[c]['rule'], grades, courses)
        added -= selected | finished
        if not added:
            break
        if added - set(courses):
            issues.append('Unresolved prerequisite references: ' + ', '.join(sorted(added - set(courses))))
            break
        selected |= added
    return selected, allocations, issues

def term_label(prefs, index):
    n = prefs['start_year'] * 2 + (1 if prefs['start_term'] == 'Fall' else 0) + index
    return f"{'Fall' if n % 2 else 'Spring'} {n // 2}"

def plan(snapshot, state, prefs):
    started = time.perf_counter()
    selected, allocations, issues = select_requirements(snapshot, state, prefs)
    courses = snapshot['courses']
    if state.get('gpa') is None or state['gpa'] < 2:
        issues.append('Confirm a GPA of at least 2.0 before asserting degree completion.')
    grades = dict(state['completed'])
    grades.update({c: 'C' for c in state['in_progress']})
    base_credits = state['applied_credits'] + sum(courses.get(c, {}).get('credits', 0) for c in state['in_progress'])
    credit_map = {}
    for c in sorted(selected):
        if c in courses:
            try:
                credit_map[c] = credits_for(courses[c], prefs)
            except ValueError as exc:
                issues.append(str(exc))
    projected = base_credits + sum(credit_map.values())
    if projected < snapshot['program']['total_credits']:
        issues.append(f"Select additional unrestricted electives: projected credits {projected:g} are below 120.")
    for c, index in prefs.get('pinned', {}).items():
        if c in grades and grades[c] != 'F':
            issues.append(f'Pinned course {c} is already completed or in progress.')
    for c in selected:
        if courses.get(c, {}).get('quarantined'):
            issues.append(f'{c} is quarantined pending data review.')
    limit = 16
    if prefs.get('target_year'):
        end = prefs['target_year'] * 2 + (1 if prefs['target_term'] == 'Fall' else 0)
        start = prefs['start_year'] * 2 + (1 if prefs['start_term'] == 'Fall' else 0)
        limit = min(16, end - start + 1)
        if limit <= 0:
            issues.append('Target graduation term precedes the planning start term.')
    result = {'version': snapshot['version'], 'semesters': [], 'allocations': allocations,
              'unmet_constraints': sorted(set(issues)), 'warnings': ['Course offerings are unverified.',
              'This plan assumes successful completion at minimum required grades; confirm with an advisor.'],
              'projected_credits': projected, 'status': 'blocked', 'solver': {'states': 0}}
    if issues:
        return result
    # Solve courses as indivisible sets; concurrent prerequisites are checked inside each candidate term.
    ranks = {c['code']: c['score'] for c in recommend(snapshot, state, prefs)['courses']}
    visited, states = set(), 0
    timed_out = False
    enumeration_limited = False
    def search(remaining, current_grades, credits, index):
        nonlocal states, timed_out, enumeration_limited
        states += 1
        if states > 20000 or time.perf_counter() - started > 1.5:
            timed_out = True
            return None
        if not remaining:
            return []
        if index >= limit:
            return None
        key = (tuple(sorted(remaining)), index)
        if key in visited:
            return None
        visited.add(key)
        pins = {c for c, i in prefs.get('pinned', {}).items() if i == index}
        if any(i < index and c in remaining for c, i in prefs.get('pinned', {}).items()):
            return None
        available = [c for c in remaining if prefs.get('pinned', {}).get(c, index) == index and
            evaluate(courses[c]['rule'], current_grades, remaining, credits, state.get('approved_exceptions', []), c,
                     {'program': snapshot['program']['id']})]
        available.sort(key=lambda c: (-ranks.get(c, 0), c))
        candidates = []
        for count in range(min(prefs['max_courses'], len(available)), prefs['min_courses'] - 1, -1):
            for subset in itertools.combinations(available, count):
                if time.perf_counter() - started > 1.5 or len(candidates) >= 2000:
                    enumeration_limited = True
                    if time.perf_counter() - started > 1.5:
                        timed_out = True
                    break
                bundle = set(subset)
                if not pins <= bundle:
                    continue
                total = sum(credit_map[c] for c in subset)
                if not prefs['min_credits'] <= total <= prefs['max_credits']:
                    continue
                if not all(evaluate(courses[c]['rule'], current_grades, bundle, credits,
                        state.get('approved_exceptions', []), c, {'program': snapshot['program']['id']}) for c in subset):
                    continue
                candidates.append((total, subset))
            if timed_out or enumeration_limited:
                break
        candidates.sort(key=lambda x: (-len(x[1]), -sum(ranks.get(c, 0) for c in x[1]), x[1]))
        for total, subset in candidates:
            future = dict(current_grades)
            future.update({c: 'C' for c in subset})
            tail = search(remaining - set(subset), future, credits + total, index + 1)
            if tail is not None:
                return [{'term': term_label(prefs, index), 'index': index, 'credits': total,
                         'courses': [{**courses[c], 'selected_credits': credit_map[c]} for c in subset]}] + tail
            if timed_out:
                return None
        return None
    solution = search(selected, grades, base_credits, 0)
    result['solver'] = {'states': states, 'seconds': round(time.perf_counter() - started, 6), 'limit_reached': timed_out or enumeration_limited}
    if solution is None:
        result['status'] = 'search_limit' if timed_out or enumeration_limited else 'infeasible'
        result['unmet_constraints'] = ['No valid schedule found within the search bound.' if timed_out or enumeration_limited else
                                      'No schedule satisfies the selected prerequisite, term, pin and load constraints.']
    else:
        result['status'] = 'valid'
        result['semesters'] = solution
    return result
