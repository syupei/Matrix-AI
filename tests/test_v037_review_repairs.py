"""Counterexamples from the candidate review, with actual bytes and successful control paths."""
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from kit import KIT
from practice_fixture import (PIXEL, approve, capture_binding, direction, fit_record, human_receipt,
                              png, practice_record, put, scope)
from test_pm_instances import Fixture, pm

spec=importlib.util.spec_from_file_location('review_repair_gate',KIT/'matrix/base/tools/stage_gate.py')
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
tone=gate.tone


class FrozenEvidence(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name).resolve()

    def test_bundle_survives_normal_live_evolution_and_detects_snapshot_changes(self):
        source=put(self.root,'code/main.html','<main>Initial trial</main>')
        record=put(self.root,'trial.json',dict(artifacts=[source]))
        bundle=tone.evidence.seal_bundle(self.root,[record],{'stage':'E-2.2','scope':'board'})
        put(self.root,source['path'],'<main>Skeleton built on the same path</main>')
        (self.root/record['path']).unlink()
        view,_=tone.evidence.verify_bundle(self.root,bundle)
        self.assertEqual((view/source['path']).read_text(),'<main>Initial trial</main>')
        (view/source['path']).write_text('tampered')
        with self.assertRaisesRegex(ValueError,'stale artifact'):
            tone.evidence.verify_bundle(self.root,bundle)

    def test_bundle_rejects_links_and_path_escape(self):
        original=put(self.root,'safe.txt','actual data')
        (self.root/'alias.txt').symlink_to(self.root/'safe.txt')
        with self.assertRaisesRegex(ValueError,'unsafe'):
            tone.evidence.seal_bundle(self.root,[dict(original,path='alias.txt')],{'scope':'x'})
        with self.assertRaisesRegex(ValueError,'relative'):
            tone.evidence.seal_bundle(self.root,[dict(original,path='../outside')],{'scope':'x'})
        import os
        os.link(self.root/'safe.txt',self.root/'hard.txt')
        with self.assertRaisesRegex(ValueError,'unsafe'):
            tone.evidence.seal_bundle(self.root,[original],{'scope':'x'})

    def test_complete_message_cannot_extract_approval_from_a_refusal(self):
        display=put(self.root,'shown.txt','Proposed full direction')
        response=put(self.root,'reply.txt','我还不能确认，请先补齐范围')
        binding=dict(format='matrix-review-binding/1',request_id='R',scope=['board'],actor='user',
                     display=display,response=dict(response,message_sha256=tone.evidence.digest('确认')),
                     person='owner',quote='确认',outcome='approved')
        with self.assertRaisesRegex(ValueError,'complete response'):
            tone.evidence.review_receipt(self.root,binding)

    def test_frozen_response_remains_valid_when_the_live_message_file_grows(self):
        contract,data=direction(self.root,tone)
        put(self.root,data['confirmation']['source'],'Synthetic approval\nA later unrelated message')
        artifact=put(self.root,'plan.md','Actual current technical intake')
        state=dict(role='solution',current='E-2.1',next='E-2.2',scope=['workspace'],blockers=[],artifacts=[artifact],tone_contract=contract,
                   conversation_check=put(self.root,'conversation.md','E-2.1 → E-2.2')['path'])
        self.assertTrue(gate.check(self.root,state)['allowed'])

    def test_template_feature_basis_cannot_mark_every_obligation_inapplicable(self):
        row=scope(tone)
        for feature in row['features'].values():feature['basis']='<说明需求依据或待决问题>'
        contract,_=direction(self.root,tone,[row])
        with self.assertRaisesRegex(ValueError,'template placeholder'):
            tone.validate(self.root,contract['path'])

    def test_direction_approval_cannot_authorize_a_changed_feature_profile(self):
        contract,data=direction(self.root,tone,[scope(tone,appearance_target='yes')])
        tone.validate(self.root,contract['path'])
        profile=json.loads((self.root/'practice.json').read_text())
        profile['scopes'][0]['features']['appearance_target']['value']='no'
        data['parts']['practice_profile']=put(self.root,'practice.json',profile)
        put(self.root,tone.DEFAULT_PATH,'```tone-contract\n'+json.dumps(data)+'\n```\n')
        with self.assertRaisesRegex(ValueError,'direction_sha256'):
            tone.validate(self.root,tone.DEFAULT_PATH)
        data['confirmation']['direction_sha256']=tone.direction_binding(tone.DEFAULT_PATH,data)['direction_sha256']
        put(self.root,tone.DEFAULT_PATH,'```tone-contract\n'+json.dumps(data)+'\n```\n')
        with self.assertRaisesRegex(ValueError,'review binding'):
            tone.validate(self.root,tone.DEFAULT_PATH)

    def test_png_decoder_and_capture_receipt_reject_wrong_or_reused_evidence(self):
        contract,data=direction(self.root,tone)
        data['parts']['screenshot']=put(self.root,'tiny.png',png(1,1))
        with self.assertRaisesRegex(ValueError,'dimensions'):
            tone.check_capture(self.root,data['parts'],None,viewport_value='1280x800',
                               capture_binding=data['capture_binding'],artifacts=[data['parts']['preview']])
        corrupt=bytearray(PIXEL);corrupt[42]^=1
        self.assertFalse(tone.picture(self.root/put(self.root,'corrupt.png',bytes(corrupt))['path']))
        fake=b'\x89PNG\r\n\x1a\n'+b'x'*30+b'\0\0\0\0IEND\xaeB`\x82'
        self.assertFalse(tone.picture(self.root/put(self.root,'signature.png',fake)['path']))
        actual=put(self.root,'implementation.html','<main>Current implemented board</main>')
        copied=dict(data['capture_binding'],artifacts=[actual])
        record={'screenshot':put(self.root,'copied.png',PIXEL),'viewport':'1280x800','artifacts':[actual],'capture_binding':copied}
        with self.assertRaisesRegex(ValueError,'capture receipt'):
            tone.check_capture(self.root,record,None)
        record['capture_binding']=capture_binding([actual],root=self.root,screenshot=record['screenshot'])
        tone.check_capture(self.root,record,None)  # unchanged pixels can legitimately be captured against new source bytes

    def test_png_checks_palette_structure_and_not_only_checksums(self):
        import struct,zlib
        def chunk(kind,payload):
            return struct.pack('>I',len(payload))+kind+payload+struct.pack('>I',zlib.crc32(kind+payload)&0xffffffff)
        header=chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,3,0,0,0))
        ending=chunk(b'IEND',b'')
        malformed=b'\x89PNG\r\n\x1a\n'+header+chunk(b'PLTE',b'\x10\x20\x30')+chunk(b'IDAT',b'invalid-zlib')+ending
        self.assertFalse(tone.picture(self.root/put(self.root,'bad-zlib.png',malformed)['path']))
        absent=b'\x89PNG\r\n\x1a\n'+header+chunk(b'IDAT',zlib.compress(b'\0\0'))+ending
        self.assertFalse(tone.picture(self.root/put(self.root,'no-palette.png',absent)['path']))
        valid=b'\x89PNG\r\n\x1a\n'+header+chunk(b'PLTE',b'\x10\x20\x30')+chunk(b'IDAT',zlib.compress(b'\0\0'))+ending
        self.assertTrue(tone.picture(self.root/put(self.root,'palette.png',valid)['path']))
        bad_index=b'\x89PNG\r\n\x1a\n'+header+chunk(b'PLTE',b'\x10\x20\x30')+chunk(b'IDAT',zlib.compress(b'\0\1'))+ending
        self.assertFalse(tone.picture(self.root/put(self.root,'bad-index.png',bad_index)['path']))
        duplicate=PIXEL[:33]+PIXEL[8:33]+PIXEL[33:]
        self.assertFalse(tone.picture(self.root/put(self.root,'duplicate-header.png',duplicate)['path']))

    def test_skeleton_uses_frozen_trial_but_must_review_all_current_implementation(self):
        contract,data=direction(self.root,tone,[scope(tone,appearance_target='yes')])
        trial=put(self.root,'code/scene.html','<main>Trial renderer</main>')
        evidence={key:{'workspace':practice_record(self.root,tone,contract,key,[trial],
                  **({'screenshot':put(self.root,'trial.png',PIXEL)} if key=='appearance_proof' else {}))}
                  for key in ('rendering_choice','appearance_proof')}
        initial=dict(role='solution',current='E-2.2',next='E-2.3',scope=['workspace'],blockers=[],artifacts=[trial],
                     tone_contract=contract,practice_evidence=evidence,
                     conversation_check=put(self.root,'conversation.md','E-2.2 → E-2.3')['path'])
        gate.check(self.root,initial)
        current=put(self.root,'code/scene.html','<main>Actual skeleton after trial evolution</main>')
        skeleton=practice_record(self.root,tone,contract,'core_scene_skeleton',[current],screenshot=put(self.root,'skeleton.png',PIXEL))
        fit=fit_record(self.root,contract,[current],record_path='skeleton-fit.json',
            reference_screenshot=data['parts']['screenshot'],reference_viewport=data['viewport'],comparison_state='Route choice open')
        evidence.update(core_scene_skeleton={'workspace':skeleton},skeleton_fit={'workspace':fit})
        initial.update(current='E-2.3',next='E-2.4',artifacts=[current])
        put(self.root,'conversation.md','E-2.3 → E-2.4')
        self.assertTrue(gate.check(self.root,initial)['allowed'])
        extra=put(self.root,'code/gameplay.js','export const turn = "board"')
        initial['artifacts'].append(extra)
        with self.assertRaisesRegex(ValueError,'cover current stage artifacts'):
            gate.check(self.root,initial)
        # Updating current artifacts still invalidates this stage's live fit, despite old trial snapshots.
        changed=put(self.root,current['path'],'<form>Replacement form</form>')
        initial['artifacts']=[changed]
        with self.assertRaisesRegex(ValueError,'stale artifact'):
            gate.check(self.root,initial)

    def test_design_first_d6_uses_actual_handoff_and_implemented_d6_cannot_skip_walkthrough(self):
        contract,_=direction(self.root,tone,[scope(tone,appearance_target='yes')])
        design=put(self.root,'design-spec.md','Actual design-only state and interaction specification')
        from practice_fixture import review_state
        state=review_state(self.root,gate,[design['path']],role='design',stage='D-6',following='D-7',scope_ids=['workspace'])
        state['tone_contract']=contract
        state['implementation_handoff']=put(self.root,'handoff.json',dict(delivery_kind='design_only',basis='Design delivered before implementation',artifacts=[design]))
        self.assertTrue(gate.check(self.root,state)['allowed'])
        state['implementation_handoff']=put(self.root,'handoff.json',dict(delivery_kind='implemented',basis='An actual implementation is now handed over',artifacts=[design]))
        with self.assertRaisesRegex(ValueError,'implementation_walkthrough'):
            gate.check(self.root,state)
        current=put(self.root,'current.html','<main>Implemented current scene</main>')
        state['artifacts']=[current]
        state['implementation_handoff']=put(self.root,'handoff.json',dict(delivery_kind='design_only',basis='Old design handoff',artifacts=[design]))
        with self.assertRaisesRegex(ValueError,'actual stage delivery'):
            tone.check_stage(self.root,state,[current])

    def test_build_and_quality_late_stages_require_current_observed_play(self):
        contract,_=direction(self.root,tone,[scope(tone,direct_manipulation='yes')])
        artifact=put(self.root,'current.html','<main>Current playable increment</main>')
        for stage in ('E-3.3','Q-2'):
            state=dict(current=stage,tone_contract=contract,scope=['workspace'],practice_evidence={})
            with self.subTest(stage=stage),self.assertRaisesRegex(ValueError,'playable_prototype'):
                tone.check_stage(self.root,state,[artifact])

    def test_current_playable_record_rejects_pending_and_unobserved_logs(self):
        contract,_=direction(self.root,tone,[scope(tone,direct_manipulation='yes')])
        artifact=put(self.root,'play.html','<main>Playable turn</main>')
        ref=practice_record(self.root,tone,contract,'playable_prototype',[artifact])
        tone.check_record(self.root,'playable_prototype','workspace',ref,contract)
        data=json.loads((self.root/ref['path']).read_text());data['timing']='待定'
        bad=put(self.root,'pending.json',data)
        with self.assertRaisesRegex(ValueError,'placeholder'):
            tone.check_record(self.root,'playable_prototype','workspace',bad,contract)
        data['timing']='Measured in the actual run';data['run_evidence']=put(self.root,'unobserved.json',{'status':'pending','events':[]})
        bad=put(self.root,'pending.json',data)
        with self.assertRaisesRegex(ValueError,'actual run'):
            tone.check_record(self.root,'playable_prototype','workspace',bad,contract)


