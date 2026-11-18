"""Synthetic PM records: no real people, model sessions, or approvals."""
import json
import unittest
from test_pm_instances import Fixture, pm


class DirectionRecovery(Fixture, unittest.TestCase):
    def put(self, path, value):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(value if isinstance(value, str) else json.dumps(value), encoding='utf-8')
        return path

    def setup_direction(self, missing_content=False):
        professions = [('p','product'), ('d','experience-design'), ('e','code-engineering'), ('q','quality-engineering')]
        if not missing_content:
            professions.append(('c','content-design'))
        entries = [dict(id=i,profession=role,level='T7',model='SIM-big',count=1,master=True) for i,role in professions]
        entries.append(dict(id='checks',profession='quality-engineering',level='T7',model='SIM-big',count=2,master=False))
        entries.extend(getattr(self,'extra_entries',[]))
        self.staff({'entries': entries})
        brief = self.put('external/brief.md', 'SIM real business brief: build a route racing game.')
        self.call('intake_register', id='BRIEF', source_id='brief', path=brief, version='1', source='SIM brief', profession='product')
        self.call('intake_submit', id='BRIEF', master='product-001')
        self.call('intake_review', 'product-001', id='BRIEF', outcome='approved', conclusion='SIM clarified', resolved_risks=[], resolved_conflicts=[], open_items=[], human_required=False)
        self.call('intake_admit', id='BRIEF')
        assigned = {role: role+'-001' for _,role in professions}
        assigned.update(fit_checker='quality-engineering-002',task_checker='quality-engineering-003')
        return brief, assigned

    def test_pm_cannot_be_its_own_task_checker(self):
        brief, assigned = self.setup_direction()
        assigned['task_checker'] = 'PM'
        with self.assertRaisesRegex(ValueError, 'independent task_checker'):
            self.call('direction_sample', id='DIR', brief=brief, admitted_inputs=['BRIEF'], profile='SIM game',
                      person='SIM-owner', combined_review_authorization='SIM single review', assigned=assigned)
        self.assertFalse(any(t['id'].startswith('DIR') for t in pm.execute(self.root, {'op':'status'})['tasks']))

    def test_real_brief_completes_normal_team_p1_and_unblocks_design(self):
        from practice_fixture import direction, fit_record, put, capture_binding
        brief, assigned = self.setup_direction()
        tone = pm.admission.load_gate().tone
        rec = self.call('direction_sample', id='DIR', brief=brief, admitted_inputs=['BRIEF'], profile='SIM game',
                        person='SIM-owner', combined_review_authorization='SIM combined review', assigned=assigned)['direction_sample']
        self.complete_direction(rec, assigned, rework=True)
        from test_v037_round2_pm_stages import PMStageRound2
        self.gate=pm.admission.load_gate();self.tone=self.gate.tone;self.serial=100
        self.contract=dict(self.tone.evidence.ref(self.root,self.tone.DEFAULT_PATH),version='1')
        for stage,following in [('D-1','D-2'),('D-2','D-3')]:
            artifact=put(self.root,'design/'+stage+'.md','SIM actual '+stage+' design')
            entry=dict(role='design',current=stage,scope=['workspace'],tone_contract=self.contract)
            from practice_fixture import practice_record
            evidence={}
            if stage=='D-1':
                evidence={'direction_contribution':{'workspace':practice_record(self.root,self.tone,self.contract,'direction_contribution',[artifact])}}
            path,state=PMStageRound2.completion(self,entry,[artifact['path']],practice_evidence=evidence)
            self.create(stage,project_level=False,owner='experience-design-001',executor='experience-design-001',
                        checker='quality-engineering-003',inputs=[self.tone.DEFAULT_PATH],dependencies=['DIR'],
                        admitted_inputs=[],practice_stage=entry,practice_completion=path,outputs=[artifact['path'],path])
            self.mutate('transition',stage,state='running',reason='SIM approved direction handover',execution_receipt='SIM')
            self.mutate('transition',stage,state='waiting_review',reason='SIM complete design',stop_evidence='SIM',evidence=[artifact['path'],path])
            self.check(stage);self.close(stage)
            self.assertEqual('done',self.t(stage)['state'])
        self.reconfirm_other_scope(rec,assigned)
        self.assertFalse(self.t('D-1')['needs_recheck'])
        self.assertFalse(self.t('D-2')['needs_recheck'])
        from practice_fixture import scope
        changed=scope(self.tone);changed['description']='SIM changed existing workspace activity'
        self.direction_rows=[changed,scope(self.tone,'admin')]
        successor=self.call('direction_sample',id='DIR3',brief=brief,admitted_inputs=['BRIEF'],profile=rec['profile'],
                            person='SIM-owner',combined_review_authorization='SIM materially revised direction',assigned=assigned)['direction_sample']
        self.complete_direction(successor,assigned)
        self.assertTrue(self.t('D-1')['needs_recheck'])
        self.assertTrue(self.t('D-2')['needs_recheck'])

    def reconfirm_other_scope(self,rec,assigned):
        from practice_fixture import scope
        tone=pm.admission.load_gate().tone
        self.direction_rows=[scope(tone),scope(tone,'admin')]
        successor=self.call('direction_sample',id='DIR2',brief='external/brief.md',admitted_inputs=['BRIEF'],
                            profile=rec['profile'],person='SIM-owner',combined_review_authorization='SIM successor direction',assigned=assigned)['direction_sample']
        self.complete_direction(successor,assigned)

    def complete_direction(self, rec, assigned, human_copy=False, rework=False):
        from practice_fixture import direction, fit_record, put, capture_binding
        tone = pm.admission.load_gate().tone;did=rec['id']
        _, data = direction(self.root, tone, rows=getattr(self,'direction_rows',None), label=rec['profile'],unconfirmed=True)
        for name in ('brief', 'scene', 'samples', 'practice_profile'):
            old = data['parts'][name]
            dest = rec['practice_profile'] if name == 'practice_profile' else rec['outputs'][name]
            payload=(self.root/dest).read_bytes() if human_copy and name=='samples' else (self.root/old['path']).read_bytes()
            data['parts'][name] = put(self.root, dest, payload)
        data['parts']['preview'] = put(self.root, rec['preview'], '<main>SIM actual direction scene</main>')
        data['capture_binding'] = capture_binding([data['parts']['preview']], root=self.root, screenshot=data['parts']['screenshot'])
        for key in ('feasibility', 'acceptance'):
            data['parts'][key] = put(self.root, rec['outputs'][key], 'SIM delivered ' + key)
        def draft():
            text = '```tone-contract\n' + json.dumps(data) + '\n```\n'
            put(self.root, rec['outputs']['compose'], text)
            put(self.root, tone.DEFAULT_PATH, text)
        for suffix, *_ in pm.direction.TASKS:
            tid = did+'-'+suffix
            if tid not in rec['tasks']:continue
            if suffix == 'compose': draft()
            if suffix == 'fit':
                fit_record(self.root, tone.direction_binding(tone.DEFAULT_PATH, data),
                           [data['parts'][key] for key in ('scene', 'preview', 'samples', 'practice_profile')],
                           record_path=rec['outputs']['fit'], producer='product-001', checker=assigned['fit_checker'],
                           mode='independent', review_task=tid, binding_mode='pre_confirmation_direction')
            self.mutate('transition', tid, state='running', reason='SIM normal work', execution_receipt='SIM local execution')
            self.mutate('transition', tid, state='waiting_review', reason='SIM actual handoff', stop_evidence='SIM stopped', evidence=self.t(tid)['outputs'])
            self.check(tid); self.close(tid)
        if rework:
            self.call('human_attention',id='SIM-P1-return-'+did,task_id=did,kind='confirmation',scope='SIM complete P1',
                      display=self.put('first-display.md','SIM initial complete direction'))
            quote='SIM change the scene contour before approving the direction'
            return_source='responses/'+did+'-return.md'
            self.call('human_attention',id='SIM-P1-return-'+did,response=self.put(return_source,quote))
            self.mutate('human_review',did,'PM',outcome='changes_requested',person='SIM-owner',
                        presented_ref='first-display.md',source=return_source,quote=quote,scope='SIM complete P1',attention_id='SIM-P1-return-'+did)
            for suffix in ('fit','compose','scene'):
                tid=did+'-'+suffix
                self.mutate('transition',tid,self.t(tid)['manager'],state='planned',reason='SIM requested direction rework',
                            rework_reason='execution',note='SIM address actual human feedback')
            data['parts']['scene']=put(self.root,rec['outputs']['scene'],'SIM reworked contour after actual request')
            for suffix in ('scene','compose','fit'):
                tid=did+'-'+suffix
                if suffix=='compose':draft()
                if suffix=='fit':
                    fit_record(self.root,tone.direction_binding(tone.DEFAULT_PATH,data),
                               [data['parts'][key] for key in ('scene','preview','samples','practice_profile')],
                               record_path=rec['outputs']['fit'],producer='product-001',checker=assigned['fit_checker'],
                               mode='independent',review_task=tid,binding_mode='pre_confirmation_direction')
                self.mutate('transition',tid,state='running',reason='SIM actual P1 correction',execution_receipt='SIM new process',
                            rework_reason='execution',note='SIM address human feedback')
                self.mutate('transition',tid,state='waiting_review',reason='SIM revised delivery',stop_evidence='SIM stopped',evidence=self.t(tid)['outputs'])
                self.check(tid);self.close(tid)
        self.mutate('update', did, changes={'evidence':[tone.DEFAULT_PATH]}, reason='SIM material ready')
        self.check(did)
        self.call('human_attention', id='SIM-P1-'+did, task_id=did, kind='confirmation', scope='SIM combined P1',
                  display=self.put('display.md', 'SIM complete draft presented'))
        quote='SIM approve this complete direction '+did
        response_source='responses/'+did+'.md'
        self.call('human_attention', id='SIM-P1-'+did, response=self.put(response_source, quote))
        result=self.mutate('human_review',did,'PM',outcome='approved',person='SIM-owner',presented_ref='display.md',
                           source=response_source,quote=quote,scope='SIM combined P1',attention_id='SIM-P1-'+did)
        data['confirmation']=dict(person='SIM-owner',quote=quote,source=response_source,
            direction_sha256=tone.direction_binding(tone.DEFAULT_PATH,data)['direction_sha256'],
            review_receipt=result['task']['human_review']['review_receipt'])
        draft(); self.close(did)
        self.assertEqual(tone.validate(self.root,tone.DEFAULT_PATH)['profile'],rec['profile'])
        entry=pm.admission.load_gate().check_entry(self.root,dict(role='design',current='D-1',scope=['workspace'],tone_contract=put(self.root,tone.DEFAULT_PATH,(self.root/tone.DEFAULT_PATH).read_bytes())))
        self.assertEqual(entry['profession'],'experience-design')
        self.assertTrue(all(self.t(tid)['state']=='done' for tid in rec['tasks']))
        self.data=data

    def test_missing_profession_can_adopt_closed_gap_and_resume_composition(self):
        self.adopt_gap_delivery('human')

    def test_external_expert_delivery_is_recorded_by_pm_and_closes_p1(self):
        self.adopt_gap_delivery('expert')

    def adopt_gap_delivery(self, choice):
        brief, assigned = self.setup_direction(missing_content=True)
        result = self.call('direction_sample', id='DIR', brief=brief, admitted_inputs=['BRIEF'], profile='SIM game',
                           person='SIM-owner', combined_review_authorization='SIM single review', assigned=assigned)
        self.assertIn('content-design', result['direction_sample']['missing_roles'])
        gap = self.call('gap_open', domain='content-design', kind='not_set_up', why='SIM need sample copy', qualification='SIM content', risk='F3',task_ids=['DIR'])['record']
        self.call('gap_decide', gap=gap['id'], expected_revision=gap['revision'], choice=choice, person='SIM-owner',
                  quote='SIM designated external delivery',**({'expert':'SIM external copy specialist'} if choice=='expert' else {}))
        samples = self.put('content/方向样句.md', 'SIM actual delivered moment, text and consequence.')
        gap = pm.execute(self.root, {'op':'status'})['gaps'][gap['id']]
        with self.assertRaisesRegex(ValueError,'only PM or front desk'):
            self.call('gap_close','product-001',gap=gap['id'],expected_revision=gap['revision'],source='SIM self-attested result',evidence=[samples])
        self.call('gap_close', gap=gap['id'], expected_revision=gap['revision'], source='SIM received '+choice+' result', evidence=[samples])
        self.call('intake_register', id='COPY', source_id='copy', new_family_reason='SIM separate content delivery', path=samples, version='1', source='SIM delivered copy', profession='product')
        self.call('intake_submit', id='COPY', master='product-001')
        self.call('intake_review', 'product-001', id='COPY', outcome='approved', conclusion='SIM adopted copy', resolved_risks=[], resolved_conflicts=[], open_items=[], human_required=False, coexists_with=['BRIEF'], conflicts_with=[])
        self.call('intake_admit', id='COPY')
        result = self.call('direction_resolve_gap', id='DIR', role='content-design', gap=gap['id'], admitted_inputs=['COPY'])
        rec = result['direction_sample']
        self.assertEqual([], rec['missing_roles'])
        self.assertEqual([], rec['pending_contributions'])
        self.assertIn('DIR-compose', rec['tasks'])
        self.assertIn('DIR-fit', rec['tasks'])
        self.assertEqual(['DIR-fit'], self.t('DIR')['dependencies'])
        self.assertEqual(gap['id'], rec['gap_resolutions']['content-design']['gap'])
        self.complete_direction(rec, assigned, human_copy=True)


if __name__ == '__main__':
    unittest.main()
