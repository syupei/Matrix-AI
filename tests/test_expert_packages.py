"""Mechanism tests: source packages, models, people and runner reports are SIMULATED."""
import importlib.util
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
from test_pm_instances import Fixture, pm
from kit import KIT
from practice_fixture import direction, fit_record, practice_record, put, scope, capture_binding, PIXEL

s=importlib.util.spec_from_file_location('expert_api_test', KIT/'matrix/orchestration/tools/platform_api.py')
api=importlib.util.module_from_spec(s);s.loader.exec_module(api)


class Experts(Fixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.write('expert-professions.json', dict(schema='matrix-expert-professions/1', professions=['code-engineering'], configured_by='SIM-person', authorization='SIM-human preset'))
        self.e=pm.team.experts
        self.ident=dict(id='sim-expert',version='1')

    def prepare_params(self, profession='code-engineering'):
        with patch.object(self.e,'fetch',return_value={'SKILL.md':b'SIM professional method','LICENSE':b'SIM permission'}):
            self.e.prepare(pm.api(),self.root,dict(self.ident,profession=profession,url='https://example.org/sim.git',commit='a'*40))
        contract=self.e.framework_contract(pm.api(),self.root,profession)
        mapping=[dict(stage=row['stage'],requirement=row['requirement'],source=dict(path='SKILL.md',section='SIM professional method'),
                      adapted_method='Use SIM professional method',records=[row['definition']['record']]) for row in contract['requirements']]
        review=dict(reviewer='SIM',source_entry='SKILL.md',license='SIM permission',preserved_methods='SIM method',
                    directory_changes='SIM destinations mapped',dependencies='none',framework_mapping=mapping)
        return dict(self.ident,methods='Use SIM professional method. Save under workspace/private/ or workspace/public/.',review=review)

    def scenario(self, profession):
        gate = pm.admission.load_gate()
        tone = gate.tone
        workspace = self.root/'management/instances'/getattr(self,'admission_author','SIM-admission-instance')/'workspace/public'
        ref, data = direction(workspace, tone)
        # SIMULATED controller-pinned approval lives in the original project, never an author DB.
        shutil.copytree(workspace/'management/evidence',self.root/'management/evidence',dirs_exist_ok=True)
        with pm.connect(self.root) as db:
            pm.integrity.save(pm.api(),db,'direction_sample',dict(id='SIM-direction',tasks=[],closed=True,
                reviewed_direction=tone.direction_binding(tone.DEFAULT_PATH,data),confirmation_receipt=data['confirmation']['review_receipt']))
        if profession == 'product':
            arts = [ref]
            fit = fit_record(workspace, tone.direction_binding(tone.DEFAULT_PATH,data),
                             [data['parts'][k] for k in ('scene','preview','samples','practice_profile')],
                             binding_mode='pre_confirmation_direction')
            content_hash = gate.artifact_digest(workspace, arts)
            req = put(workspace,'request.json',dict(request_id='SIM',role='product',stage='P-1',scope=['workspace'],
                      artifact_sha256=content_hash,display_evidence='direction-brief.md',display_sha256=data['parts']['brief']['sha256']))
            reply = put(workspace,'reply.json',dict(request_id='SIM',actor='user',choice='confirm',scope=['workspace'],
                        artifact_sha256=content_hash,source=data['confirmation']['source'],quote=data['confirmation']['quote'],
                        display_sha256=data['parts']['brief']['sha256'],message_sha256=tone.evidence.digest(data['confirmation']['quote'])))
            state = dict(role='product',current='P-1',next='P-2',artifacts=arts,request=req['path'],response=reply['path'],
                         tone_fit_review=fit['path'])
        else:
            artifact = put(workspace,'output.md','SIM professional direction contribution')
            record = practice_record(workspace,tone,ref,'direction_contribution',[artifact])
            state = dict(role='engineering', current='E-1.1',next='E-1.2',artifacts=[artifact],
                         practice_evidence={'direction_contribution':{'workspace':record}})
        state.update(scope=['workspace'], blockers=[], tone_contract=ref, conversation_check='conversation.md')
        put(workspace,state['conversation_check'],f"{state['current']} -> {state['next']}")
        saved = put(workspace,'stage.json',state)
        paths = {file.relative_to(self.root).as_posix():self.e.digest(file.read_bytes())
                 for file in workspace.rglob('*') if file.is_file()}
        return (workspace/saved['path']).relative_to(self.root).as_posix(),paths

    def package(self, review_points=True, profession='code-engineering', enable=True, validate=True, token=''):
        if profession == 'product':
            return self.composed_package(validate=validate,enable=enable)
        params=Experts.prepare_params(self, profession)
        if review_points:
            params['review']['review_points']=[{'who':'master','what':'Review engineering baseline and open risks'}]
        adapted = self.e.adapt(pm.api(),self.root,params)
        if adapted['state'] == 'blocked':
            return adapted
        base,m=self.e.read(pm.api(),self.root,self.ident)
        sha=self.e.digest((base/'METHODS.md').read_bytes())
        author, reviewer = 'SIM-admission-instance'+token, 'SIM-independent-reviewer'+token
        self.admission_author=author
        task_id, author_run, review_run = 'SIM-admission-task'+token, 'SIM-admission'+token, 'SIM-review'+token
        for iid in (author, reviewer):
            self.call('register_instance',id=iid,instance=dict(role=profession,endpoint='SIM-'+iid,
                      write_roots=['management/instances/'+iid+'/workspace']))
        installed=self.root/'matrix/base/MATRIX.md'
        installed.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(KIT/'matrix/base/MATRIX.md',installed)
        self.call('create',task=dict(id=task_id,title='SIM actual lifecycle',owner=author,executor=author,
                  checker=reviewer,goal='SIM admission',inputs=['matrix/base/MATRIX.md'],outputs=['management/instances/'+author+'/workspace/public/'],
                  criteria=['SIM method and framework'],next_action='SIM bounded exercise'))
        self.call('launch_start',id=author_run,task_id=task_id,purpose='start',instance=author,
                  model='SIM-model',session='SIM-admission',command=['SIM'],admission_expert=self.ident,admission_runner='SIM-worker')
        self.call('launch_started',id=author_run,pid=4242)
        stage, paths = Experts.scenario(self, profession)
        self.call('hand_over',actor=author,run=author_run,evidence=sorted(paths),summary='SIM actual file handover')
        self.call('launch_exit',actor='launcher',id=author_run,exit_code=0)
        scenario = dict(stage_state=stage,contract_sha256=m['framework_contract_sha256'],mapping_sha256=m['framework_mapping_sha256'],
                        reviewer=reviewer,readback='Synthetic fixture checked manually in the test')
        self.call('launch_start',id=review_run,task_id=task_id,purpose='check',instance=reviewer,
                  model='SIM-model',session='SIM-review',command=['SIM'])
        self.call('launch_started',id=review_run,pid=4243)
        gate=pm.admission.load_gate()
        workspace=self.root/'management/instances'/author/'workspace/public'
        state=json.loads((self.root/stage).read_text())
        checked=gate.check(workspace,state,registry_root=self.root)
        completed,_=gate.framework_outputs(workspace,state,checked,registry_root=self.root)
        tested={(checked['from'],r['requirement']) for r in completed}
        expected={(r['stage'],r['requirement']) for r in self.e.framework_contract(pm.api(),self.root,profession)['requirements']}
        report=dict(passed=True, methods_sha256=sha,runner='SIM-worker',run_id=author_run,model='SIM-model',review_run_id=review_run,
                    checks={k:dict(passed=True,evidence='SIMULATED only') for k in ('method_preservation','write_isolation','handoff_contract')},
                    framework_scenario=scenario,
                    tested_requirements=[dict(stage=a,requirement=b) for a,b in sorted(tested)],
                    untested_requirements=[dict(stage=a,requirement=b) for a,b in sorted(expected-tested)])
        self.report_ref='management/instances/'+reviewer+'/workspace/public/report.json'
        dest=self.root/self.report_ref;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(report))
        task=self.t(task_id)
        self.call('review',actor=reviewer,task_id=task['id'],expected_revision=task['revision'],outcome='passed',
                  criteria_checked=task['criteria'],evidence=[self.report_ref])
        self.call('launch_exit',actor='launcher',id=review_run,exit_code=0)
        self.validation_params=dict(self.ident,evidence=dict(runner='SIM-worker',report=self.report_ref,source_sha256=sha))
        if validate:
            self.e.validate(pm.api(),self.root,self.validation_params,operator='SIM-controller')
        if enable:
            self.e.enable(pm.api(),self.root,dict(self.ident,person='SIM-person',quote='SIMULATED enable authorization'),operator='SIM-controller')
        return self.e.read(pm.api(),self.root,self.ident)[1]

    def composed_package(self, validate=True, enable=False, mutate=None, fit_transform=None):
        """No model: real author/check lifecycles with immutable, separately owned files."""
        self.write('expert-professions.json',dict(schema='matrix-expert-professions/1',professions=['product'],configured_by='SIM',authorization='SIM'))
        params=self.prepare_params('product');params['review']['review_points']=[dict(who='master',what='SIM independent direction')]
        self.e.adapt(pm.api(),self.root,params)
        author,reviewer,task_id='VIEW-author','VIEW-checker','VIEW-task'
        for iid in (author,reviewer):
            self.call('register_instance',id=iid,instance=dict(role='product',endpoint='SIM-'+iid,write_roots=['management/instances/'+iid+'/workspace']))
        trusted=self.root/'matrix/base/MATRIX.md';trusted.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(KIT/'matrix/base/MATRIX.md',trusted)
        author_public=self.root/'management/instances'/author/'workspace/public'
        checker_public=self.root/'management/instances'/reviewer/'workspace/public'
        self.call('create',task=dict(id=task_id,title='SIM two producer admission',owner=author,executor=author,checker=reviewer,
            goal='SIM P1',inputs=['matrix/base/MATRIX.md'],outputs=[author_public.relative_to(self.root).as_posix()+'/'],criteria=['SIM real independent fit'],next_action='SIM draft'))
        self.call('launch_start',id='VIEW-author-run',task_id=task_id,purpose='start',instance=author,model='SIM-model',session='SIM',command=['SIM'],admission_expert=self.ident,admission_runner='SIM-worker')
        self.call('launch_started',id='VIEW-author-run',pid=4242)
        tone=pm.admission.load_gate().tone;gate=pm.admission.load_gate()
        _,draft=direction(author_public,tone);draft.pop('confirmation')
        contract_ref=put(author_public,tone.DEFAULT_PATH,'# Direction\n\n```tone-contract\n'+json.dumps(draft)+'\n```\n')
        original=dict(role='product',current='P-1',next='P-2',scope=['workspace'],blockers=[],artifacts=[contract_ref],tone_contract=contract_ref,
            conversation_check='conversation.md',request='pending-request.json',response='pending-response.json',tone_fit_review='pending-fit.json')
        put(author_public,'conversation.md','P-1 -> P-2');put(author_public,'stage-template.json',original)
        author_paths={p.relative_to(self.root).as_posix():self.e.digest(p.read_bytes()) for p in author_public.rglob('*')
            if p.is_file() and 'management' not in p.relative_to(author_public).parts and not p.name.startswith('synthetic-')}
        self.call('hand_over',actor=author,run='VIEW-author-run',evidence=sorted(author_paths),summary='SIM unconfirmed author originals')
        self.call('launch_exit',actor='launcher',id='VIEW-author-run',exit_code=0)
        self.assertEqual('waiting_review',self.t(task_id)['state'])
        self.call('launch_start',id='VIEW-review-run',task_id=task_id,purpose='check',instance=reviewer,model='SIM-model',session='SIM',command=['SIM'])
        self.call('launch_started',id='VIEW-review-run',pid=4243)
        binding=tone.direction_binding(tone.DEFAULT_PATH,draft)
        observed=[draft['parts'][key] for key in ('scene','preview','samples','practice_profile')]
        screenshot=put(checker_public,'fit.png',PIXEL)
        fit_data=dict(tone_contract=binding,artifacts=observed,screenshot=screenshot,
            viewport='1280x800',capture_binding=capture_binding(observed,root=checker_public,screenshot=screenshot),capture='SIM deterministic render',
            genre_fit='SIM flow visible',application_drift='SIM activity preserved',copy_fit='SIM consequence words observed',outcome='passed',
            producer=author,checker=reviewer,mode='independent',review_task=task_id,binding_mode='pre_confirmation_direction')
        if fit_transform:fit_transform(fit_data)
        put(checker_public,'fit.json',fit_data)
        _,manifest=self.e.read(pm.api(),self.root,self.ident)
        contract=self.e.framework_contract(pm.api(),self.root,'product');tested={(row['stage'],row['requirement']) for row in contract['requirements'] if row['stage']=='P-1'}
        expected={(row['stage'],row['requirement']) for row in contract['requirements']}
        source_sha=self.e.admission_binding(pm.api(),self.root,self.ident)['methods_sha256']
        report=dict(passed=True,methods_sha256=source_sha,runner='SIM-worker',run_id='VIEW-author-run',review_run_id='VIEW-review-run',model='SIM-model',
            checks={key:dict(passed=True,evidence='SIM independently read actual draft') for key in ('method_preservation','write_isolation','handoff_contract')},
            framework_scenario=dict(stage_state='stage.json',reviewer=reviewer,readback='SIM actual independent observations',contract_sha256=manifest['framework_contract_sha256'],mapping_sha256=manifest['framework_mapping_sha256']),
            tested_requirements=[dict(stage=a,requirement=b) for a,b in sorted(tested)],untested_requirements=[dict(stage=a,requirement=b) for a,b in sorted(expected-tested)])
        put(checker_public,'report.json',report)
        self.report_ref=(checker_public/'report.json').relative_to(self.root).as_posix()
        review_paths={p.relative_to(self.root).as_posix():self.e.digest(p.read_bytes()) for p in checker_public.rglob('*') if p.is_file() and 'management' not in p.relative_to(checker_public).parts}
        task=self.t(task_id)
        self.call('review',actor=reviewer,task_id=task_id,expected_revision=task['revision'],outcome='passed',criteria_checked=task['criteria'],evidence=sorted(review_paths))
        self.call('launch_exit',actor='launcher',id='VIEW-review-run',exit_code=0)
        view=self.root/'management/scenario-draft';view.mkdir()
        origins=[]
        for producer,paths,public in (('author',author_paths,author_public),('review',review_paths,checker_public)):
            for source,sha in paths.items():
                logical=(self.root/source).relative_to(public).as_posix()
                if logical==tone.DEFAULT_PATH:logical='author-direction-original.md'
                if logical=='stage-template.json':logical='author-stage-original.json'
                if logical=='report.json':logical='review-report.json'
                put(view,logical,(self.root/source).read_bytes())
                origins.append(dict(logical_path=logical,source_path=source,sha256=sha,origin=producer))
        display=put(self.root,'control-display.md','Synthetic display of actual author direction and independent fit; no production approval')
        reply=put(self.root,'control-message.md','Synthetic isolated exercise approval only')
        approval_binding=dict(format='matrix-review-binding/1',request_id='VIEW-request',scope=['workspace'],actor='user',direction_sha256=binding['direction_sha256'],
            display=display,response=dict(reply,message_sha256=tone.evidence.digest('Synthetic isolated exercise approval only')),person='fixture-person',quote='Synthetic isolated exercise approval only',outcome='approved')
        receipt=tone.evidence.review_receipt(self.root,approval_binding)
        final=dict(draft,confirmation=dict(person='fixture-person',quote=approval_binding['quote'],source=reply['path'],direction_sha256=binding['direction_sha256'],review_receipt=receipt))
        final_ref=put(view,tone.DEFAULT_PATH,'# Direction\n\n```tone-contract\n'+json.dumps(final)+'\n```\n')
        content_hash=gate.artifact_digest(view,[final_ref])
        request=dict(request_id='VIEW-request',role='product',stage='P-1',scope=['workspace'],artifact_sha256=content_hash,display_evidence=display['path'],display_sha256=display['sha256'])
        response=dict(request_id='VIEW-request',actor='user',choice='confirm',scope=['workspace'],artifact_sha256=content_hash,source=reply['path'],quote=approval_binding['quote'],display_sha256=display['sha256'],message_sha256=approval_binding['response']['message_sha256'])
        request_ref=put(view,'request.json',request);response_ref=put(view,'response.json',response)
        stage=dict(original,artifacts=[final_ref],tone_contract=final_ref,request='request.json',response='response.json',tone_fit_review='fit.json')
        stage_ref=put(view,'stage.json',stage)
        controls=[]
        for kind,ref,source,diff in (
            ('contract_confirmation',final_ref,(author_public/tone.DEFAULT_PATH).relative_to(self.root).as_posix(),self.e.control_diff(draft,final)),
            ('stage',stage_ref,(author_public/'stage-template.json').relative_to(self.root).as_posix(),self.e.control_diff(original,stage)),
            ('request',request_ref,None,self.e.control_diff({},request)),('response',response_ref,None,self.e.control_diff({},response)),
            ('display',put(view,display['path'],(self.root/display['path']).read_bytes()),None,[]),
            ('synthetic_response',put(view,reply['path'],(self.root/reply['path']).read_bytes()),None,[])):
            row=dict(kind=kind,logical_path=ref['path'],sha256=ref['sha256'],diff=diff)
            if source:row['source_path']=source
            controls.append(row)
        context=dict(format='matrix-admission-scenario/1',author_run_id='VIEW-author-run',review_run_id='VIEW-review-run',state_path='stage.json',origins=origins,control_derivations=controls)
        self.scenario_view,self.scenario_context=view,context
        if mutate:mutate(view,context)
        refs=[tone.evidence.ref(view,p.relative_to(view).as_posix()) for p in view.rglob('*') if p.is_file()]
        local_ref=tone.evidence.seal_bundle(view,refs,context,destination='sealed',follow_refs=False)
        scenario_view=dict(local_ref,path=(view/local_ref['path']).relative_to(self.root).as_posix())
        self.validation_params=dict(self.ident,evidence=dict(runner='SIM-worker',report=self.report_ref,source_sha256=source_sha,scenario_view=scenario_view))
        if validate:self.e.validate(pm.api(),self.root,self.validation_params,operator='SIM-controller')
        if enable:self.e.enable(pm.api(),self.root,dict(self.ident,person='SIM-person',quote='SIM enable'),operator='SIM-controller')
        return self.e.read(pm.api(),self.root,self.ident)[1]

    def test_composed_view_accepts_real_independent_fit_and_freezes_sources(self):
        manifest=self.composed_package(enable=True)
        self.assertEqual('enabled',manifest['state'])
        self.assertTrue(manifest['validation']['gate_receipt']['view_files'])
        for path in self.root.glob('management/instances/*/workspace/public/**/*'):
            if path.is_file():path.write_text('SIM later work')
        self.e.binding(pm.api(),self.root,'product',self.ident)

    def test_composed_view_rejects_unattributed_file(self):
        with self.assertRaisesRegex(ValueError,'every scenario view file'):
            self.composed_package(mutate=lambda view,context:put(view,'unattributed-business.md','SIM invented'))

    def test_composed_view_rejects_controller_business_rewrite(self):
        def mutate(view,context):
            row=next(r for r in context['control_derivations'] if r['kind']=='contract_confirmation')
            data=pm.admission.load_gate().tone.read(view,row['logical_path']);data['core_loop']='Controller invented business'
            changed=put(view,row['logical_path'],'# Direction\n\n```tone-contract\n'+json.dumps(data)+'\n```\n');row['sha256']=changed['sha256']
        with self.assertRaisesRegex(ValueError,'only add confirmation'):
            self.composed_package(mutate=mutate)

    def test_composed_view_rejects_changed_checker_fit(self):
        def mutate(view,context):
            row=next(r for r in context['origins'] if r['logical_path']=='fit.json')
            data=json.loads((view/'fit.json').read_text());data['copy_fit']='Controller replaced independent conclusion'
            row['sha256']=put(view,'fit.json',data)['sha256']
        with self.assertRaisesRegex(ValueError,'producer trusted handback'):
            self.composed_package(mutate=mutate)

    def test_composed_view_rejects_controller_scope_or_blocker_changes(self):
        def mutate(view,context):
            row=next(r for r in context['control_derivations'] if r['kind']=='stage')
            data=json.loads((view/'stage.json').read_text());data['scope']=['workspace','invented']
            row['sha256']=put(view,'stage.json',data)['sha256'];row['diff'].append(dict(field='scope',before=['workspace'],after=data['scope']))
        with self.assertRaisesRegex(ValueError,'business scope, blockers or workflow'):
            self.composed_package(mutate=mutate)

    def test_composed_view_rejects_missing_actual_fit_capture_binding(self):
        with self.assertRaisesRegex(ValueError,'artifact reference must include'):
            self.composed_package(fit_transform=lambda fit:fit['capture_binding'].pop('receipt'))

    def test_composed_view_cannot_rewrite_independent_report_passed(self):
        def mutate(view,context):
            row=next(r for r in context['origins'] if r['logical_path']=='review-report.json')
            data=json.loads((view/'review-report.json').read_text());data['passed']=False
            row['sha256']=put(view,'review-report.json',data)['sha256']
        with self.assertRaisesRegex(ValueError,'producer trusted handback'):
            self.composed_package(mutate=mutate)

    def test_composed_view_cannot_claim_author_as_actual_checker(self):
        with self.assertRaisesRegex(ValueError,'actual author and review runs'):
            self.composed_package(mutate=lambda view,context:context.update(review_run_id='VIEW-author-run'))

    def test_composed_p1_does_not_close_downstream_direction(self):
        self.composed_package()
        view=self.scenario_view
        with self.assertRaisesRegex(ValueError,'milestone is not closed'):
            pm.admission.load_gate().tone.validate(view,pm.admission.load_gate().tone.DEFAULT_PATH,registry_root=self.root,require_closed=True)

    def test_missing_review_points_blocks_before_admission(self):
        adapted=self.package(review_points=False)
        self.assertEqual('blocked',adapted['state'])
        self.assertIn('master review points',' '.join(adapted['unresolved']))
        with self.assertRaisesRegex(ValueError,'adaptation must be complete'):
            self.e.admission_binding(pm.api(),self.root,self.ident)

    def test_adaptation_blocks_missing_conflicting_or_duplicate_mapping(self):
        params = self.prepare_params()
        mapping = params['review']['framework_mapping']
        for rows, message in ((mapping[:-1], 'missing framework mapping'),
                              ([*mapping, mapping[0]], 'duplicate framework mapping'),
                              ([dict(mapping[0], records=['irrelevant_entry']), *mapping[1:]], 'required framework record')):
            with self.subTest(message=message):
                params['review']['framework_mapping'] = rows
                adapted = self.e.adapt(pm.api(), self.root, params)
                self.assertEqual('blocked', adapted['state'])
                self.assertIn(message, ' '.join(adapted['unresolved']))
                with self.assertRaisesRegex(ValueError, 'validated expert'):
                    self.e.enable(pm.api(), self.root, self.ident)

    def test_contract_changes_under_enabled_package_but_skill_revisions_do_not(self):
        self.package()
        registry_dir = self.root/'matrix/professions'
        shutil.copytree(KIT/'matrix/professions', registry_dir)
        path = registry_dir/'code-engineering/profession.json'
        registry = json.loads(path.read_text())
        registry.update(version='19.1', standards=['Updated built-in professional practice'])
        path.write_text(json.dumps(registry))
        self.assertEqual(self.ident['id'], self.e.binding(pm.api(), self.root, 'code-engineering', self.ident)['id'])
        registry['framework_requirements']['E-2.1']['complete'] = ['rendering_choice']
        path.write_text(json.dumps(registry))
        with self.assertRaisesRegex(ValueError,'framework contract changed'):
            self.e.binding(pm.api(),self.root,'code-engineering',self.ident)
        with self.assertRaisesRegex(ValueError,'framework contract changed'):
            self.e.enable(pm.api(),self.root,dict(self.ident,person='SIM-person',quote='SIM'),operator='SIM-controller')

    def test_same_practice_dispatch_prerequisites_for_imported_and_builtin_experts(self):
        self.package()
        self.staff(self.config())
        tone = pm.admission.load_gate().tone
        contract, data = direction(self.root,tone,[scope(tone,appearance_target='yes')])
        with pm.connect(self.root) as db:
            pm.integrity.save(pm.api(),db,'direction_sample',dict(id='SIM-stage-direction',tasks=[],closed=True,
                reviewed_direction=tone.direction_binding(tone.DEFAULT_PATH,data),confirmation_receipt=data['confirmation']['review_receipt']))
        stage = dict(role='solution',current='E-2.3',scope=['workspace'],tone_contract=contract)
        for iid in ('code-engineering-001','code-engineering-002'):
            with self.subTest(instance=iid):
                self.create(iid,owner=iid,project_level=False,practice_stage=stage)
                with self.assertRaisesRegex(ValueError,'missing practice evidence: rendering_choice'):
                    self.mutate('transition',iid,state='running',reason='start',execution_receipt='SIM')

    def test_imported_product_master_still_requires_input_admission(self):
        self.write('expert-professions.json', dict(schema='matrix-expert-professions/1', professions=['product'],
                   configured_by='SIM-person', authorization='SIM-human preset'))
        self.package(profession='product')
        self.staff({'entries':[dict(id='imported',profession='product',level='T7',model='SIM-big',
                    count=1,master=True,expert=self.ident)]})
        path=self.root/'external'
        path.mkdir()
        (path/'prd.md').write_text('Synthetic external input')
        self.call('intake_register',id='PRD',path='external/prd.md',version='1',source='fixture',source_id='SIM-PRD',profession='product')
        r=self.call('intake_submit',id='PRD',master='product-001')['input']
        self.assertEqual(r['expert']['id'],'sim-expert')
        with self.assertRaisesRegex(ValueError,'not admitted'):
            self.create('PROD',owner='product-001',inputs=['external/prd.md'],admitted_inputs=['PRD'])

    def config(self):
        return {'entries':[dict(id='internal',profession='code-engineering',level='T7',model='SIM-big',count=1,master=True,aliases=['小 M.ai']),
                           dict(id='imported',profession='code-engineering',level='T4',model='SIM-small',count=1,aliases=['小王.ai'],expert=self.ident,runner='SIM-other')]}

    def test_two_sources_and_aliases_keep_distinct_stable_identity(self):
        self.package();self.staff(self.config())
        a,b=[self.instance('code-engineering-'+x) for x in ['001','002']]
        self.assertEqual('builtin',a['expert']['id']);self.assertEqual('sim-expert',b['expert']['id'])
        self.assertEqual('SIM-other',b['runner'])
        self.assertIsNone(self.e.entry(pm.api(),self.root,a))
        self.assertEqual('experts/sim-expert/1/ENTRY.md',self.e.entry(pm.api(),self.root,b))
        self.assertEqual(a['id'],pm.execute(self.root,dict(op='resolve_instance',name=' 小 m.AI '))['record']['id'])
        self.call('rename_instance',id=b['id'],expected_revision=1,alias='小王二.ai')
        self.assertEqual(b['id'],pm.execute(self.root,dict(op='resolve_instance',name='小王.ai'))['record']['id'])
        with self.assertRaisesRegex(ValueError,'duplicate'):
            self.call('rename_instance',id=a['id'],expected_revision=1,alias='小王.ai')

    def test_legacy_binding_defaults_and_renamed_profile(self):
        self.staff({'entries':[dict(id='legacy',profession='code-engineering',level='T4',model='SIM-big',count=1)]})
        iid='code-engineering-001'
        db=pm.connect(self.root)
        old=pm.integrity.records(db,'instance')[iid]
        for key in ('expert','runner','alias','alias_history'):old.pop(key,None)
        pm.integrity.save(pm.api(),db,'instance',old);db.commit();db.close()
        self.write('instance-config.json',{'entries':[dict(id='legacy',profession='code-engineering',level='T5',model='SIM-big',count=1)]})
        self.confirm()
        self.call('relevel_instance',id=iid,expected_revision=1,reason='SIM confirmed level')
        self.call('rename_instance',id=iid,expected_revision=2,alias='新别名.ai')
        profile=(self.root/'management/instances'/iid/'profile.md').read_text()
        self.assertIn('新别名.ai',profile)
        db=pm.connect(self.root,readonly=True)
        try:self.assertIn('新别名.ai',pm.views.name(pm.views.context(pm.api(),self.root,db),iid))
        finally:db.close()

    def test_transport_success_alone_is_not_admission(self):
        self.package()
        base,manifest=self.e.read(pm.api(),self.root,self.ident)
        manifest['state']='awaiting_validation'
        self.e.save(pm.api(),base,manifest)
        self.write('sim-validation.json',dict(passed=True,methods_sha256=self.e.digest((base/'METHODS.md').read_bytes()),runner='SIM-worker'))
        with self.assertRaisesRegex(ValueError,'method, isolation and handoff'):
            self.e.validate(pm.api(),self.root,dict(self.ident,evidence=dict(runner='SIM-worker',report='management/sim-validation.json',source_sha256=self.e.digest((base/'METHODS.md').read_bytes()))))

    def test_preset_and_unvalidated_package_rejected(self):
        with self.assertRaisesRegex(ValueError,'not preset'):
            self.e.allowed(pm.api(),self.root,'product')
        with patch.object(self.e,'fetch',return_value={'SKILL.md':b'SIM'}):
            self.e.prepare(pm.api(),self.root,dict(self.ident,profession='code-engineering',url='https://example.org/sim.git',commit='a'*40))
        with self.assertRaisesRegex(ValueError,'not enabled'):
            self.e.binding(pm.api(),self.root,'code-engineering',self.ident)
        with self.assertRaisesRegex(ValueError,'validated expert'):
            self.e.enable(pm.api(),self.root,self.ident)

    def test_alias_duplicates_and_package_mutation_blocked(self):
        self.package();cfg=self.config();cfg['entries'][1]['aliases']=['小 m.AI']
        self.write('instance-config.json',cfg)
        with self.assertRaisesRegex(ValueError,'duplicate'):
            self.confirm()
        self.staff(self.config())
        base,_=self.e.read(pm.api(),self.root,self.ident)
        (base/'METHODS.md').write_text('tampered')
        with self.assertRaisesRegex(ValueError,'changed'):
            self.e.entry(pm.api(),self.root,self.instance('code-engineering-002'))

    def test_disabling_pinned_package_blocks_existing_instance(self):
        self.package();self.staff(self.config())
        self.e.disable(pm.api(),self.root,dict(self.ident,reason='SIM failed review'))
        with self.assertRaisesRegex(ValueError,'not enabled'):
            self.e.entry(pm.api(),self.root,self.instance('code-engineering-002'))

    def test_public_paths_can_evolve_after_validation_but_snapshot_cannot(self):
        m=self.package(enable=False)
        for root in (self.root/'management/instances'/iid/'workspace/public' for iid in
                     ('SIM-admission-instance','SIM-independent-reviewer')):
            for path in root.rglob('*'):
                if path.is_file(): path.write_text('SIM normal later work')
        # Every authority dependency is frozen as well; later consumers need no live evidence.
        self.assertTrue(m['validation']['gate_receipt']['authority_files'])
        for name in m['validation']['gate_receipt']['authority_files']:
            (self.root/name).write_text('SIM later authority-resource evolution')
        self.e.enable(pm.api(),self.root,dict(self.ident,person='SIM-person',quote='SIM enable'),operator='SIM-controller')
        self.e.binding(pm.api(),self.root,'code-engineering',self.ident)
        view,_=self.e.evidence_bundles.verify_bundle(self.root,m['validation']['bundle'])
        next(path for path in view.rglob('*') if path.is_file()).write_text('SIM tamper')
        with self.assertRaisesRegex(ValueError,'stale artifact'):
            self.e.binding(pm.api(),self.root,'code-engineering',self.ident)

    def test_invalid_import_only_blocks_its_entry(self):
        first=self.ident.copy()
        self.package()
        self.ident=dict(id='second-expert',version='1')
        self.package(token='-two')
        self.staff({'entries':[
            dict(id='builtin',profession='code-engineering',level='T4',model='SIM-big',count=1),
            dict(id='first',profession='code-engineering',level='T4',model='SIM-big',count=1,expert=first),
            dict(id='second',profession='code-engineering',level='T4',model='SIM-big',count=1,expert=self.ident),
            dict(id='other-profession',profession='quality-engineering',level='T4',model='SIM-big',count=1)]})
        self.e.disable(pm.api(),self.root,dict(first,reason='SIM local failure'))
        entries={e['id']:e for e in self.team()['instance_config']['entries']}
        self.assertFalse(entries['first']['current'])
        self.assertIn('not enabled',entries['first']['binding_error'])
        for entry in ('builtin','second','other-profession'):
            self.assertTrue(entries[entry]['current'])
        with pm.connect(self.root) as db:
            for iid in ('code-engineering-001','code-engineering-003','quality-engineering-001'):
                self.assertIsNone(pm.team.instance_fit_issue(pm.api(),self.root,db,self.instance(iid)))
            self.assertIsNotNone(pm.team.instance_fit_issue(pm.api(),self.root,db,self.instance('code-engineering-002')))

    def test_malformed_import_manifest_does_not_invalidate_builtin_entry(self):
        self.package();self.staff(self.config())
        base,_=self.e.read(pm.api(),self.root,self.ident)
        (base/'manifest.json').write_text('[]')
        entries={e['id']:e for e in self.team()['instance_config']['entries']}
        self.assertTrue(entries['internal']['current'])
        self.assertFalse(entries['imported']['current'])
        self.assertIn('manifest must be an object',entries['imported']['binding_error'])

    def test_contract_change_only_invalidates_related_import(self):
        self.package(); self.staff(self.config())
        registry_dir=self.root/'matrix/professions'
        shutil.copytree(KIT/'matrix/professions',registry_dir)
        path=registry_dir/'code-engineering/profession.json'
        registry=json.loads(path.read_text());registry['framework_requirements']['E-2.1']['complete']=['rendering_choice']
        path.write_text(json.dumps(registry))
        entries={e['id']:e for e in self.team()['instance_config']['entries']}
        self.assertTrue(entries['internal']['current'])
        self.assertFalse(entries['imported']['current'])
        self.assertIn('framework contract changed',entries['imported']['binding_error'])

    def test_author_cannot_self_sign_validation_report(self):
        self.package(enable=False,validate=False)
        path=self.root/self.report_ref
        data=json.loads(path.read_text());data['framework_scenario']['reviewer']='SIM-admission-instance'
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'reviewer must differ'):
            self.e.validate(pm.api(),self.root,self.validation_params,operator='SIM-controller')

    def test_report_requires_real_review_run_and_handed_back_bytes(self):
        self.package(enable=False,validate=False)
        path=self.root/self.report_ref; original=path.read_text();data=json.loads(original)
        data['review_run_id']='nonexistent';path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'review run must exist'):
            self.e.validate(pm.api(),self.root,self.validation_params,operator='SIM-controller')
        data=json.loads(original);data['checks']['method_preservation']['evidence']='Author replaced independent findings'
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'report changed after reviewer handback'):
            self.e.validate(pm.api(),self.root,self.validation_params,operator='SIM-controller')

    def test_missing_handover_output_cannot_be_frozen(self):
        self.package(enable=False,validate=False)
        with pm.connect(self.root) as db:
            run=pm.integrity.records(db,'launch')['SIM-admission']
            output=next(name for name in run['handover']['files'] if name.endswith('/direction-brief.md'))
            del run['handover']['files'][output]
            pm.integrity.save(pm.api(),db,'launch',run)
        with self.assertRaisesRegex(ValueError,'evidence closure and resources must be actual handed-over'):
            self.e.validate(pm.api(),self.root,self.validation_params,operator='SIM-controller')
        self.assertFalse((self.root/'management/expert-validations').exists())

    def test_trusted_original_review_receipt_cannot_be_replaced_after_validation(self):
        self.package()
        with pm.connect(self.root) as db:
            run=pm.integrity.records(db,'launch')['SIM-review'];run['model']='SIM changed model'
            pm.integrity.save(pm.api(),db,'launch',run)
        with self.assertRaisesRegex(ValueError,'receipt changed'):
            self.e.binding(pm.api(),self.root,'code-engineering',self.ident)

    def test_source_nested_manifest_is_hashed(self):
        self.package();base,m=self.e.read(pm.api(),self.root,self.ident)
        (base/'source/manifest.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'changed'):
            self.e.read(pm.api(),self.root,self.ident)

    def test_changed_preset_blocks_existing_package(self):
        self.package()
        self.write('expert-professions.json',dict(schema='matrix-expert-professions/1',professions=[],configured_by='SIM',authorization='SIM revoked'))
        with self.assertRaisesRegex(ValueError,'not preset'):
            self.e.binding(pm.api(),self.root,'code-engineering',self.ident)

    def test_git_fetch_rejects_credentials_and_nonfixed_refs_without_network(self):
        for url,commit in [('https://token@example.org/a.git','a'*40),('file:///tmp/a','a'*40),('https://example.org/a.git','main')]:
            with self.assertRaises(ValueError):
                self.e.fetch(url,commit)


class PlatformFixture(Fixture):
    def setUp(self):
        super().setUp()
        assessments=json.loads((self.root/'management/model-fit.json').read_text())
        for row in assessments['models']:
            if row['model']=='SIM-big': row['model_version']='SIM-actual'
            if row['model']=='SIM-small': row['model_version']='SIM-actual-small'
        self.write('model-fit.json',assessments)
        self.staff()
        self.create('A')
        caps={k:{'state':'supported','evidence':'SIMULATED fixture; no real sandbox claim'} for k in ('launch','write_isolation','model_selection')}
        self.config=dict(schema=api.SPEC, project_id='SIMULATED', principals={'SIM-controller':dict(active=True,actor='PM',operations=sorted(api.OPERATIONS),task_ops=['create','derive'])},
                         runners={'default':dict(version='SIM',models={'SIM-big':'SIM-actual'},capabilities=caps)})
        self.access()
        self.seq=0

    def access(self):
        (self.root/api.CONFIG).write_text(json.dumps(self.config))

    def req(self,operation,**params):
        self.seq+=1
        return dict(protocol=api.SPEC,project_id='SIMULATED',request_id='SIM-request-'+str(self.seq),event_id='SIM-event-'+str(self.seq),op=operation,params=params)

    def run_api(self,request):
        return api.handle(self.root,request,'SIM-controller')

    def invoke(self,op,**params):
        out=self.run_api(self.req(op,**params))
        self.assertTrue(out['ok'],out)
        return out['result']

    def claim(self):
        self.invoke('runtime.configure',mode='external',expected_generation=0)
        plan=self.invoke('actions.plan')
        return self.invoke('actions.claim',action_id=plan['actions'][0]['action_id'],expected_revision=plan['revision'])['record']

class Platform(PlatformFixture, unittest.TestCase):
    def test_plan_is_readonly_and_claim_is_atomic_idempotent(self):
        self.invoke('runtime.configure',mode='external',expected_generation=0)
        plan=self.invoke('actions.plan');again=self.invoke('actions.plan')
        self.assertEqual(plan,again);self.assertEqual('planned',self.t('A')['state'])
        req=self.req('actions.claim',action_id=plan['actions'][0]['action_id'],expected_revision=plan['revision'])
        first=self.run_api(req);self.assertTrue(first['ok'],first);self.assertEqual(first,self.run_api(req))
        self.assertEqual('running',self.t('A')['state'])
        stale=self.run_api(self.req('actions.claim',action_id=plan['actions'][0]['action_id'],expected_revision=plan['revision']))
        self.assertEqual('STALE_REVISION',stale['error']['code'])
        self.assertEqual(1,len(self.invoke('runs.query')['runs']))

    def test_owner_blocks_local_launch_and_switch_during_run(self):
        rec=self.claim()
        state=pm.execute(self.root,{'op':'continue'})
        self.assertEqual('managed',state['scheduler_health']['state'])
        self.assertNotIn('重启',state['scheduler_health']['message'])
        with self.assertRaisesRegex(ValueError,'external runtime'):
            self.call('launch_start',id='SIM-local',purpose='start',task_id='A',instance=rec['instance'],model='SIM',session='SIM',command=['SIM'])
        self.assertEqual('RUNS_ACTIVE',self.run_api(self.req('runtime.configure',mode='local',expected_generation=1))['error']['code'])

    def test_cancel_does_not_claim_stopped_and_unknown_does_not_relaunch(self):
        rec=self.claim()
        rec=self.invoke('runs.event',run_id=rec['id'],expected_revision=rec['revision'],kind='unknown',receipt='SIM connection lost')['record']
        self.assertEqual([],self.invoke('actions.plan')['actions'])
        result=self.invoke('runs.cancel',run_id=rec['id'],expected_revision=rec['revision'],reason='SIM stop')
        self.assertFalse(result['stopped']);self.assertEqual('starting',result['record']['state'])
        rec=result['record']
        rec=self.invoke('runs.event',run_id=rec['id'],expected_revision=rec['revision'],kind='failed',receipt='SIM runtime confirms never started')['record']
        self.assertEqual('not_started',rec['state'])
        self.assertEqual('RUN_CLOSED',self.run_api(self.req('runs.event',run_id=rec['id'],expected_revision=rec['revision'],kind='started',pid=123,model='SIM-actual',receipt='SIM late'))['error']['code'])

    def test_auth_actor_spoof_schema_and_idempotency(self):
        self.assertEqual('UNAUTHORIZED',api.handle(self.root,self.req('inspect'),'attacker')['error']['code'])
        self.assertEqual('INVALID_REQUEST',self.run_api(self.req('tasks.command',op='derive',actor='PM'))['error']['code'])

    def test_protocol_error_and_changed_request(self):
        req=self.req('inspect');req['protocol']='matrix-platform/99'
        self.assertEqual('UNSUPPORTED_PROTOCOL',self.run_api(req)['error']['code'])
        req=self.req('runtime.configure',mode='external',expected_generation=0)
        self.assertTrue(self.run_api(req)['ok']);req['params']['mode']='local'
        self.assertEqual('IDEMPOTENCY_CONFLICT',self.run_api(req)['error']['code'])

    def test_unknown_isolation_blocks_claim_without_start(self):
        self.config['runners']['default']['capabilities']['write_isolation']={'state':'unknown'};self.access()
        self.invoke('runtime.configure',mode='external',expected_generation=0)
        plan=self.invoke('actions.plan')
        result=self.run_api(self.req('actions.claim',action_id=plan['actions'][0]['action_id'],expected_revision=plan['revision']))
        self.assertEqual('UNSUPPORTED',result['error']['code']);self.assertEqual('planned',self.t('A')['state'])

    def test_two_concurrent_claims_start_at_most_one_run(self):
        from concurrent.futures import ThreadPoolExecutor
        self.invoke('runtime.configure',mode='external',expected_generation=0)
        plan=self.invoke('actions.plan')
        requests=[self.req('actions.claim',action_id=plan['actions'][0]['action_id'],expected_revision=plan['revision']) for _ in range(2)]
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(self.run_api,requests))
        self.assertEqual(1,sum(r['ok'] for r in results))
        self.assertEqual(1,len(self.invoke('runs.query')['runs']))

    def test_failed_git_retrieval_is_machine_readable(self):
        import subprocess
        self.write('expert-professions.json', dict(schema='matrix-expert-professions/1', professions=['product'], configured_by='SIM-person', authorization='SIM-human preset'))
        with patch.object(api.pm.team.experts,'fetch',side_effect=subprocess.CalledProcessError(128,['git'])):
            result=self.run_api(self.req('expert.prepare',id='x',version='1',profession='product',url='https://example.org/x',commit='a'*40))
        self.assertEqual('SOURCE_UNAVAILABLE',result['error']['code'])
        self.assertTrue(result['error']['retryable'])

    def test_wrong_actual_model_rejected(self):
        rec=self.claim()
        result=self.run_api(self.req('runs.event',run_id=rec['id'],expected_revision=1,kind='started',pid=123,model='WRONG',receipt='SIM receipt'))
        self.assertEqual('MODEL_MISMATCH',result['error']['code'])