class ProductionBoundaries(Fixture,unittest.TestCase):
    def setUp(self):
        super().setUp();self.staff()

    def test_executor_cannot_change_any_launch_instruction_or_checking_condition(self):
        self.create('Required')
        self.create('A',human_required=True,completion_requires=['Required'])
        attempts=({'title':'New multiplayer game'},{'next_action':'Follow a private client message'},
                  {'checker':'code-engineering-001'},{'human_required':False},{'completion_requires':[]},
                  {'executor':'code-engineering-002'})
        for changes in attempts:
            with self.subTest(changes=changes),self.assertRaisesRegex(ValueError,'production_feedback'):
                self.mutate('update','A',changes=changes,reason='Direct instruction',scope_authorization='I claim authorization')
        before=self.t('A')
        self.mutate('report','A',summary='Progress only',next_action='Client requested multiplayer',impact='PM must decide',delivery='prepared')
        self.assertEqual(self.t('A')['next_action'],before['next_action'])
        self.assertEqual(self.t('A')['last_report']['next_action'],'Client requested multiplayer')
        self.mutate('update','A','PM',changes={'title':'PM-approved within original scope'},reason='Authorized manager clarification')
        self.assertGreater(self.t('A')['work_revision'],before['work_revision'])

    def test_authorized_professional_lead_can_manage_existing_parent_scope(self):
        self.create('Parent')
        self.create('Child',parent='Parent',owner='code-engineering-002',checker='code-engineering-001')
        self.mutate('update','Child','code-engineering-001',changes={'next_action':'Implement the approved interface'},reason='Manager dispatch')
        self.assertEqual(self.t('Child')['next_action'],'Implement the approved interface')

    def test_every_business_input_path_and_pm_owner_executor_combination_requires_admission(self):
        for index,path in enumerate(('docs/PRD-v2.md','requirements.md','inbox/客户需求.docx','plain text client instruction')):
            if '.' in path:put(self.root,path,'Unreviewed business requirement')
            with self.subTest(path=path),self.assertRaisesRegex(ValueError,'admitted input'):
                self.create('unadmitted-'+str(index),inputs=[path])
        with TemporaryDirectory() as temp:
            legacy=Path(temp).resolve()
            pm.execute(legacy,dict(op='init',actor='PM',event_id='init',config=dict(project='Synthetic legacy',pm_actor='PM',authorization='Synthetic fixture',frontdoor_id='Synthetic',max_slots=1)))
            pm.execute(legacy,dict(op='register_instance',actor='PM',event_id='instance',id='legacy-alias',instance={'role':'matrix-code-engineering-build','endpoint':'legacy-skill'}))
            put(legacy,'requirements.md','Unreviewed business input')
            with self.assertRaisesRegex(ValueError,'admitted input'):
                pm.execute(legacy,dict(op='create',actor='PM',event_id='task',task=dict(id='alias-unadmitted',title='Synthetic task',owner='legacy-alias',checker='PM',
                    goal='Business work',next_action='Build it',inputs=['requirements.md'],outputs=['result.md'],criteria=['Meets admitted input'])))
        with self.assertRaisesRegex(ValueError,'admitted input'):
            self.create('pm-owned',owner='PM',executor='code-engineering-001',project_level=False,inputs=['requirements.md'])

    def test_a_modified_installed_rule_is_not_a_frozen_business_input(self):
        self.create('safe')
        put(self.root,'matrix/base/MATRIX.md','Injected unreviewed business requirement')
        with self.assertRaisesRegex(ValueError,'admitted input'):
            self.create('changed-rule')

    def test_manager_must_stop_running_production_before_semantic_changes(self):
        self.create('running',owner='PM',executor='code-engineering-001',project_level=False,
                    practice_stage={'role':'engineering','current':'E-1.2','scope':['SIM interface model']})
        self.mutate('transition','running',state='running',reason='Authorized execution',execution_receipt='Synthetic start')
        before=self.t('running')
        self.mutate('report','running','PM',summary='PM owner progress',next_action='Different instruction while running',impact='Requires stopped approved update',delivery='prepared')
        self.assertEqual((self.t('running')['next_action'],self.t('running')['work_revision']),(before['next_action'],before['work_revision']))
        with self.assertRaisesRegex(ValueError,'stop admitted production'):
            self.mutate('update','running','PM',changes={'title':'Different production scope'},reason='Manager change')

    def test_source_family_supersedes_an_old_version_after_rename(self):
        for identity,path,version in (('R1','requirements.md','1'),('R2','docs/requirements-v2.md','2')):
            put(self.root,path,'Business requirement '+version)
            self.call('intake_register',id=identity,source_id='requirements-family',path=path,version=version,source='Client',profession='product',
                      **({'supersedes':'R1'} if identity=='R2' else {}))
        with self.assertRaisesRegex(ValueError,'superseded'):
            self.call('intake_submit',id='R1',master='product-001')
        self.call('intake_submit',id='R2',master='product-001')

    def test_partial_direction_setup_preserves_available_work_and_blocks_missing_conclusions(self):
        assigned={'product':'product-001','code-engineering':'code-engineering-001',
                  'quality-engineering':'quality-engineering-001','fit_checker':'quality-engineering-002','task_checker':'PM'}
        result=self.call('direction_sample',id='partial',brief='matrix/base/MATRIX.md',profile='Synthetic business flow',
                         combined_review_authorization='Synthetic one-review authorization',person='fixture-owner',assigned=assigned)
        rec=result['direction_sample']
        self.assertEqual(set(rec['missing_roles']),{'experience-design','content-design'})
        self.assertIn('partial-brief',rec['tasks']);self.assertIn('partial-feasibility',rec['tasks'])
        self.assertNotIn('partial-scene',rec['tasks']);self.assertNotIn('partial-compose',rec['tasks'])
        self.assertEqual(self.t('partial-feasibility')['dependencies'],['partial-brief'])
        with pm.connect(self.root,readonly=True) as db:
            with self.assertRaisesRegex(ValueError,'missing professional conclusions'):
                pm.direction.confirm_milestone(pm.api(),self.root,db,self.t('partial'))

    def test_same_instance_and_fake_human_review_fail_in_a_team(self):
        artifact=put(self.root,'scene.html','<main>Actual result</main>')
        fit=fit_record(self.root,{},[artifact],mode='same_instance',producer='code-engineering-001',checker='code-engineering-001')
        with self.assertRaisesRegex(ValueError,'single-conversation'):
            tone.check_fit(self.root,fit['path'],[artifact])
        screenshot_fit=fit_record(self.root,{},[artifact],producer='code-engineering-001',checker='unlisted-human')
        screenshot_data=json.loads((self.root/screenshot_fit['path']).read_text());screenshot_data['mode']='human'
        put(self.root,screenshot_fit['path'],screenshot_data)
        with self.assertRaisesRegex(ValueError,'human response receipt'):
            tone.check_fit(self.root,screenshot_fit['path'],[artifact])
        fit=fit_record(self.root,{},[artifact],mode='human',producer='code-engineering-001',checker='unlisted-human',
                       manual_review=put(self.root,'note.md','I looked at it'),capture_unavailable='No capture')
        put(self.root,'management/people.json',dict(people=[dict(id='boss',decides=['project'])]))
        with self.assertRaisesRegex(ValueError,'listed'):
            tone.check_fit(self.root,fit['path'],[artifact])


