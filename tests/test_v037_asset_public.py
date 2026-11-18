"""Synthetic D-4 acceptance through package CLIs and public PM operations only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import longchain_fixture as h
from pm_game_fixture import Team, OUT_D


def cli(root,tool,*args):
    run=subprocess.run([sys.executable,'-B',str(h.KIT/'matrix/base/tools'/tool),'--project',str(root),*args],text=True,capture_output=True)
    if run.returncode:raise ValueError(run.stdout+run.stderr)
    return json.loads(run.stdout)


def materials(root,C,D,status='achieved',png=False):
    anchors=[h.put(root,'design/assets/a'+str(i)+'.svg','<svg><text>SIM anchor '+str(i)+'</text></svg>') for i in range(3)]
    scene=h.put(root,'design/assets/scene.html','<main>SIM current anchored scene</main>')
    direction=D['parts'].get('screenshot') or D['parts']['preview']
    tag='img' if direction['path'].endswith('.png') else 'iframe'
    sources=[scene,*anchors]
    sample=h.put(root,'design/assets/scene.png',h.shotpng()) if png else scene
    binding=h.capture(root,sources,sample) if png else None
    sample_tag='img' if png else 'iframe'
    page=h.put(root,'design/assets/review.html','<main>Visible contour '+status+'<'+tag+' src="'+os.path.relpath(direction['path'],'design/assets')+'"></'+tag+'><'+sample_tag+' src="'+Path(sample['path']).name+'"></'+sample_tag+'></main>')
    arts=[*sources,*([sample] if png else []),page]
    rec=h.record(root,'asset_anchors',C,arts,'design/assets/record.json')
    data=json.loads((root/rec['path']).read_text())
    data.update(anchors=anchors,comparison=dict(confirmed_features=['Visible contour'],scene_sample=sample,review_page=page,
        rows=[dict(feature='Visible contour',reference=direction,reference_observation='SIM observed separated edge',anchor=sample,
                   anchor_observation='SIM current separate edge',status=status,difference='SIM documented boundary difference')]))
    if png:data['comparison'].update(capture_binding=binding,viewport='1280x800')
    rec=h.put(root,rec['path'],data)
    result=cli(root,'tone_contract.py','--asset-comparison',rec['path'])
    wrapper=h.put(root,'design/representative.html','<main>SIM representative page<iframe src="assets/review.html"></iframe></main>')
    return arts,rec,result,wrapper


class SingleAsset(unittest.TestCase):
    def test_png_sample_closes_d4_and_d5_without_treating_capture_receipt_as_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);C,D=h.direction(root,[h.feature_scope(asset_family='yes')])
            arts,record,result,wrapper=materials(root,C,D,png=True)
            data=json.loads((root/record['path']).read_text())
            capture_path=root/data['comparison']['capture_binding']['receipt']['path']
            self.assertNotIn(str(capture_path.relative_to(root)),[a['path'] for a in arts])
            fit=h.fit(root,C,arts,'design/png-fit.json',shot=h.put(root,'design/fit.png',h.shotpng()),direction_data=D)
            state=h.human_stage(root,h.stage(root,'design','D-4','D-5',C,arts,
                dict(asset_anchors={'board':record},asset_fit={'board':fit}),
                asset_comparison_receipts={'board':result['asset_comparison_receipt']}),'PNG-D4')
            request=json.loads((root/state['request']).read_text());reply=json.loads((root/state['response']).read_text())
            request.update(display_evidence=wrapper['path'],display_sha256=wrapper['sha256']);reply['display_sha256']=wrapper['sha256']
            h.put(root,state['request'],request);h.put(root,state['response'],reply)
            path=h.put(root,'png-d4.json',state)
            self.assertTrue(cli(root,'stage_gate.py','--state',str(root/path['path']))['allowed'])
            next_state=h.stage(root,'design','D-5','D-6',C,[h.put(root,'design/complete.md','SIM complete PNG design')])
            next_path=h.put(root,'png-d5.json',next_state)
            self.assertTrue(cli(root,'stage_gate.py','--state',str(root/next_path['path']))['allowed'])
            # Evidence is still hash-bound even though it is not an approved artifact.
            capture_path.write_text(capture_path.read_text()+' ')
            with self.assertRaises(ValueError):
                cli(root,'tone_contract.py','--asset-comparison',record['path'])

    def test_wrapper_cannot_approve_a_page_or_embedded_material_omitted_from_artifacts(self):
        for missing in ('review.html','scene.html','a0.svg'):
            with self.subTest(material=missing),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);C,D=h.direction(root,[h.feature_scope(asset_family='yes')])
                arts,record,result,wrapper=materials(root,C,D)
                shown=[a for a in arts if not a['path'].endswith('/'+missing)]
                fit=h.fit(root,C,arts,'design/fit.json',shot=h.put(root,'design/fit.png',h.shotpng()),direction_data=D)
                state=h.human_stage(root,h.stage(root,'design','D-4','D-5',C,shown,
                    dict(asset_anchors={'board':record},asset_fit={'board':fit}),
                    asset_comparison_receipts={'board':result['asset_comparison_receipt']}),'missing')
                request=json.loads((root/state['request']).read_text());reply=json.loads((root/state['response']).read_text())
                request.update(display_evidence=wrapper['path'],display_sha256=wrapper['sha256']);reply['display_sha256']=wrapper['sha256']
                h.put(root,state['request'],request);h.put(root,state['response'],reply)
                path=h.put(root,'missing.json',state)
                with self.assertRaisesRegex(ValueError,'artifacts must bind'):
                    cli(root,'stage_gate.py','--state',str(root/path['path']))

    def test_refreshed_receipt_cannot_approve_post_reply_page_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);C,D=h.direction(root,[h.feature_scope(asset_family='yes')])
            arts,record,result,wrapper=materials(root,C,D)
            approved=[a for a in arts if a['path']!='design/assets/review.html']
            page=root/'design/assets/review.html';completed=page.read_text()
            page.write_text('<main>SIM pending observations</main>')
            state=h.human_stage(root,h.stage(root,'design','D-4','D-5',C,approved),'old-display')
            request=json.loads((root/state['request']).read_text());reply=json.loads((root/state['response']).read_text())
            request.update(display_evidence=wrapper['path'],display_sha256=wrapper['sha256']);reply['display_sha256']=wrapper['sha256']
            h.put(root,state['request'],request);h.put(root,state['response'],reply)
            page.write_text(completed)
            result=cli(root,'tone_contract.py','--asset-comparison',record['path'])
            fit=h.fit(root,C,arts,'design/fit.json',shot=h.put(root,'design/fit.png',h.shotpng()),direction_data=D)
            state.update(practice_evidence=dict(asset_anchors={'board':record},asset_fit={'board':fit}),
                         asset_comparison_receipts={'board':result['asset_comparison_receipt']})
            path=h.put(root,'changed-after-reply.json',state)
            with self.assertRaisesRegex(ValueError,'artifacts must bind'):
                cli(root,'stage_gate.py','--state',str(root/path['path']))

    def test_natural_evidence_folder_is_sealed_as_user_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);C,_=h.direction(root,[h.feature_scope()])
            artifact=h.put(root,'management/evidence/e22/observed.md','SIM actual evidence in a natural project folder')
            state=h.stage(root,'design','D-3','D-4',C,[artifact])
            path=h.put(root,'natural.json',state)
            self.assertTrue(cli(root,'stage_gate.py','--state',str(root/path['path']))['allowed'])

    def test_public_d4_wrapper_then_d5_and_unmet_not_releasable(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            C,D=h.direction(root,[h.feature_scope(asset_family='yes')])
            arts,record,result,wrapper=materials(root,C,D)
            fit=h.fit(root,C,arts,'design/fit.json',shot=h.put(root,'design/fit.png',h.shotpng()),direction_data=D)
            state=h.human_stage(root,h.stage(root,'design','D-4','D-5',C,arts,
                dict(asset_anchors={'board':record},asset_fit={'board':fit}),asset_comparison_receipts={'board':result['asset_comparison_receipt']}),'D4')
            request=json.loads((root/state['request']).read_text());reply=json.loads((root/state['response']).read_text())
            request.update(display_evidence=wrapper['path'],display_sha256=wrapper['sha256']);reply['display_sha256']=wrapper['sha256']
            h.put(root,state['request'],request);h.put(root,state['response'],reply)
            path=h.put(root,'d4.json',state)
            self.assertTrue(cli(root,'stage_gate.py','--state',str(root/path['path']))['allowed'])
            next_state=h.stage(root,'design','D-5','D-6',C,[h.put(root,'design/complete.md','SIM complete design')])
            path=h.put(root,'d5.json',next_state)
            self.assertTrue(cli(root,'stage_gate.py','--state',str(root/path['path']))['allowed'])
            arts,record,result,wrapper=materials(root,C,D,'unmet')
            self.assertFalse(result['release_ready'])
            fit=h.fit(root,C,arts,'design/unmet-fit.json',shot=h.put(root,'design/unmet-fit.png',h.shotpng()),direction_data=D)
            state=h.human_stage(root,h.stage(root,'design','D-4','D-5',C,arts,
                dict(asset_anchors={'board':record},asset_fit={'board':fit}),asset_comparison_receipts={'board':result['asset_comparison_receipt']}),'D4-unmet')
            path=h.put(root,'d4-unmet.json',state)
            with self.assertRaisesRegex(ValueError,'cannot release'):
                cli(root,'stage_gate.py','--state',str(root/path['path']))


class TeamAsset(Team,unittest.TestCase):
    rows=[h.feature_scope(asset_family='yes')]

    def test_p1_and_d1_can_consume_distinct_replies_with_identical_words(self):
        entry=dict(role='design',current='D-1',scope=['board'],tone_contract=self.C)
        completion='design/d1-state.json'
        self.create('D1-same-option',project_level=False,owner='experience-design-001',executor='experience-design-001',checker='quality-engineering-003',
                    inputs=[self.tone.DEFAULT_PATH],admitted_inputs=[],dependencies=['DIR'],outputs=OUT_D,
                    practice_stage=entry,practice_completion=completion)
        self.start('D1-same-option')
        artifact=self.put('design/d1.md','SIM current direction contribution')
        contribution=h.record(self.root,'direction_contribution',self.C,[artifact],'design/d1-contribution.json')
        quote=self.D['confirmation']['quote']
        state=h.human_stage(self.root,self.state('design','D-1',[artifact],dict(direction_contribution={'board':contribution})),
                            'D1-same-option',reply=quote)
        request=json.loads((self.root/state['request']).read_text());response=json.loads((self.root/state['response']).read_text())
        self.put(completion,state)
        self.call('human_attention',id='D1-same-option',task_id='D1-same-option',kind='confirmation',display=request['display_evidence'],
                  scope=['board'],inputs=[artifact['path']])
        with self.assertRaisesRegex(ValueError,'already bound'):
            self.call('human_attention',id='D1-same-option',response=self.D['confirmation']['source'])
        self.call('human_attention',id='D1-same-option',response=response['source'])
        response['review_receipt']=self.call('stage_confirmation',state=completion,attention_id='D1-same-option',person='SIM-owner')['review_receipt']
        self.put(state['response'],response)
        self.finish('D1-same-option',[completion,contribution['path'],artifact['path'],state['response']])
        self.assertEqual('done',self.t('D1-same-option')['state'])

    def test_d4_cannot_consume_another_stage_or_unstaged_tasks_attention(self):
        arts,record,result,wrapper=materials(self.root,self.C,self.D)
        for stage in ('D-3',None):
            tid='other-'+(stage or 'none')
            entry=dict(role='design',current=stage,scope=['board'],tone_contract=self.C) if stage else None
            self.create(tid,project_level=False,owner='experience-design-001',executor='experience-design-001',checker='quality-engineering-003',
                        inputs=[self.tone.DEFAULT_PATH],admitted_inputs=[],dependencies=['DIR'],outputs=OUT_D,
                        **({'practice_stage':entry} if entry else {}))
            state=h.human_stage(self.root,self.state('design','D-4',arts,
                dict(asset_anchors={'board':record}),asset_comparison_receipts={'board':result['asset_comparison_receipt']}),tid)
            request=json.loads((self.root/state['request']).read_text());reply=json.loads((self.root/state['response']).read_text())
            request.update(display_evidence=wrapper['path'],display_sha256=wrapper['sha256']);reply['display_sha256']=wrapper['sha256']
            self.put(state['request'],request);self.put(state['response'],reply)
            path=self.put('design/'+tid+'-state.json',state)['path']
            self.call('human_attention',id=tid,task_id=tid,kind='confirmation',display=wrapper['path'],scope=['board'],inputs=[a['path'] for a in arts])
            self.call('human_attention',id=tid,response=reply['source'])
            with self.subTest(task_stage=stage),self.assertRaisesRegex(ValueError,'assigned D-4 task'):
                self.call('stage_confirmation',state=path,attention_id=tid,person='SIM-owner')

    def test_d4_dispatch_rejects_different_practice_scope(self):
        entry=dict(role='design',current='D-4',scope=['board'],practice_scope=['other'],tone_contract=self.C)
        with self.assertRaisesRegex(ValueError,'practice_scope must match'):
            self.create('bad-scope',project_level=False,owner='experience-design-001',executor='experience-design-001',checker='quality-engineering-003',
                        inputs=[self.tone.DEFAULT_PATH],admitted_inputs=[],dependencies=['DIR'],outputs=OUT_D,practice_stage=entry)

    def test_team_stage_review_locks_embedded_page_before_requesting_approval(self):
        entry=dict(role='design',current='D-4',scope=['board'],tone_contract=self.C)
        self.create('D4-omit',project_level=False,owner='experience-design-001',executor='experience-design-001',checker='quality-engineering-003',
                    inputs=[self.tone.DEFAULT_PATH],admitted_inputs=[],dependencies=['DIR'],outputs=OUT_D,practice_stage=entry)
        arts,record,result,wrapper=materials(self.root,self.C,self.D)
        state=self.state('design','D-4',[a for a in arts if a['path']!='design/assets/review.html'],
            dict(asset_anchors={'board':record}),asset_comparison_receipts={'board':result['asset_comparison_receipt']})
        path=self.put('design/omit-state.json',state)['path']
        with self.assertRaisesRegex(ValueError,'artifacts must bind'):
            self.call('human_attention',id='omit',task_id='D4-omit',kind='confirmation',review_purpose='stage_review',stage_state=path,
                      display=wrapper['path'],scope=['board'],inputs=[a['path'] for a in state['artifacts']])

    def test_public_team_closes_d4_with_embedded_page(self):
        self.close_d4_with_embedded_page()

    def test_public_team_closes_d4_with_png_sample(self):
        self.close_d4_with_embedded_page(png=True)

    def close_d4_with_embedded_page(self,png=False):
        entry=dict(role='design',current='D-4',scope=['board'],tone_contract=self.C)
        completion='design/d4-state.json'
        self.create('D4',project_level=False,owner='experience-design-001',executor='experience-design-001',checker='quality-engineering-003',
                    inputs=[self.tone.DEFAULT_PATH],admitted_inputs=[],dependencies=['DIR'],practice_stage=entry,practice_completion=completion,outputs=OUT_D)
        self.start('D4')
        question=self.put('design/question.md','SIM choose asset family batch')
        for kind in ('clarification','correction','confirmation'):
            self.call('human_attention',id='normal-'+kind,task_id='D4',kind=kind,display=question['path'],scope=['board'])
        with self.assertRaisesRegex(ValueError,'stage_state'):
            self.call('human_attention',id='anchor-missing',task_id='D4',kind='confirmation',review_purpose='asset_anchors',display=question['path'],scope=['board'])
        arts,record,result,wrapper=materials(self.root,self.C,self.D,'unmet',png=png)
        self.put(completion,dict(entry,artifacts=arts,practice_evidence={'asset_anchors':{'board':record}},asset_comparison_receipts={'board':result['asset_comparison_receipt']}))
        self.call('human_attention',id='unmet-anchor',task_id='D4',kind='confirmation',review_purpose='asset_anchors',stage_state=completion,
                  display=wrapper['path'],scope=['board'])
        self.assertFalse(result['release_ready'])
        arts,record,result,wrapper=materials(self.root,self.C,self.D,png=png)
        fit=self.fit_child('D4','FIT-D4','quality-engineering-002','reviews/d4-fit.json',
            lambda:h.fit(self.root,self.C,arts,'reviews/d4-fit.json',shot=self.put('reviews/d4.png',h.shotpng()),direction_data=self.D,
                         mode='independent',checker='quality-engineering-002',producer='experience-design-001',review_task='FIT-D4'))
        state=self.state('design','D-4',arts,dict(asset_anchors={'board':record},asset_fit={'board':fit}),
                         asset_comparison_receipts={'board':result['asset_comparison_receipt']})
        self.put(completion,state)
        self.call('human_attention',id='anchor',task_id='D4',kind='confirmation',review_purpose='asset_anchors',stage_state=completion,
                  display=wrapper['path'],scope=['board'],inputs=[a['path'] for a in arts])
        digest=self.gate.artifact_digest(self.root,arts);quote='SIM actual stage review B approval'
        reply=self.put('management/reviews/D4-reply.md',quote)
        self.call('human_attention',id='B',task_id='D4',kind='confirmation',review_purpose='stage_review',stage_state=completion,
                  display=wrapper['path'],scope=['board'],inputs=[a['path'] for a in arts])
        self.call('human_attention',id='B',response=reply['path'])
        answer=self.mutate('human_review','D4','PM',outcome='approved',person='SIM-owner',attention_id='B',
                           presented_ref=wrapper['path'],source=reply['path'],quote=quote,scope=['board'])
        state['request']=self.put('management/reviews/B-request.json',dict(request_id='B',role='design',stage='D-4',scope=['board'],
            artifact_sha256=digest,display_evidence=wrapper['path'],display_sha256=wrapper['sha256']))['path']
        state['response']=self.put('management/reviews/B-response.json',dict(request_id='B',scope=['board'],artifact_sha256=digest,
            actor='user',choice='confirm',source=reply['path'],quote=quote,display_sha256=wrapper['sha256'],message_sha256=self.ev.digest(quote),
            review_receipt=answer['task']['human_review']['review_receipt']))['path']
        self.put(completion,state)
        self.finish('D4',[completion,record['path'],*[a['path'] for a in arts]])
        self.assertEqual('done',self.t('D4')['state'])
