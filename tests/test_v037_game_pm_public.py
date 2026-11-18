"""Public PM acceptance for the completed skeleton and implemented increments."""
import copy
import json
import unittest
from pm_game_fixture import Steps, h3, OUT_BUILD, OUT_D


class GamePM(Steps, unittest.TestCase):
    def design_review(self, tid, inc, producer):
        path='design/'+tid+'/gate.json'
        self.create(tid,owner='experience-design-001',executor='experience-design-001',
                    practice_stage=dict(role='design',current='D-6',scope=['board'],tone_contract=self.C),
                    practice_completion=path,outputs=['design/'+tid+'/', 'management/reviews/','management/conversation/'])
        self.start(tid)
        walk=h3.record(self.root,'implementation_walkthrough',self.C,inc,'design/'+tid+'/walk.json')
        design_note=self.put('design/'+tid+'/review.md','SIM actual design implementation review and limitations')
        fit=self.fit_child(tid,'FIT-'+tid,'quality-engineering-002','reviews/'+tid+'-fit.json',
            lambda:h3.fit(self.root,self.C,inc,'reviews/'+tid+'-fit.json',
                          shot=self.put('reviews/'+tid+'.png',h3.shotpng()),direction_data=self.D,
                          mode='independent',checker='quality-engineering-002',producer=producer,review_task='FIT-'+tid))
        state=self.human(self.state('design','D-6',inc+[design_note],{
            'implementation_walkthrough':{'board':walk},'increment_fit':{'board':fit}}),tid)
        self.gate_file(path,state)
        self.finish(tid,[path,walk['path'],design_note['path']])
        self.assertEqual('done',self.t(tid)['state'])
        return walk,self.t(tid)['practice_receipt']

    def test_first_and_second_increment_design_reviews_and_historical_checker(self):
        self.e22();self.e23()
        config=json.loads((self.root/'management/instance-config.json').read_text())
        next(row for row in config['entries'] if row['id']=='code-executors')['count']=1
        self.write('instance-config.json',config);self.confirm()
        self.call('retire_instance',id='code-engineering-002',expected_revision=self.instance('code-engineering-002')['revision'],
                  reason='SIM retire the actual closed skeleton fit checker')
        self.assertFalse(self.instance('code-engineering-002')['active'])
        self.e24();self.e31()
        # The already closed skeleton is historical work. Retiring its actual
        # independent fit checker must not invalidate E-2.4 or its downstream.
        e32=dict(role='build',current='E-3.2',scope=['board'],tone_contract=self.C,
                 practice_evidence=self.f31['practice_evidence'],**self.up)
        self.create('BUILD',practice_stage=e32,outputs=OUT_BUILD,practice_completion='engineering/build/complete.json')
        self.start('BUILD')
        self.create('INC1',parent='BUILD',actor='PM',owner='code-engineering-003',executor='code-engineering-003',
                    checker='quality-engineering-001',outputs=['src/board.js','src/main.js','src/turn.js','engineering/build/inc1/'],
                    practice_completion='engineering/build/inc1/gate.json')
        self.start('INC1')
        board=self.put('src/board.js','SIM actual first increment evolution')
        turn=self.put('src/turn.js','SIM roll choose move')
        inc=[board,self.main1,turn]
        self.handover('INC1',[board['path'],turn['path']]);self.check('INC1')
        walk,receipt=self.design_review('D6FIRST',inc,'code-engineering-003')
        data=json.loads((self.root/walk['path']).read_text())
        data['design_review']=dict(bundle=receipt['bundle'],state_path=receipt['state_path'])
        walk=h3.ref(self.put('engineering/build/inc1/walk.json',data))
        fit=self.fit_child('INC1','FIT-INC1','quality-engineering-003','reviews/inc1-fit.json',
            lambda:h3.fit(self.root,self.C,inc,'reviews/inc1-fit.json',shot=self.put('reviews/inc1.png',h3.shotpng()),
                          direction_data=self.D,mode='independent',checker='quality-engineering-003',
                          producer='code-engineering-003',review_task='FIT-INC1'))
        evidence=copy.deepcopy(self.f31['practice_evidence'])
        evidence.update(implementation_walkthrough={'board':walk},increment_fit={'board':fit})
        path='engineering/build/inc1/gate.json'
        self.gate_file(path,self.state('build','E-3.2',inc,evidence,**self.up))
        self.mutate('update','INC1',changes={'evidence':[board['path'],turn['path'],path]},reason='SIM completed first increment review')
        self.check('INC1');self.close('INC1')
        self.assertTrue(self.t('INC1')['practice_receipt']['increment_review'])
        self.create('INC2',parent='BUILD',actor='PM',owner='code-engineering-003',executor='code-engineering-003',
                    checker='quality-engineering-001',outputs=['src/capture.js'])
        self.start('INC2');cap=self.put('src/capture.js','SIM second increment capture')
        self.handover('INC2',[cap['path']]);self.check('INC2')
        self.design_review('D6SECOND',[cap],'code-engineering-003')
        self.close('INC2')
        self.assertEqual('done',self.t('INC2')['state'])
        cumulative=[board,self.main1,turn,cap]
        walk,receipt=self.design_review('D6ALL',cumulative,'code-engineering-003')
        data=json.loads((self.root/walk['path']).read_text())
        data['design_review']=dict(bundle=receipt['bundle'],state_path=receipt['state_path'])
        walk=self.put('engineering/build/walk-all.json',data)
        fit=self.fit_child('BUILD','FIT-BUILD','quality-engineering-003','reviews/build-fit.json',
            lambda:h3.fit(self.root,self.C,cumulative,'reviews/build-fit.json',shot=self.put('reviews/build.png',h3.shotpng()),
                          direction_data=self.D,mode='independent',checker='quality-engineering-003',
                          producer='code-engineering-003',review_task='FIT-BUILD'))
        evidence=copy.deepcopy(self.f31['practice_evidence'])
        evidence.update(implementation_walkthrough={'board':walk},increment_fit={'board':fit})
        path='engineering/build/complete.json'
        self.gate_file(path,self.state('build','E-3.2',cumulative,evidence,**self.up))
        self.finish('BUILD',[path,walk['path']])
        self.assertEqual('done',self.t('BUILD')['state'])
        self.create('E33',practice_stage=dict(role='build',current='E-3.3',scope=['board'],tone_contract=self.C,**self.up),outputs=['engineering/build/e33.md'])
        self.start('E33')
        self.assertEqual('running',self.t('E33')['state'])

