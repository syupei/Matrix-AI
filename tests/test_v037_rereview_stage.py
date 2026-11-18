"""Round-two stage regressions. All people, approvals, execution logs and images are synthetic."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from practice_fixture import png
from kit import KIT

BASE = KIT / 'matrix/base/tools'
spec = importlib.util.spec_from_file_location('round2_stage', BASE / 'stage_gate.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
tone = gate.tone


class StageRegressions(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.serial = 0
        self.contract, self.data = self.direction()

    def put(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, dict): data = json.dumps(data, ensure_ascii=False)
        path.write_bytes(data.encode() if isinstance(data, str) else data)
        return tone.evidence.ref(self.root, name)

    def row(self, sid='board', **features):
        return dict(id=sid, description='Synthetic static scope '+sid,
                    features={key:dict(value=features.get(key,'no'),basis='Actual fixture activity '+key) for key in tone.practice.FEATURES},
                    practices={key:dict(approach='Follow the declared object activity',pitfall='Omit its result',check='Read the actual output') for key in tone.practice.PROFESSIONS})

    def capture(self, artifacts, name, state='current'):
        color=tuple(hashlib.sha256(json.dumps(artifacts,sort_keys=True).encode()).digest()[:3])
        picture=self.put(name,png(color=color))
        binding=dict(artifacts=artifacts,pixel_size=[1280,800],viewport='1280x800',scale=1,state=state,method='Synthetic deterministic rendering',source='Unit fixture')
        binding['receipt']=self.put(name+'.capture.json',dict(binding,screenshot_sha256=picture['sha256']))
        return picture,binding

    def approve(self, data):
        self.serial+=1
        message='Synthetic complete approval '+str(self.serial)
        display=self.put('reviews/shown-'+str(self.serial)+'.md','Displayed this complete direction '+str(self.serial))
        reply=self.put('reviews/reply-'+str(self.serial)+'.json',dict(messages=[dict(id='message-'+str(self.serial),text=message)]))
        scopes=[row['id'] for row in tone.profile(self.root,data)['scopes']]
        binding=dict(format='matrix-review-binding/1',request_id='review-'+str(self.serial),scope=scopes,actor='user',
                     person='synthetic-user',quote=message,outcome='approved',display=display,
                     response=dict(reply,response_id='message-'+str(self.serial),message_sha256=tone.evidence.digest(message)),
                     direction_sha256=tone.direction_binding(tone.DEFAULT_PATH,data)['direction_sha256'])
        data['confirmation']=dict(person=binding['person'],quote=message,source=reply['path'],direction_sha256=binding['direction_sha256'],review_receipt=tone.evidence.review_receipt(self.root,binding))
        self.put(tone.DEFAULT_PATH,'```tone-contract\n'+json.dumps(data)+'\n```\n')
        return dict(tone.evidence.ref(self.root,tone.DEFAULT_PATH),version=data['version'])

    def direction(self, rows=None):
        parts={key:dict(self.put(name,value),version='1') for key,name,value in [
            ('brief','brief.md','Synthetic declared scope'),('scene','design/preview.html','<main>Scene objects</main>'),
            ('samples','copy.md','Synthetic operation copy'),
            ('practice_profile','practice.json',dict(schema=tone.practice.SCHEMA,version='1',scopes=rows or [self.row()]))]}
        parts['preview']=parts['scene']
        screenshot,binding=self.capture([parts['preview']],'design/direction.png','initial')
        parts['screenshot']=dict(screenshot,version='1')
        data=dict(version='1',genre='Synthetic product',profile='Activity',tone='Clear',core_loop='Enter and act',viewport='1280x800',parts=parts,capture_binding=binding,
                  references=[dict(name='External work '+str(i),source='https://example.test/work/'+str(i),borrows='Object-to-result activity',observed='Synthetic locator only; not visited') for i in (1,2)],
                  avoid=['Lose the object state'],samples=[dict(moment='Moment '+str(i%4),text='Actual line '+str(i),consequence='Continue activity') for i in range(6)])
        return self.approve(data),data

    def state(self, role, stage, artifacts, following=None, **extra):
        self.serial+=1
        digest=gate.artifact_digest(self.root,artifacts)
        prefix='reviews/stage-'+str(self.serial)
        shown=self.put(prefix+'-display.md','Displayed all synthetic stage artifacts')
        if role=='design' and stage=='D-4' and extra.get('practice_evidence',{}).get('asset_anchors'):
            receipts={}
            for sid, record in extra['practice_evidence']['asset_anchors'].items():
                result=tone.asset_comparison_receipt(self.root,record['path'])
                receipts[sid]=result['asset_comparison_receipt'];shown=result['review_page']
            extra['asset_comparison_receipts']=receipts
        message='Confirmed synthetic stage '+str(self.serial)
        reply=self.put(prefix+'-human.md',message)
        request=self.put(prefix+'-request.json',dict(request_id=prefix,role=role,stage=stage,scope=['board'],artifact_sha256=digest,display_evidence=shown['path'],display_sha256=shown['sha256']))
        response=self.put(prefix+'-response.json',dict(request_id=prefix,scope=['board'],artifact_sha256=digest,actor='user',choice='confirm',source=reply['path'],quote=message,display_sha256=shown['sha256'],message_sha256=tone.evidence.digest(message)))
        following=following or gate.STAGES[role][gate.STAGES[role].index(stage)+1]
        state=dict(role=role,current=stage,next=following,scope=['board'],blockers=[],artifacts=artifacts,tone_contract=self.contract,
                   request=request['path'],response=response['path'],conversation_check=self.put(prefix+'-conversation.md',stage+' → '+following)['path'])
        state.update(extra)
        return state

    def fit(self, artifacts, name='fit.json', **extra):
        picture,binding=self.capture(artifacts,name+'.png')
        data=dict(outcome='passed',mode='same_instance',producer='single',checker='single',artifacts=artifacts,tone_contract=self.contract,
                  screenshot=picture,capture_binding=binding,viewport='1280x800',capture='Synthetic current capture',genre_fit='Objects readable',application_drift='Activity retained',copy_fit='Copy matches')
        data.update(extra)
        return self.put(name,data)

    def record(self, key, artifacts, name=None, **extra):
        data={key:'Specific synthetic '+key for key in tone.practice.REQUIREMENTS[key]['fields']}
        data.update(scope='board',tone_contract=self.contract,artifacts=artifacts,**extra)
        return self.put(name or key+'.json',data)

    def frozen(self, result):
        view,_=tone.evidence.stage_receipt(self.root,result['review_bundle'])
        return view,json.loads(tone.evidence.file(view,result['upstream_state']).read_text())

    def solution_review(self):
        artifact=self.put('engineering/solution.md','Actual synthetic technical scope')
        return gate.check(self.root,self.state('solution','E-2.4',[artifact]))

    def test_design_only_d6_snapshot_contains_handoff_and_replays(self):
        artifact=self.put('design/spec.md','Design-only specifications')
        handoff=self.put('design/handoff.json',dict(delivery_kind='design_only',basis='No implementation has been handed over',artifacts=[artifact]))
        result=gate.check(self.root,self.state('design','D-6',[artifact],implementation_handoff=handoff))
        view,state=self.frozen(result)
        self.assertTrue((view/handoff['path']).is_file())
        self.assertTrue(gate.check(view,state,registry_root=self.root,seal=False)['allowed'])
        self.assertTrue(gate.check_entry(self.root,dict(role='design',current='D-7',scope=['board']))['profession'])

    def test_delegated_solution_freezes_every_record_it_reads(self):
        artifact=self.put('engineering/solution.md','Delegated technical scope')
        state=self.state('solution','E-2.4',[artifact]);digest=gate.artifact_digest(self.root,[artifact])
        source=self.put('reviews/grant.md','Synthetic explicit scoped delegation')
        self.put('management/delegations.json',dict(delegations=[dict(id='D',revision=1,revoked=False,expires_at='2099-01-01T00:00:00+00:00',role='solution',stages=['E-2.4'],scope=['board'],source=source['path'],source_sha256=source['sha256'],person_id='user',instance_id='delegate')]))
        proof=self.put('reviews/independent.json',dict(checker='other',outcome='passed',artifact_sha256=digest,scope=['board'],evidence=self.put('reviews/verification.md','Synthetic independent verification evidence')['path']))
        state['delegated_decision']=self.put('reviews/delegated.json',dict(delegation_id='D',delegation_revision=1,instance_id='delegate',decision_kind='routine',role='solution',stage='E-2.4',artifact_sha256=digest,scope=['board'],source=self.put('reviews/rationale.md','Synthetic technical rationale')['path'],producers=['maker'],review=proof['path']))['path']
        result=gate.check(self.root,state);view,saved=self.frozen(result)
        self.assertTrue((view/'management/delegations.json').is_file())
        self.assertTrue(gate.check(view,saved,registry_root=self.root,seal=False)['allowed'])
        next_state=dict(role='build',current='E-3.1',scope=['board'],tone_contract=self.contract,upstream=result['upstream_state'],upstream_bundle=result['review_bundle'])
        self.assertTrue(gate.check_entry(self.root,next_state))

        # New decisions use current time; successful historical decisions use their
        # sealed check timestamp, including the next stage's upstream replay.
        from datetime import datetime, timezone
        from unittest.mock import patch
        class Future(datetime):
            @classmethod
            def now(cls,tz=None):return cls(2100,1,1,tzinfo=timezone.utc)
        with patch.object(gate,'datetime',Future):
            self.assertTrue(gate.check(view,saved,registry_root=self.root,seal=False)['allowed'])
            self.assertTrue(gate.check_entry(self.root,next_state))
            with self.assertRaisesRegex(ValueError,'expired'):
                gate.check(self.root,state)

    def test_partial_upstream_is_rejected_before_a_success_receipt(self):
        result=self.solution_review()
        with self.assertRaisesRegex(ValueError,'upstream_bundle'):
            gate.check_entry(self.root,dict(role='build',current='E-3.1',scope=['board'],tone_contract=self.contract,upstream=result['upstream_state']))

    def test_new_contract_preserves_an_unchanged_scope_but_not_a_changed_one(self):
        result=self.solution_review();view,state=self.frozen(result)
        profile=json.loads((self.root/'practice.json').read_text());profile['version']='2';profile['scopes'].append(self.row('admin'))
        self.data['version']='2';self.data['parts']['practice_profile']=dict(self.put('practice.json',profile),version='2')
        self.contract=self.approve(self.data)
        self.assertTrue(gate.check(view,state,registry_root=self.root,seal=False)['allowed'])
        profile['scopes'][0]['practices']['product']['approach']='Changed core activity'
        self.data['parts']['practice_profile']=dict(self.put('practice.json',profile),version='2');self.contract=self.approve(self.data)
        with self.assertRaisesRegex(ValueError,'activity scope'):
            gate.check(view,state,registry_root=self.root,seal=False)

    def test_scope_comparison_defaults_to_the_current_project_authority(self):
        # An isolated old contract snapshot deliberately contains business evidence,
        # not a copied PM/response authority ledger.
        found=tone.evidence.closure(self.root,[self.contract])
        bundle=tone.evidence.seal_bundle(self.root,[dict(path=name,sha256=sha) for name,sha in found.items()],
                                         dict(format='synthetic-contract-snapshot/1'),follow_refs=False)
        old,_=tone.evidence.verify_bundle(self.root,bundle)
        self.assertFalse((old/'management/review-bindings').exists())
        self.assertTrue(tone.check_contract_scope(old,self.contract,self.root,self.contract,['board']))

    def test_d2_new_fit_does_not_require_deleted_d1_artifact_bytes(self):
        self.contract,self.data=self.direction([self.row(appearance_target='yes')])
        old=self.put('design/old.svg','<svg><path/></svg>')
        evidence={'direction_contribution':{'board':self.record('direction_contribution',[old])},'appearance_target':{'board':self.record('appearance_target',[old])},'design_fit':{'board':self.fit([old],'d1-fit.json')}}
        first=gate.check(self.root,self.state('design','D-1',[old],practice_evidence=evidence))
        (self.root/old['path']).unlink();current=self.put('design/refined.svg','<svg><circle/></svg>')
        evidence={'appearance_target':first['practice_evidence']['appearance_target'],'design_fit':{'board':self.fit([current],'d2-fit.json')}}
        result=gate.check(self.root,self.state('design','D-2',[current],practice_evidence=evidence))
        self.assertTrue(result['allowed'])
        fake=self.record('appearance_target',[current],'forged.json')
        fake['bundle']=tone.evidence.seal_bundle(self.root,[fake],dict(role='design',stage='D-1',scope='board',requirement='appearance_target',tone_contract=self.contract))
        evidence['appearance_target']={'board':fake}
        with self.assertRaisesRegex(ValueError,'successful registered stage'):
            gate.check(self.root,self.state('design','D-2',[current],practice_evidence=evidence))

    def test_a_valid_history_cannot_replace_the_selected_upstream(self):
        self.contract,self.data=self.direction([self.row(appearance_target='yes')])
        def d1(name):
            artifact=self.put(name+'.svg','<svg>'+name+'</svg>')
            records={key:{'board':self.record(key,[artifact],name+'-'+key+'.json')} for key in ('direction_contribution','appearance_target')}
            records['design_fit']={'board':self.fit([artifact],name+'-fit.json')}
            return gate.check(self.root,self.state('design','D-1',[artifact],practice_evidence=records))
        first=d1('first');selected=d1('selected')
        artifact=self.put('refined.svg','<svg>New scoped design</svg>')
        records={'appearance_target':first['practice_evidence']['appearance_target'],'design_fit':{'board':self.fit([artifact],'current-fit.json')}}
        state=self.state('design','D-2',[artifact],practice_evidence=records,
                         upstream=selected['upstream_state'],upstream_bundle=selected['review_bundle'])
        with self.assertRaisesRegex(ValueError,'chosen upstream stage'):
            gate.check(self.root,state)
        records['appearance_target']=selected['practice_evidence']['appearance_target']
        self.assertTrue(gate.check(self.root,state)['allowed'])

    def test_admission_view_is_not_mistaken_for_registered_stage_history(self):
        from unittest.mock import patch
        artifact=self.put('views/design.md','Actual isolated design view')
        state=self.state('design','D-6',[artifact],implementation_handoff=self.put('views/handoff.json',
                         dict(delivery_kind='design_only',basis='No implementation',artifacts=[artifact])))
        state_ref=self.put('views/state.json',state)
        bundle=tone.evidence.seal_bundle(self.root,[state_ref],dict(format='matrix-admission-scenario/1',state_path=state_ref['path']))
        view,_=tone.evidence.verify_bundle(self.root,bundle)
        # Scenario evidence is a current isolated view, not a closed stage replay.
        # Observe the branch without pretending this fixture has a complete PM authority.
        with patch.object(gate,'_check',return_value={'allowed':True}) as checked:
            self.assertTrue(gate.check(view,state,registry_root=self.root,seal=False)['allowed'])
            self.assertFalse(checked.call_args.args[-1])

    def test_scaled_thumbnail_and_cross_source_reused_picture_are_rejected(self):
        picture=self.put('tiny.png',png(16,10));binding=dict(artifacts=[self.data['parts']['preview']],pixel_size=[16,10],viewport='1280x800',scale=.0125,state='initial',method='synthetic',source='fixture')
        binding['receipt']=self.put('tiny-receipt.json',dict(binding,screenshot_sha256=picture['sha256']))
        with self.assertRaisesRegex(ValueError,'dimensions'):
            tone.check_capture(self.root,dict(screenshot=picture,viewport='1280x800',capture_binding=binding),None)
        origin=dict(screenshot=self.data['parts']['screenshot'],capture_binding=self.data['capture_binding'])
        tone.compare_capture_source(origin,origin)
        changed=dict(origin,capture_binding=dict(origin['capture_binding'],artifacts=[self.put('other.html','<main>different</main>')]))
        with self.assertRaisesRegex(ValueError,'different source'):
            tone.compare_capture_source(changed,origin)

    def test_fake_independent_without_project_run_cannot_bypass_single_instance(self):
        artifact=self.put('result.svg','<svg/>');ref=self.fit([artifact],mode='independent',producer='invented maker',checker='invented checker')
        with self.assertRaisesRegex(ValueError,'trusted project review run'):
            tone.check_fit(self.root,ref['path'],[artifact],self.contract)

    def test_historical_fit_accepts_retired_registered_instances_but_new_fit_does_not(self):
        artifact=self.put('src/board.js','const board=1');ref=self.fit([artifact],mode='independent',producer='maker',checker='checker',review_task='CHECK')
        directory=self.root/'management/runtime';directory.mkdir(parents=True)
        with sqlite3.connect(directory/'tasks.sqlite3') as db:
            db.execute('CREATE TABLE pm_records(kind TEXT,id TEXT,data TEXT)');db.execute('CREATE TABLE tasks(id TEXT,data TEXT)')
            for identity in ['maker','checker']:db.execute('INSERT INTO pm_records VALUES(?,?,?)',('instance',identity,json.dumps(dict(id=identity,active=False,profession='code-engineering'))))
            for task in [dict(id='MAKE',owner='maker',executor='maker',handed_output_sha256={artifact['path']:artifact['sha256']}),dict(id='CHECK',owner='checker',state='done',handed_output_sha256={ref['path']:ref['sha256']})]:db.execute('INSERT INTO tasks VALUES(?,?)',(task['id'],json.dumps(task)))
        self.assertTrue(tone.check_fit(self.root,ref['path'],[artifact],self.contract,historical=True))
        with self.assertRaisesRegex(ValueError,'active project instances'):
            tone.check_fit(self.root,ref['path'],[artifact],self.contract)

    def test_first_increment_uses_its_actual_stage_and_real_design_snapshot(self):
        self.contract,self.data=self.direction([self.row(appearance_target='yes')])
        artifact=self.put('src/increment.js','const currentTurn=1')
        observation=self.put('reviews/increment-state.json',dict(state='Current turn',result='HUD retained'))
        def records(prefix, design=None):
            walkthrough=self.record('implementation_walkthrough',[artifact],prefix+'-walk.json',
                preserved_states=[dict(state='Current player',layer='HUD',basis='Required to decide next action')],
                design_recheck_states=[dict(state='Current turn',method='Read the actual HUD',evidence=observation)],corrections=[])
            if design:
                data=json.loads((self.root/walkthrough['path']).read_text());data['design_review']=dict(bundle=design['review_bundle'],state_path=design['upstream_state'])
                walkthrough=self.put(walkthrough['path'],data)
            fit=self.fit([artifact],prefix+'-fit.json',reference_screenshot=self.data['parts']['screenshot'],
                         reference_viewport='1280x800',comparison_state='Current player has control')
            return dict(implementation_walkthrough={'board':walkthrough},increment_fit={'board':fit})
        design=gate.check(self.root,self.state('design','D-6',[artifact],practice_evidence=records('design')))
        state=dict(role='build',current='E-3.1',scope=['board'],tone_contract=self.contract,practice_evidence=records('increment',design))
        result=tone.check_increment(self.root,state,[artifact],seal=False)
        self.assertEqual(state['current'],'E-3.1')
        self.assertIn(dict(scope='board',requirement='increment_fit'),result)
        record=state['practice_evidence']['implementation_walkthrough']['board']
        data=json.loads((self.root/record['path']).read_text());data.pop('design_review')
        state['practice_evidence']['implementation_walkthrough']['board']=self.put(record['path'],data)
        with self.assertRaisesRegex(ValueError,'artifact reference'):
            tone.check_increment(self.root,state,[artifact],seal=False)

    def test_completion_covers_actual_handover_and_does_not_rewrite_dispatch(self):
        solution=self.solution_review();artifact=self.put('engineering/plan.md','Actual planning delivery')
        state=self.state('build','E-3.1',[artifact],upstream=solution['upstream_state'],upstream_bundle=solution['review_bundle'])
        context=dict(task_id='PLAN',dispatched={key:state[key] for key in ('role','current','scope','tone_contract','upstream','upstream_bundle')},
                     handed_files={artifact['path']:artifact['sha256']},producers={artifact['path']:'maker'},increment_review=True)
        result=gate.check(self.root,state,task_context=context)
        view,frozen=self.frozen(result)
        self.assertEqual(result['from'],'E-3.1');self.assertTrue(result['increment_review'])
        self.assertTrue(gate.check(view,frozen,registry_root=self.root,seal=False)['allowed'])
        hidden=self.put('src/omitted.js','const unreviewed=true');context['handed_files'][hidden['path']]=hidden['sha256']
        with self.assertRaisesRegex(ValueError,'actual task and child handover'):
            gate.check(self.root,state,task_context=context)
        context['handed_files'].pop(hidden['path']);context['dispatched']['scope']=['another-scope']
        with self.assertRaisesRegex(ValueError,'dispatched scope'):
            gate.check(self.root,state,task_context=context)

    def test_real_start_handover_is_a_producer_but_an_unhanded_run_is_not(self):
        artifact=self.put('src/author.js','const version=1')
        fit=self.fit([artifact],mode='independent',producer='author',checker='checker',review_task='CHECK')
        directory=self.root/'management/runtime';directory.mkdir(parents=True)
        with sqlite3.connect(directory/'tasks.sqlite3') as db:
            db.execute('CREATE TABLE pm_records(kind TEXT,id TEXT,data TEXT)');db.execute('CREATE TABLE tasks(id TEXT,data TEXT)')
            for identity in ('author','checker'):
                db.execute('INSERT INTO pm_records VALUES(?,?,?)',('instance',identity,json.dumps(dict(id=identity,active=True))))
            for task in (dict(id='AUTHOR',owner='author',executor='author'),dict(id='CHECK',owner='checker',state='done',handed_output_sha256={fit['path']:fit['sha256']})):
                db.execute('INSERT INTO tasks VALUES(?,?)',(task['id'],json.dumps(task)))
            run=dict(id='START',task_id='AUTHOR',purpose='start',instance='author',state='exited',exit_code=0,handed=True,handover=dict(files={artifact['path']:artifact['sha256']}))
            db.execute('INSERT INTO pm_records VALUES(?,?,?)',('launch','START',json.dumps(run)))
        self.assertTrue(tone.check_fit(self.root,fit['path'],[artifact],self.contract))
        run['handover']['files']={'src/same-bytes-other-path.js':artifact['sha256']}
        with sqlite3.connect(directory/'tasks.sqlite3') as db:
            db.execute('UPDATE pm_records SET data=? WHERE id=?',(json.dumps(run),'START'))
        with self.assertRaisesRegex(ValueError,'exact actual task handover path'):
            tone.check_fit(self.root,fit['path'],[artifact],self.contract)
        run['handover']['files']={artifact['path']:artifact['sha256']}
        with sqlite3.connect(directory/'tasks.sqlite3') as db:
            db.execute('UPDATE pm_records SET data=? WHERE id=?',(json.dumps(run),'START'))
            db.execute('UPDATE tasks SET data=? WHERE id=?',(json.dumps(dict(id='CHECK',owner='checker',state='done',handed_output_sha256={'same-bytes-different-fit.json':fit['sha256']})),'CHECK'))
        with self.assertRaisesRegex(ValueError,'fit path and hash'):
            tone.check_fit(self.root,fit['path'],[artifact],self.contract)
        with sqlite3.connect(directory/'tasks.sqlite3') as db:
            db.execute('UPDATE tasks SET data=? WHERE id=?',(json.dumps(dict(id='CHECK',owner='checker',state='done',handed_output_sha256={fit['path']:fit['sha256']})),'CHECK'))
        context=dict(handed_files={artifact['path']:artifact['sha256']},producers={})
        with self.assertRaisesRegex(ValueError,'exact task handover and actual producer'):
            tone.check_fit(self.root,fit['path'],[artifact],self.contract,task_context=context)
        context['producers'][artifact['path']]='author'
        self.assertTrue(tone.check_fit(self.root,fit['path'],[artifact],self.contract,task_context=context))
        extra=self.put('src/not-handed.js','const unhanded=2')
        partial=self.fit([artifact,extra],record_path='partial-fit.json',mode='independent',producer='author',checker='checker',review_task='CHECK')
        with self.assertRaisesRegex(ValueError,'exact actual task handover path'):
            tone.check_fit(self.root,partial['path'],[artifact,extra],self.contract)
        with sqlite3.connect(directory/'tasks.sqlite3') as db:
            run['handed']=False;db.execute('UPDATE pm_records SET data=? WHERE id=?',(json.dumps(run),'START'))
        with self.assertRaisesRegex(ValueError,'actual task handover'):
            tone.check_fit(self.root,fit['path'],[artifact],self.contract)

    def test_release_execution_requires_its_real_decision_and_prior_completion(self):
        solution=self.solution_review();output=self.put('release/candidate.md','Synthetic release candidate')
        built=gate.check(self.root,self.state('build','E-3.3',[output],upstream=solution['upstream_state'],upstream_bundle=solution['review_bundle']))
        with self.assertRaisesRegex(ValueError,'upstream review record'):
            gate.check(self.root,self.state('release','E-4.3',[output]))
        before=gate.check(self.root,self.state('release','E-4.1',[output],upstream=built['upstream_state'],upstream_bundle=built['review_bundle']))
        decision=gate.check(self.root,self.state('release','E-4.2',[output],upstream=built['upstream_state'],upstream_bundle=built['review_bundle']))
        self.assertTrue(gate.check(self.root,self.state('release','E-4.3',[output],upstream=decision['upstream_state'],upstream_bundle=decision['review_bundle']))['allowed'])

    def asset_comparison(self):
        anchors=[self.put('design/anchor-'+str(i)+'.svg','<svg><text>Actual synthetic anchor '+str(i)+'</text></svg>') for i in range(3)]
        scene=self.put('design/current-scene.html','<main>Actual branch scene'+''.join('<img src="anchor-'+str(i)+'.svg">' for i in range(3))+'</main>')
        page=self.put('design/review.html','<section>Visible layered object contour: achieved<iframe src="preview.html"></iframe><iframe src="current-scene.html"></iframe><img src="anchor-0.svg"></section>')
        comparison=dict(confirmed_features=['Visible layered object contour'],rows=[dict(feature='Visible layered object contour',reference=self.data['parts']['preview'],
            reference_observation='The direction objects have a separate light edge',anchor=anchors[0],anchor_observation='The current object retains a light edge at actual scene scale',
            status='achieved',difference='No material contour difference was observed at this scale')],review_page=page,scene_sample=scene)
        return self.record('asset_anchors',[scene,*anchors,page],anchors=anchors,comparison=comparison)

    def test_d4_requires_actual_structured_comparison_and_current_materials(self):
        import copy
        ref=self.asset_comparison();original=json.loads((self.root/ref['path']).read_text())
        self.assertTrue(tone.check_record(self.root,'asset_anchors','board',ref,self.contract))
        cases=[('missing table',lambda row:row.pop('comparison'),'structured direction comparison'),
               ('only plan',lambda row:row['comparison']['rows'][0].update(anchor_observation='稍后对照'),'not placeholders'),
               ('stale reference',lambda row:row['comparison']['rows'][0]['reference'].update(sha256='0'*64),'stale artifact'),
               ('missed feature',lambda row:row['comparison']['confirmed_features'].append('Second agreed feature'),'every declared confirmed feature'),
               ('unmet',lambda row:row['comparison']['rows'][0].update(status='unmet'),'cannot release the asset family'),
               ('invalid status',lambda row:row['comparison']['rows'][0].update(status='looks fine'),'status must be')]
        for label,change,error in cases:
            with self.subTest(label=label):
                value=copy.deepcopy(original);change(value);changed=self.put('d4-invalid.json',value)
                with self.assertRaisesRegex(ValueError,error):tone.check_record(self.root,'asset_anchors','board',changed,self.contract)
        value=copy.deepcopy(original);value['comparison']['rows'][0].update(status='close',difference='The current edge is thinner; preserve the actual readability review')
        page=self.put('design/close-review.html',(self.root/'design/review.html').read_text().replace('achieved','close'))
        value['comparison']['review_page']=page;value['artifacts'].append(page)
        self.assertTrue(tone.check_record(self.root,'asset_anchors','board',self.put('d4-close.json',value),self.contract))
        page=self.put('design/review.html','Visible layered object contour achieved; Direction preview.html and current-scene.html will be compared')
        value=copy.deepcopy(original);value['comparison']['review_page']=page
        value['artifacts']=[page if ref['path']==page['path'] else ref for ref in value['artifacts']]
        with self.assertRaisesRegex(ValueError,'must embed'):
            tone.check_record(self.root,'asset_anchors','board',self.put('d4-links-only.json',value),self.contract)
        (self.root/original['comparison']['scene_sample']['path']).unlink()
        with self.assertRaisesRegex(ValueError,'missing or unsafe'):
            tone.check_record(self.root,'asset_anchors','board',ref,self.contract)

    def test_d4_completed_gate_hands_over_the_actual_side_by_side_page(self):
        self.contract,self.data=self.direction([self.row(asset_family='yes')])
        anchors=self.asset_comparison();data=json.loads((self.root/anchors['path']).read_text());artifacts=data['artifacts']
        fit=self.fit(artifacts,'asset-fit.json')
        state=self.state('design','D-4',artifacts,practice_evidence={'asset_anchors':{'board':anchors},'asset_fit':{'board':fit}})
        result=gate.check(self.root,state)
        self.assertTrue(result['allowed'])
        _,outputs=gate.framework_outputs(self.root,state,result)
        self.assertIn(data['comparison']['review_page']['path'],outputs)
        self.assertIn(data['comparison']['scene_sample']['path'],outputs)
        view,frozen=self.frozen(result)
        self.assertTrue(gate.check(view,frozen,registry_root=self.root,seal=False)['allowed'])
        data.pop('comparison');state['practice_evidence']['asset_anchors']['board']=self.put('missing-d4-table.json',data)
        with self.assertRaisesRegex(ValueError,'structured direction comparison'):
            gate.check(self.root,state)

    def test_d4_is_content_triggered_and_contract_definition_has_new_version(self):
        registry=json.loads((BASE.parents[1]/'professions/experience-design/profession.json').read_text())
        requirements=tone.practice.stage_requirements(registry)['D-4']
        inactive=tone.practice.active(dict(scopes=[self.row()]),requirements['complete'])
        self.assertNotIn('asset_anchors',inactive.get('board',[]))
        active=tone.practice.active(dict(scopes=[self.row(asset_family='yes')]),requirements['complete'])
        self.assertIn('asset_anchors',active['board'])
        contract=tone.practice.professional_contract(registry)
        definition=next(row['definition'] for row in contract['requirements'] if row['stage']=='D-4' and row['requirement']=='asset_anchors')
        self.assertEqual(definition['version'],5)
        self.assertIn('comparison',definition)

    def test_cross_root_sealing_requires_explicit_read_only_view(self):
        artifact=self.put('design/scope.md','Actual design-only scope')
        state=self.state('design','D-6',[artifact],implementation_handoff=self.put('design/handoff.json',
                         dict(delivery_kind='design_only',basis='No implementation',artifacts=[artifact])))
        result=gate.check(self.root,state);view,frozen=self.frozen(result)
        with self.assertRaisesRegex(ValueError,'use seal=False'):
            gate.check(view,frozen,registry_root=self.root)
        self.assertTrue(gate.check(view,frozen,registry_root=self.root,seal=False)['allowed'])

    def test_same_reply_source_cannot_be_bound_to_a_new_direction(self):
        _,manifest=tone.evidence.verify_bundle(self.root,self.data['confirmation']['review_receipt']);binding=manifest['context']
        binding=dict(binding,direction_sha256='changed')
        with self.assertRaisesRegex(ValueError,'already bound'):
            tone.evidence.review_receipt(self.root,binding)

    def test_references_accept_real_offline_material_and_reject_current_outputs(self):
        self.put('references/external.pdf',b'Synthetic external manual fixture')
        rows=[dict(name='One',source='references/external.pdf',borrows='Object activity',observed='Fixture'),dict(name='Two',source='system:existing-ledger/v2',borrows='Object action',observed='Unobserved')]
        tone.validate_references(self.root,rows,self.data['parts'])
        rows[0]['source']=self.data['parts']['scene']['path']
        with self.assertRaisesRegex(ValueError,'not an external'):
            tone.validate_references(self.root,rows,self.data['parts'])

    def playable(self, artifacts, stage, pending=False, name='play.json'):
        run=self.put(name+'-run.json',dict(status='observed',environment='Synthetic desktop',stage=stage,artifacts=artifacts,
                                         events=[dict(action='Select object',result='Object moves',at_ms=10)]))
        timing=self.put(name+'-timing.json',dict(status='observed',environment='Synthetic desktop',stage=stage,artifacts=artifacts,
                                                measurements=[dict(event='First feedback',result='Visible change',started_ms=0,observed_ms=10)]))
        extra=dict(status='completed',run_evidence=run,timing_evidence=timing,playtest_status='pending' if pending else 'observed')
        if not pending:
            source=self.put(name+'-participant.md','SIMULATED participant tried the object action and described its visible result')
            extra['playtest_evidence']=self.put(name+'-playtest.json',dict(status='observed',environment='Synthetic desktop',artifacts=artifacts,
                sessions=[dict(player='SIMULATED participant',source=source,observations=['Recognized the moved object'])]))
        return self.record('playable_prototype',artifacts,name,**extra)

    def test_prototype_logs_bind_stage_and_version_without_new_e2_human_approval(self):
        artifact=self.put('src/turn.js','const turn=1')
        record=self.playable([artifact],'E-2.2',pending=True)
        tone.check_record(self.root,'playable_prototype','board',record,self.contract,stage='E-2.2')
        with self.assertRaisesRegex(ValueError,'another stage'):
            tone.check_record(self.root,'playable_prototype','board',record,self.contract,stage='E-3.3')
        data=json.loads((self.root/record['path']).read_text());log=json.loads((self.root/data['run_evidence']['path']).read_text())
        log['artifacts']=[self.put('src/old.js','old run version')]
        data['run_evidence']=self.put(data['run_evidence']['path'],log);record=self.put(record['path'],data)
        with self.assertRaisesRegex(ValueError,'actual current artifacts'):
            tone.check_record(self.root,'playable_prototype','board',record,self.contract,stage='E-2.2')
        actual=self.playable([artifact],'E-3.3',name='actual-play.json')
        self.assertTrue(tone.check_record(self.root,'playable_prototype','board',actual,self.contract,stage='E-3.3'))

    def test_walkthrough_requires_structured_state_and_action_evidence(self):
        artifact=self.put('src/board.js','const board=1');observation=self.put('reviews/state.json',dict(state='Player turn',result='HUD retained'))
        record=self.record('implementation_walkthrough',[artifact],preserved_states=[dict(state='Current player',layer='HUD',basis='Needed to decide the next action')],
            design_recheck_states=[dict(state='Current turn',method='Observe the active player',evidence=observation)],
            corrections=[dict(location='Board selection',type='implementation_deviation',destination='Engineering task FIX')])
        self.assertTrue(tone.check_record(self.root,'implementation_walkthrough','board',record,self.contract))
        data=json.loads((self.root/record['path']).read_text());data['preserved_states']='无';record=self.put(record['path'],data)
        with self.assertRaisesRegex(ValueError,'structured walkthrough'):
            tone.check_record(self.root,'implementation_walkthrough','board',record,self.contract)

    def test_successful_draft_persists_a_tool_bound_receipt_and_refreshes_real_digests(self):
        import subprocess,sys
        self.data.pop('confirmation');self.data['parts']['samples']['sha256']='stale'
        self.put(tone.DEFAULT_PATH,'```tone-contract\n'+json.dumps(self.data)+'\n```')
        process=subprocess.run([sys.executable,str(BASE/'tone_contract.py'),'--project',str(self.root),'--draft','--refresh-draft'],capture_output=True,text=True)
        self.assertEqual(process.returncode,0,process.stdout+process.stderr)
        result=json.loads(process.stdout);receipt=json.loads(tone.verify_ref(self.root,result['tool_receipt']).read_text())
        self.assertEqual(receipt['format'],'direction-tool-receipt/1')
        self.assertEqual(result['draft'],tone.evidence.ref(self.root,tone.DEFAULT_PATH))
        self.assertEqual(receipt['tool']['sha256'],hashlib.sha256((BASE/'tone_contract.py').read_bytes()).hexdigest())
        self.assertTrue(receipt['allowed']);self.assertEqual(receipt['delivery'],result['delivery'])
        # Tool provenance is install metadata, never a workspace file to recursively collect.
        closure=tone.evidence.closure(self.root,[result['tool_receipt']])
        self.assertNotIn('matrix/base/tools/tone_contract.py',closure)

    def test_incomplete_human_draft_returns_reference_but_never_delivery(self):
        import subprocess,sys
        self.data.pop('confirmation');self.data['parts'].pop('screenshot')
        self.data['parts']['manual_review']=dict(self.put('manual.md','Actual synthetic displayed viewport, awaiting the user reply'),version='1')
        self.data['capture_unavailable']='No capture capability in this fixture'
        self.put(tone.DEFAULT_PATH,'```tone-contract\n'+json.dumps(self.data)+'\n```')
        process=subprocess.run([sys.executable,str(BASE/'tone_contract.py'),'--project',str(self.root),'--draft'],capture_output=True,text=True)
        result=json.loads(process.stdout);self.assertNotEqual(process.returncode,0)
        self.assertIn('direction_reference',result);self.assertNotIn('delivery',result)
        self.assertEqual(result['draft'],tone.evidence.ref(self.root,tone.DEFAULT_PATH))
        self.assertFalse((self.root/(tone.DEFAULT_PATH+'.delivery.json')).exists())

    def test_q2_playtest_binds_the_actual_tested_build_not_just_a_report(self):
        solution=self.solution_review();code=self.put('src/tested.js','const tested=1')
        completed=gate.check(self.root,self.state('build','E-3.3',[code],upstream=solution['upstream_state'],upstream_bundle=solution['review_bundle']))
        report=self.put('quality/report.md','Synthetic observed acceptance results')
        ref=self.playable([code,report],'Q-2',name='quality-play.json');data=json.loads((self.root/ref['path']).read_text())
        data['tested_stage']=dict(bundle=completed['review_bundle'],state_path=completed['upstream_state']);ref=self.put(ref['path'],data)
        self.assertTrue(tone.check_record(self.root,'playable_prototype','board',ref,self.contract,stage='Q-2'))
        ref=self.playable([report],'Q-2',name='report-only-play.json');data=json.loads((self.root/ref['path']).read_text())
        data['tested_stage']=dict(bundle=completed['review_bundle'],state_path=completed['upstream_state']);ref=self.put(ref['path'],data)
        with self.assertRaisesRegex(ValueError,'E-3.3 tested artifacts'):
            tone.check_record(self.root,'playable_prototype','board',ref,self.contract,stage='Q-2')

    def test_self_written_human_receipt_does_not_create_a_pm_attention_event(self):
        artifact=self.put('src/object.js','const object=1')
        display=self.put('human/display.md','Synthetic rendered current view')
        response=self.put('human/reply.md','Synthetic user saw the rendered current view')
        binding=dict(format='matrix-review-binding/1',request_id='attention-never-recorded',scope=['board'],actor='user',
            display=display,response=dict(response,message_sha256=tone.evidence.digest('Synthetic user saw the rendered current view')),
            person='synthetic-user',quote='Synthetic user saw the rendered current view',outcome='approved',artifacts=[artifact])
        receipt=tone.evidence.review_receipt(self.root,binding)
        directory=self.root/'management/runtime';directory.mkdir(parents=True)
        with sqlite3.connect(directory/'tasks.sqlite3') as db:
            db.execute('CREATE TABLE pm_records(kind TEXT,id TEXT,data TEXT)');db.execute('CREATE TABLE tasks(id TEXT,data TEXT)')
        with self.assertRaisesRegex(ValueError,'actual answered PM human_attention'):
            tone.evidence.verify_human_receipt(self.root,receipt,artifacts=[artifact])

    def test_human_receipt_reads_its_current_trusted_transaction_only(self):
        artifact=self.put('transaction/view.html','<main>Current display</main>')
        display=self.put('transaction/display.md','Synthetic actually displayed viewport')
        reply=self.put('transaction/response.md','Synthetic complete same-transaction reply')
        binding=dict(format='matrix-review-binding/1',request_id='ATTENTION',scope=['board'],actor='user',
                     display=display,response=dict(reply,message_sha256=tone.evidence.digest('Synthetic complete same-transaction reply')),
                     person='synthetic-user',quote='Synthetic complete same-transaction reply',outcome='approved',artifacts=[artifact])
        receipt=tone.evidence.review_receipt(self.root,binding)
        shown=tone.evidence.seal_bundle(self.root,[display],dict(kind='display'),follow_refs=False)
        answered=tone.evidence.seal_bundle(self.root,[reply],dict(kind='response'),follow_refs=False)
        directory=self.root/'management/runtime';directory.mkdir(parents=True)
        db=sqlite3.connect(directory/'tasks.sqlite3');self.addCleanup(db.close)
        db.execute('CREATE TABLE pm_records(kind TEXT,id TEXT,data TEXT)');db.execute('CREATE TABLE tasks(id TEXT,data TEXT)');db.commit()
        attention=dict(id='ATTENTION',seconds=1,response_message=binding['quote'],context=dict(scope=['board']),
                       display=display['path'],display_bundle=shown,response_bundle=answered,review_receipts=[receipt])
        db.execute('INSERT INTO pm_records VALUES(?,?,?)',('human_attention','ATTENTION',json.dumps(attention)))
        with self.assertRaisesRegex(ValueError,'actual answered PM human_attention'):
            tone.evidence.verify_human_receipt(self.root,receipt,artifacts=[artifact])
        self.assertEqual(tone.evidence.verify_human_receipt(self.root,receipt,artifacts=[artifact],authority_db=db),binding)
        manual=self.put('transaction/viewport.md','Synthetic current visible objects')
        fit=self.fit([artifact],'transaction/fit.json',mode='human',producer='maker',checker='synthetic-user')
        fit_data=json.loads((self.root/fit['path']).read_text());fit_data.pop('screenshot');fit_data.pop('capture_binding')
        fit_data.update(manual_review=manual,capture_unavailable='Synthetic host capture unavailable')
        self.put(fit['path'],fit_data)
        self.assertTrue(tone.check_fit(self.root,fit['path'],[artifact],self.contract,human_review_receipt=receipt,authority_db=db))
        with sqlite3.connect(':memory:') as other:
            with self.assertRaisesRegex(ValueError,'this project PM database'):
                tone.evidence.verify_human_receipt(self.root,receipt,authority_db=other)
        db.rollback()

    def test_incomplete_sealing_cannot_publish_a_successful_stage_receipt(self):
        from unittest.mock import patch
        from contextlib import nullcontext
        artifact=self.put('design/spec.md','Actual design-only document')
        handoff=self.put('design/handoff.json',dict(delivery_kind='design_only',basis='No implementation',artifacts=[artifact]))
        with patch.object(tone.evidence,'track_reads',return_value=nullcontext({})):
            with self.assertRaisesRegex(ValueError,'missing or unsafe'):
                gate.check(self.root,self.state('design','D-6',[artifact],implementation_handoff=handoff))
        self.assertFalse(list((self.root/'management/stage-receipts').glob('*.json')))

    def test_handcrafted_new_bundle_cannot_rebind_an_existing_response(self):
        _,original=tone.evidence.verify_bundle(self.root,self.data['confirmation']['review_receipt'])
        self.data['tone']='A different agreed tone'
        expected=tone.direction_binding(tone.DEFAULT_PATH,self.data)['direction_sha256']
        binding=dict(original['context'],direction_sha256=expected)
        receipt=tone.evidence.seal_bundle(self.root,[binding['display'],binding['response']],binding,follow_refs=False)
        self.data['confirmation'].update(direction_sha256=expected,review_receipt=receipt)
        self.put(tone.DEFAULT_PATH,'```tone-contract\n'+json.dumps(self.data)+'\n```')
        with self.assertRaisesRegex(ValueError,'rebound'):
            tone.validate(self.root,tone.DEFAULT_PATH)


if __name__=='__main__':unittest.main()