class DirectionBindings(Fixture,unittest.TestCase):
    """Synthetic trusted PM state plus actual task transactions; no human identity assertion."""
    def setUp(self):
        super().setUp();self.staff();self.tone=pm.admission.load_gate().tone
        _,self.data=direction(self.root,self.tone)
        self.data.pop('confirmation')
        self.data['parts']['feasibility']=put(self.root,'feasibility.md','Actual synthetic feasibility conclusion')
        self.data['parts']['acceptance']=put(self.root,'acceptance.md','Actual synthetic acceptance conclusion')
        self.create('Fit',owner='quality-engineering-001',checker='PM',outputs=['fit.json'])
        self.create('Direction',owner='product-001',checker='PM',kind='stage',slots=0,
                    dependencies=['Fit'],human_required=True,outputs=[self.tone.DEFAULT_PATH])
        rec=dict(id='Direction',tasks=['Fit'],outputs={key:self.data['parts'][key]['path']
                 for key in ('brief','scene','samples','feasibility','acceptance')},
                 profile=self.data['profile'],practice_profile=self.data['parts']['practice_profile']['path'],
                 preview=self.data['parts']['preview']['path'],producer='product-001',fit_checker='quality-engineering-001',
                 masters={'product':'product-001','code-engineering':'code-engineering-001','quality-engineering':'quality-engineering-001'})
        rec['outputs'].update(compose='draft.md',fit='fit.json')
        with pm.connect(self.root) as db:pm.integrity.save(pm.api(),db,'direction_sample',rec)
        self.write_draft()
        reviewed=[self.data['parts'][key] for key in ('scene','preview','samples','practice_profile')]
        fit_record(self.root,self.tone.direction_binding(self.tone.DEFAULT_PATH,self.data),reviewed,
                   producer='product-001',checker='quality-engineering-001',review_task='Fit',binding_mode='pre_confirmation_direction')
        self.mutate('update','Fit',changes={'evidence':['fit.json']},reason='Actual synthetic fit handover')
        self.check('Fit');self.close('Fit')
        self.mutate('update','Direction',changes={'evidence':[self.tone.DEFAULT_PATH]},reason='Direction draft ready')
        self.check('Direction')
        put(self.root,'shown.md','The entire current synthetic direction and its profile were displayed')

    def write_draft(self):
        source='```tone-contract\n'+json.dumps(self.data)+'\n```\n'
        put(self.root,'draft.md',source);put(self.root,self.tone.DEFAULT_PATH,source)

    def show_and_answer(self):
        self.call('human_attention',id='R1',kind='confirmation',task_id='Direction',scope='complete direction',display='shown.md')
        put(self.root,'reply.md','I approve the complete displayed direction')
        self.call('human_attention',id='R1',response='reply.md')

    def approve_direction(self):
        result=self.mutate('human_review','Direction','PM',outcome='approved',person='owner',presented_ref='shown.md',source='reply.md',
                           quote='I approve the complete displayed direction',scope='complete direction',attention_id='R1')
        receipt=result['task']['human_review']['review_receipt']
        self.data['confirmation']=dict(person='owner',quote='I approve the complete displayed direction',source='reply.md',
            direction_sha256=self.tone.direction_binding(self.tone.DEFAULT_PATH,self.data)['direction_sha256'],review_receipt=receipt)
        self.write_draft()
        return receipt

    def test_real_display_reply_and_milestone_close_are_all_required(self):
        self.show_and_answer();self.approve_direction()
        with self.assertRaisesRegex(ValueError,'milestone is not closed'):
            self.tone.validate(self.root,self.tone.DEFAULT_PATH)
        self.close('Direction')
        self.assertEqual(self.tone.validate(self.root,self.tone.DEFAULT_PATH)['tone'],self.data['tone'])

    def test_capture_limitation_uses_the_same_single_p1_reply(self):
        self.data['parts'].pop('screenshot');self.data.pop('capture_binding')
        self.data['capture_unavailable']='The actual display works but this host cannot capture it'
        viewport_note=put(self.root,'displayed-viewport.md','The actual current preview was displayed at 1280x800 for the P-1 review')
        self.data['parts']['manual_review']=viewport_note
        self.write_draft()
        fit=json.loads((self.root/'fit.json').read_text())
        fit.update(mode='human',checker='owner',tone_contract=self.tone.direction_binding(self.tone.DEFAULT_PATH,self.data),
                   manual_review=viewport_note,capture_unavailable=self.data['capture_unavailable'],outcome='pending')
        fit.pop('screenshot');fit.pop('capture_binding')
        put(self.root,'fit.json',fit)
        with self.assertRaises(ValueError):self.tone.validate(self.root,'draft.md',confirmed=False)
        self.show_and_answer()  # pending display registration is possible without claiming a passed human review
        fit['outcome']='passed';put(self.root,'fit.json',fit)
        self.approve_direction();self.close('Direction')
        self.tone.validate(self.root,self.tone.DEFAULT_PATH)
        status=pm.execute(self.root,{'op':'human_attention_status'})
        self.assertEqual((status['count'],status['answered']),(1,1))

    def test_changed_display_cannot_reuse_the_recorded_response(self):
        self.show_and_answer()
        self.data['tone']='Different unshown direction';self.write_draft()
        with self.assertRaisesRegex(ValueError,'changed after its display'):
            self.approve_direction()
        self.call('human_attention',id='R2',kind='confirmation',task_id='Direction',scope='complete direction',display='shown.md')
        with self.assertRaisesRegex(ValueError,'already bound'):
            self.call('human_attention',id='R2',response='reply.md')
        put(self.root,'renamed-reply.md','I approve the complete displayed direction')
        with self.assertRaisesRegex(ValueError,'already bound'):
            self.call('human_attention',id='R2',response='renamed-reply.md')

    def test_live_response_append_keeps_only_the_original_message_authority(self):
        self.show_and_answer()
        put(self.root,'reply.md','I approve the complete displayed direction\nLater unrelated reply')
        self.approve_direction();self.close('Direction')
        self.tone.validate(self.root,self.tone.DEFAULT_PATH)  # frozen response remains usable
        self.data['tone']='A second direction that was never displayed';self.write_draft()
        with self.assertRaisesRegex(ValueError,'direction_sha256'):
            self.tone.validate(self.root,self.tone.DEFAULT_PATH)


if __name__=='__main__':unittest.main()
