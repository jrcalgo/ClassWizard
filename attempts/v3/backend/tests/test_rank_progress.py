from test_engine import snapshot,state,prefs,c
from classwizard.engine import recommend,select_requirements

def test_unrestricted_pool_does_not_mark_every_course_as_required():
    s=snapshot([c('TEST 1000'),c('TEST 2000'),c('TEST 3000')])
    s['program']['groups']=[s['program']['groups'][0],{'id':'unrestricted','name':'Electives','options':list(s['courses']), 'count':0,'credits':0,'external':True}]
    st=state(satisfied_groups=['unrestricted'])
    result=recommend(s,st,prefs())
    scores={c['code']:c['score_components']['degree_progress'] for c in result['courses']}
    assert scores['TEST 1000']==1 and scores['TEST 3000']==0

def test_unrestricted_explicit_choices_are_all_allocated():
    s=snapshot();s['program']['groups']=[{'id':'unrestricted','name':'Electives','options':list(s['courses']),'count':0,'credits':0,'external':True}]
    selected,allocations,issues=select_requirements(s,state(requirement_choices={'unrestricted':['TEST 1000','TEST 2000']}),prefs())
    assert selected=={'TEST 1000','TEST 2000'} and not issues
