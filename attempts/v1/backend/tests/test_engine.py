import copy
import pytest
from classwizard.engine import evaluate, plan, recommend, select_requirements
from classwizard.models import AcademicState, Preferences

def c(code, rule=None, credits=3):
    return {'code': code, 'title': code, 'credits': credits, 'credit_range': [credits, credits],
            'rule': rule or {'kind': 'true'}, 'description': 'Programming and software.', 'skills': {},
            'evidence': {'url': 'https://example.org/catalog'}, 'quarantined': False}

def snapshot(courses=None, groups=None):
    courses = courses or [c('TEST 1000'), c('TEST 2000', {'kind': 'course', 'code': 'TEST 1000', 'grade': 'C'})]
    groups = groups or [{'id': co['code'], 'name': co['code'], 'options': [co['code']], 'count': 1, 'credits': 0, 'external': False} for co in courses]
    return {'version': 'fixture', 'courses': {co['code']: co for co in courses}, 'skills': {},
            'careers': [{'soc': '15-1252.00', 'skills': {}}],
            'program': {'id': 'cs-bs-web-software', 'total_credits': 120, 'groups': groups}}

def state(**kwargs):
    return AcademicState(applied_credits=114, gpa=3, reviewed=True, **kwargs).model_dump()

def prefs(**kwargs):
    return Preferences(min_courses=0, min_credits=0, **kwargs).model_dump()

def test_prerequisite_sequence():
    r = plan(snapshot(), state(), prefs())
    assert r['status'] == 'valid'
    assert [[c['code'] for c in s['courses']] for s in r['semesters']] == [['TEST 1000'], ['TEST 2000']]

def test_grade_and_transfer_do_not_bypass_threshold():
    rule = {'kind': 'course', 'code': 'TEST 1000', 'grade': 'C'}
    assert evaluate(rule, {'TEST 1000': 'B'}, set(), 0)
    assert not evaluate(rule, {'TEST 1000': 'D'}, set(), 0)
    assert not evaluate(rule, {'TEST 1000': 'TR'}, set(), 0)
    assert not evaluate(rule, {}, {'TEST 1000'}, 0)

def test_and_or():
    rule = {'kind': 'and', 'items': [{'kind': 'or', 'items': [{'kind': 'course', 'code': 'TEST 1000'}, {'kind': 'course', 'code': 'TEST 1001'}]}, {'kind': 'standing', 'level': 'Junior'}]}
    assert evaluate(rule, {'TEST 1001': 'A'}, set(), 60)
    assert not evaluate(rule, {'TEST 1001': 'A'}, set(), 59)

def test_corequisite_bundle():
    courses = [c('TEST 1000', {'kind': 'course', 'code': 'TEST 1001', 'concurrent': True}),
               c('TEST 1001', {'kind': 'course', 'code': 'TEST 1000', 'concurrent': True})]
    r = plan(snapshot(courses), state(), prefs())
    assert r['status'] == 'valid'
    assert len(r['semesters']) == 1
    assert len(r['semesters'][0]['courses']) == 2

def test_pins_cannot_bypass_prerequisites():
    r = plan(snapshot(), state(), prefs(pinned={'TEST 2000': 0}))
    assert r['status'] == 'infeasible'

def test_impossible_target():
    r = plan(snapshot(), state(), prefs(target_year=2027, target_term='Fall'))
    assert r['status'] == 'infeasible'

def test_cycle():
    courses = [c('TEST 1000', {'kind': 'course', 'code': 'TEST 2000'}), c('TEST 2000', {'kind': 'course', 'code': 'TEST 1000'})]
    assert plan(snapshot(courses), state(), prefs())['status'] == 'infeasible'

def test_in_progress_is_conditional_and_not_recommended():
    r = recommend(snapshot(), state(in_progress=['TEST 1000']), prefs())
    assert [c['code'] for c in r['courses']] == ['TEST 2000']
    assert r['courses'][0]['conditional']

def test_no_elective_double_counting():
    g = [{'id': 'a', 'name': 'a', 'options': ['TEST 1000'], 'count': 1, 'credits': 0},
         {'id': 'b', 'name': 'b', 'options': ['TEST 1000'], 'count': 1, 'credits': 0}]
    selected, allocation, issues = select_requirements(snapshot(groups=g), state(), prefs())
    assert issues
    assert allocation['b'] == []

def test_variable_credits_need_selection():
    s = snapshot()
    s['courses']['TEST 1000']['credit_range'] = [1,3]
    r = plan(s, state(), prefs())
    assert r['status'] == 'blocked'
    assert any('variable-credit' in x for x in r['unmet_constraints'])

def test_unknowns_and_gpa_block_completion():
    s = snapshot()
    s['courses']['TEST 1000']['rule'] = {'kind': 'unknown'}
    assert plan(s, state(), prefs())['status'] == 'infeasible'
    st = state(); st['gpa'] = None
    assert plan(snapshot(), st, prefs())['status'] == 'blocked'

def test_invalid_inputs():
    with pytest.raises(ValueError):
        AcademicState(completed={'bad': 'A'})
    with pytest.raises(ValueError):
        Preferences(min_credits=20, max_credits=12)
    with pytest.raises(ValueError):
        AcademicState(completed={'TEST 1000': 'A'}, in_progress=['TEST 1000'])
