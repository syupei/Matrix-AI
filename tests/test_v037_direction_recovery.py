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

    def test_bound_attention_receipt_is_recorded_and_idempotent(self):
        self.call('human_attention', id='shown', kind='confirmation', display=self.put('shown.md', 'SIM shown'), scope='SIM scope')
        self.call('human_attention', id='shown', response=self.put('reply.json', {'messages': [{'id': 'SIM-reply', 'text': 'SIM yes'}]}), response_id='SIM-reply')
        with pm.connect(self.root) as db:
            args = dict(person='SIM-owner', quote='SIM yes', scope='SIM scope', expected={'request_id': 'shown'})
            a = pm.direction.bind_attention(pm, self.root, db, 'shown', **args)
            b = pm.direction.bind_attention(pm, self.root, db, 'shown', **args)
            record = pm.integrity.records(db, 'human_attention')['shown']
            self.assertEqual(a, b)
            self.assertEqual([a], record['review_receipts'])

    def setup_direction(self, missing_content=False):
        professions = [('p','product'), ('d','experience-design'), ('e','code-engineering'), ('q','quality-engineering')]
        if not missing_content:
            professions.append(('c','content-design'))
        entries = [dict(id=i,profession=role,level='T7',model='SIM-big',count=1,master=True) for i,role in professions]
        entries.append(dict(id='checks',profession='quality-engineering',level='T7',model='SIM-big',count=2,master=False))
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
        _, data = direction(self.root, tone, label='SIM game')
        data.pop('confirmation')
        for name in ('brief', 'scene', 'samples', 'practice_profile'):
            old = data['parts'][name]
            dest = rec['practice_profile'] if name == 'practice_profile' else rec['outputs'][name]
            data['parts'][name] = put(self.root, dest, (self.root/old['path']).read_bytes())
        data['parts']['preview'] = put(self.root, rec['preview'], '<main>SIM actual direction scene</main>')
        data['capture_binding'] = capture_binding([data['parts']['preview']], root=self.root, screenshot=data['parts']['screenshot'])
        for key in ('feasibility', 'acceptance'):
            data['parts'][key] = put(self.root, rec['outputs'][key], 'SIM delivered ' + key)
        def draft():
            text = '```tone-contract\n' + json.dumps(data) + '\n```\n'
            put(self.root, rec['outputs']['compose'], text)
            put(self.root, tone.DEFAULT_PATH, text)
        for suffix, *_ in pm.direction.TASKS:
            tid = 'DIR-' + suffix
            if suffix == 'compose': draft()
            if suffix == 'fit':
                fit_record(self.root, tone.direction_binding(tone.DEFAULT_PATH, data),
                           [data['parts'][key] for key in ('scene', 'preview', 'samples', 'practice_profile')],
                           record_path=rec['outputs']['fit'], producer='product-001', checker=assigned['fit_checker'],
                           mode='independent', review_task=tid, binding_mode='pre_confirmation_direction')
            self.mutate('transition', tid, state='running', reason='SIM normal work', execution_receipt='SIM local execution')
            self.mutate('transition', tid, state='waiting_review', reason='SIM actual handoff', stop_evidence='SIM stopped', evidence=self.t(tid)['outputs'])
            self.check(tid); self.close(tid)
        self.mutate('update', 'DIR', changes={'evidence':[tone.DEFAULT_PATH]}, reason='SIM material ready')
        self.check('DIR')
        self.call('human_attention', id='SIM-P1', task_id='DIR', kind='confirmation', scope='SIM combined P1',
                  display=self.put('display.md', 'SIM complete draft presented'))
        quote='SIM approve this complete direction'
        self.call('human_attention', id='SIM-P1', response=self.put('response.md', quote))
        result=self.mutate('human_review','DIR','PM',outcome='approved',person='SIM-owner',presented_ref='display.md',
                           source='response.md',quote=quote,scope='SIM combined P1',attention_id='SIM-P1')
        data['confirmation']=dict(person='SIM-owner',quote=quote,source='response.md',
            direction_sha256=tone.direction_binding(tone.DEFAULT_PATH,data)['direction_sha256'],
            review_receipt=result['task']['human_review']['review_receipt'])
        draft(); self.close('DIR')
        self.assertEqual(tone.validate(self.root,tone.DEFAULT_PATH)['profile'],'SIM game')
        entry=pm.admission.load_gate().check_entry(self.root,dict(role='design',current='D-1',scope=['workspace'],tone_contract=put(self.root,tone.DEFAULT_PATH,(self.root/tone.DEFAULT_PATH).read_bytes())))
        self.assertEqual(entry['profession'],'experience-design')
        self.assertTrue(all(self.t(tid)['state']=='done' for tid in rec['tasks']))

    def test_missing_profession_can_adopt_closed_gap_and_resume_composition(self):
        brief, assigned = self.setup_direction(missing_content=True)
        result = self.call('direction_sample', id='DIR', brief=brief, admitted_inputs=['BRIEF'], profile='SIM game',
                           person='SIM-owner', combined_review_authorization='SIM single review', assigned=assigned)
        self.assertIn('content-design', result['direction_sample']['missing_roles'])
        gap = self.call('gap_open', domain='content-design', kind='not_set_up', why='SIM need sample copy', qualification='SIM content', risk='F3')['record']
        self.call('gap_decide', gap=gap['id'], expected_revision=gap['revision'], choice='human', person='SIM-owner', quote='SIM human will deliver')
        samples = self.put('content/方向样句.md', 'SIM actual delivered moment, text and consequence.')
        gap = pm.execute(self.root, {'op':'status'})['gaps'][gap['id']]
        self.call('gap_close', gap=gap['id'], expected_revision=gap['revision'], source='SIM human result', evidence=[samples])
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


if __name__ == '__main__':
    unittest.main()