if __name__=='__main__':unittest.main()

@unittest.skipUnless(__import__('platform').system()=='Darwin', 'local kernel reference runner')
class ReferenceWorker(PlatformFixture, unittest.TestCase):
    def test_reference_controller_hands_over_without_worker_database_write(self):
        spec=importlib.util.spec_from_file_location('reference_worker_test', KIT/'matrix/orchestration/tools/reference_worker.py')
        worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
        import sys
        script='''import sys,re,json
from pathlib import Path
text=sys.stdin.read()
print(json.dumps({'type':'system','subtype':'init','model':'SIM-concrete-version'}),flush=True)
out=re.search(r'management/instances/[^ ]+/workspace/public/run-[a-z0-9]+-handoff.json',text).group(0).rstrip('。')
p=Path(out);p.parent.mkdir(parents=True,exist_ok=True)
file=p.parent/'candidate.txt';file.write_text('SIM worker real file')
p.write_text(json.dumps({'summary':'SIM actual local worker handover','evidence':[str(file)]}))
'''
        self.config['runners']['default']['argv']=[sys.executable,'-c',script,''];self.access()
        self.invoke('runtime.configure',mode='local',expected_generation=0)
        result=worker.execute(self.root,'SIM-controller',timeout=10)
        self.assertTrue(result['handed'],result)
        self.assertEqual('waiting_review',self.t('A')['state'])
        runs=self.invoke('runs.query')['runs'];self.assertEqual('exited',runs[0]['state'])
        self.assertEqual('SIM-actual',runs[0]['model'])
        self.assertEqual('SIM-concrete-version',runs[0]['reported_model'])


    def test_parallel_workers_complete_start_callbacks_and_handover(self):
        import sys
        import subprocess
        from concurrent.futures import ThreadPoolExecutor
        spec=importlib.util.spec_from_file_location('parallel_reference_worker', KIT/'matrix/orchestration/tools/reference_worker.py')
        worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
        script='''import sys,re,json,time
from pathlib import Path
text=sys.stdin.read()
p=Path(re.search(r'management/instances/[^ ]+/workspace/public/run-[a-z0-9]+-handoff.json',text).group(0).rstrip('。'))
f=p.parent/'candidate.txt';f.write_text('SIM actual parallel worker')
p.write_text(json.dumps({'summary':'SIM real process handover','evidence':[str(f)]}))
time.sleep(0.05)
'''
        class Case(PlatformFixture,unittest.TestCase):pass
        # Exercise mixed query/write connections while both real children run,
        # in one multithreaded controller and in two independent controllers.
        for mode in ('threads','processes'):
            for iteration in range(6):
                with self.subTest(mode=mode,iteration=iteration):
                    c=Case();c.setUp()
                    try:
                        c.create('B',executor='code-engineering-002')
                        c.config['runners']['default'].update(argv=[sys.executable,'-c',script])
                        c.config['runners']['default']['models']['SIM-small']='SIM-actual-small'
                        c.access();c.invoke('runtime.configure',mode='local',expected_generation=0)
                        actions=c.invoke('actions.plan')['actions']
                        self.assertEqual(2,len(actions))
                        def execute(action):
                            for attempt in range(4):
                                try:
                                    if mode=='threads':
                                        return worker.execute(c.root,'SIM-controller',action['action_id'],timeout=10)
                                    proc=subprocess.run([sys.executable,str(KIT/'matrix/orchestration/tools/reference_worker.py'),'--project',str(c.root),'--principal','SIM-controller','--action',action['action_id'],'--timeout','10'],capture_output=True,text=True,timeout=20)
                                    result=json.loads(proc.stdout)
                                    if proc.returncode:raise ValueError(result)
                                    return result
                                except ValueError as error:
                                    if 'STALE_REVISION' not in str(error) or attempt==3:raise
                        with ThreadPoolExecutor(max_workers=2) as pool:
                            results=list(pool.map(execute,actions))
                        self.assertTrue(all(r.get('handed') for r in results),results)
                        runs=c.invoke('runs.query')['runs']
                        self.assertEqual(2,len(runs));self.assertTrue(all(r['state']=='exited' and r.get('pid') for r in runs),runs)
                        self.assertEqual({'waiting_review'},{c.t(t)['state'] for t in ('A','B')})
                        db=pm.connect(c.root,readonly=True)
                        try:self.assertEqual('ok',db.execute('PRAGMA integrity_check').fetchone()[0])
                        finally:db.close()
                    finally:c.doCleanups()
