import copy
from test_engine import snapshot,state,prefs,c
from classwizard.engine import plan,select_requirements
from classwizard.validator import verify

def test_independent_validator_accepts_valid_and_rejects_tampering():
    s=snapshot();st=state();p=prefs();result=plan(s,st,p)
    assert not verify(s,st,p,result)
    bad=copy.deepcopy(result);bad['semesters'][0]['courses'].append(bad['semesters'][1]['courses'][0])
    assert verify(s,st,p,bad)
    bad=copy.deepcopy(result);bad['projected_credits']=999
    assert verify(s,st,p,bad)

def test_science_needs_matching_lab_and_allows_integrated_lab():
    s=snapshot([c('BIOL 1110'),c('BIOL 1110L',credits=1),c('BIOL 1115'),c('BINF 1101',credits=4),c('PHYS 1101')])
    s['program']['groups']=[{'id':'science','name':'Science','options':list(s['courses']),'count':2,'credits':7,'external':True,'science_pairing':True,'integrated_labs':['BINF 1101']}]
    bad=state(requirement_choices={'science':['BIOL 1110','BIOL 1115','PHYS 1101']})
    assert select_requirements(s,bad,prefs())[2]
    good=state(requirement_choices={'science':['BINF 1101','BIOL 1115']})
    assert not select_requirements(s,good,prefs())[2]

def test_two_variable_credit_electives_must_also_meet_six_credits():
    courses=[c('TEST 3000',credits=1),c('TEST 4000',credits=1)]
    for course in courses:course['credit_range']=[1,3]
    s=snapshot(courses,groups=[{'id':'technical','name':'Technical electives','options':['TEST 3000','TEST 4000'],'count':2,'credits':6,'external':False}])
    st=state(requirement_choices={'technical':['TEST 3000','TEST 4000']})
    low=prefs(variable_credits={'TEST 3000':1,'TEST 4000':1})
    assert select_requirements(s,st,low)[2]
    enough=prefs(variable_credits={'TEST 3000':3,'TEST 4000':3})
    assert not select_requirements(s,st,enough)[2]
