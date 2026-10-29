"""Isolated mechanism tests. All actors, execution, checks and approvals are SIMULATED."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

SOURCE = Path(os.environ.get('MATRIX_TEST_KIT', str(Path(__file__).resolve().parents[1] / 'src')))
spec = importlib.util.spec_from_file_location('pm_integrity_test_runtime', SOURCE / '.agents/skills/project-management-agent/scripts/pm_tasks.py')
pm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm)


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='pm-integrity-simulated-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.seq = 0
        self.call('init', 'PM', config=dict(project='SIMULATED', pm_actor='PM', authorization='SIMULATED only',
                  frontdoor_thread='SIMULATED', max_slots=8))

    def call(self, op, actor='DEV-1', **kw):
        self.seq += 1
        return pm.execute(self.root, dict(op=op, actor=actor, event_id='SIM-'+str(self.seq), **kw))

    def t(self, tid):
        return next(t for t in pm.execute(self.root, {'op': 'status'})['tasks'] if t['id'] == tid)

    def create(self, tid, parent=None, actor=None, **kw):
        data = dict(id=tid, parent=parent, title='SIM '+tid, owner='DEV-1', checker='QA-1',
                    goal='SIMULATED delivery', inputs=['SIM v1'], outputs=['SIM output'], criteria=['SIM correct'],
                    next_action='SIM next', executor='DEV-1')
        data.update(kw)
        return self.call('create', actor or ('PM' if parent is None or data.get('project_level') else self.t(parent)['owner']), task=data)

    def mutate(self, op, tid, actor=None, **kw):
        return self.call(op, actor or self.t(tid)['owner'], task_id=tid, expected_revision=self.t(tid)['revision'], **kw)

    def prepare(self, tid, **kw):
        self.mutate('update', tid, changes=dict(evidence=['SIMULATED work evidence'], **kw), reason='SIMULATED work')
        self.mutate('review', tid, self.t(tid)['checker'], outcome='passed', criteria_checked=self.t(tid)['criteria'], evidence=['SIMULATED checker; not real verification'])
        if self.t(tid)['human_required']:
            self.mutate('human_review', tid, 'PM', outcome='approved', presented_ref='SIM shown', source='SIM reply', quote='SIMULATED not real human approval', scope='SIM scope')

    def close(self, tid):
        return self.mutate('transition', tid, self.t(tid)['manager'], state='done', reason='SIMULATED close')

    def complete(self, tid):
        self.prepare(tid)
        return self.close(tid)

    def scope(self, members=('A', 'B'), complete=True, exits=('production',)):
        if not any(t['id'] == 'ALL' for t in pm.execute(self.root, {'op': 'status'})['tasks']):
            self.create('ALL', expanded=False)
        (self.root/'scope.json').write_text(json.dumps(list(members)))
        return self.call('register_scope', 'PM', id='S', root_task='ALL', source={'path':'scope.json'}, required_exits=list(exits), known_complete=complete)

    def bind(self, member, tid, exit_name='production', **kw):
        return self.call('bind_delivery', 'PM', id='S', expected_revision=self.record('scope', 'S')['revision'], member_id=member, exit=exit_name, task_id=tid, work_revision=self.t(tid)['work_revision'], **kw)

    def record(self, kind, rid):
        db = pm.connect(self.root)
        try:
            return pm.integrity.records(db, kind)[rid]
        finally:
            db.close()

    def change(self, affected=('WORK',), parties=('DEV-1',), scopes=()):
        self.create('ANALYZE', owner='PROD-1')
        (self.root/'oral.txt').write_text('SIMULATED: change this requirement')
        return self.call('record_change', 'PM', id='C', type='modify', source='oral.txt', quote='SIMULATED requirement change',
                         affected_tasks=list(affected), scope_ids=list(scopes), analysis_task='ANALYZE', participants=list(parties))

    def assess(self, dispositions, commands=(), actor='DEV-1', decision='impacted'):
        return self.call('assess_change', actor, id='C', expected_revision=self.record('change','C')['revision'],
                         assessment=dict(decision=decision, reason='SIMULATED professional assessment', dispositions=dispositions, commands=list(commands)))

    def apply(self, **kw):
        return self.call('apply_change_plan', 'PM', id='C', expected_revision=self.record('change','C')['revision'], **kw)

    def test_missing_object_blocks_parent_even_when_registered_children_complete(self):
        self.scope()
        self.create('A', 'ALL'); self.complete('A'); self.bind('A','A'); self.prepare('ALL')
        with self.assertRaisesRegex(pm.TaskError, 'delivery_unmapped'):
            self.close('ALL')
        issues = pm.execute(self.root, dict(op='audit', task_ids=['ALL']))['issues']
        self.assertEqual(['B'], [i['member_id'] for i in issues])
        self.create('B','ALL'); self.complete('B'); self.bind('B','B'); self.prepare('ALL'); self.close('ALL')

    def test_cancellation_does_not_remove_delivery_obligation(self):
        self.scope(('A',)); self.create('A','ALL')
        self.mutate('transition','A','DEV-1',state='cancelled',reason='SIM cancel')
        self.bind('A','A'); self.prepare('ALL')
        with self.assertRaisesRegex(pm.TaskError,'delivery_not_current'):
            self.close('ALL')

    def test_unknown_scope_cannot_be_reported_complete(self):
        self.scope((), complete=False); self.prepare('ALL')
        with self.assertRaisesRegex(pm.TaskError,'scope_unknown'):
            self.close('ALL')

    def test_changed_collection_needs_a_recorded_authorized_amendment(self):
        self.scope(('A',)); (self.root/'scope.json').write_text('["A", "B"]')
        with self.assertRaisesRegex(pm.TaskError,'recorded change'):
            self.call('register_scope','PM',id='S',expected_revision=1,root_task='ALL',source={'path':'scope.json'},required_exits=['production'],known_complete=True)

    def test_direct_artifact_edit_makes_done_stale_without_rewriting_history(self):
        self.create('WORK'); f=self.root/'work.txt'; f.write_text('SIM v1')
        self.prepare('WORK',artifact_digests={'work.txt':hashlib.sha256(f.read_bytes()).hexdigest()}); self.close('WORK')
        self.assertFalse(self.t('WORK')['needs_recheck']); f.write_text('SIM v2')
        self.assertTrue(self.t('WORK')['needs_recheck']); self.assertEqual('done',self.t('WORK')['state'])

    def test_no_fake_human_exit_and_no_self_signed_independent_qa(self):
        self.scope(('A',), exits=('qa','human')); self.create('A','ALL',checker='DEV-1'); self.complete('A')
        self.bind('A','A','qa'); self.bind('A','A','human')
        codes={i['code'] for i in pm.execute(self.root,dict(op='audit',task_ids=['ALL']))['issues']}
        self.assertEqual({'human_gate_missing','independent_check_missing'},codes)

    def test_pending_change_blocks_only_related_dispatch(self):
        self.create('WORK'); self.create('OTHER'); self.change()
        self.assertFalse(self.t('WORK')['ready'])
        self.assertTrue(self.t('OTHER')['ready'])
        with self.assertRaisesRegex(pm.TaskError,'change_plan_pending'):
            self.mutate('transition','WORK',state='running',reason='SIM start',execution_receipt='SIM receipt')
        self.mutate('transition','OTHER',state='running',reason='SIM start',execution_receipt='SIM receipt')

    def test_owner_assessment_applies_plan_and_retries_are_idempotent(self):
        self.create('WORK'); self.change()
        c=dict(op='update',actor='DEV-1',task_id='WORK',expected_revision=1,changes={'inputs':['SIM v2']},reason='SIM change',scope_authorization='SIM source')
        self.assess([{'action':'update','task_id':'WORK'}],[c])
        cmd=dict(op='apply_change_plan',actor='PM',event_id='SIM-PLAN',id='C',expected_revision=self.record('change','C')['revision'])
        result=pm.execute(self.root,cmd); self.assertEqual(result,pm.execute(self.root,cmd))
        self.assertEqual(['SIM v2'],self.t('WORK')['inputs'])
        self.mutate('transition','WORK',state='running',reason='SIM start',execution_receipt='SIM receipt')

    def test_partial_assessments_cannot_activate_a_plan(self):
        self.create('WORK'); self.change(parties=('DEV-1','DES-1'))
        self.assess([{'action':'keep','task_id':'WORK'}])
        with self.assertRaisesRegex(pm.TaskError,'incomplete'):
            self.apply()

    def test_owner_cannot_assess_another_owners_task(self):
        self.create('WORK',owner='OTHER'); self.change(parties=('DEV-1',))
        with self.assertRaisesRegex(pm.TaskError,'affected owner'):
            self.assess([{'action':'keep','task_id':'WORK'}])

    def test_failed_plan_rolls_back_all_task_changes_and_events(self):
        self.create('WORK'); self.change()
        c=dict(op='update',actor='DEV-1',task_id='WORK',expected_revision=1,changes={'inputs':['SIM v2']},reason='SIM change',scope_authorization='SIM')
        self.assess([{'action':'update','task_id':'WORK'}],[c,dict(c,expected_revision=999)])
        before=pm.execute(self.root,{'op':'status'})
        with self.assertRaisesRegex(pm.TaskError,'stale revision'):
            self.apply()
        after=pm.execute(self.root,{'op':'status'})
        self.assertEqual(before['tasks'],after['tasks']); self.assertEqual(before['revision'],after['revision'])
        self.assertEqual('assessing',self.record('change','C')['state'])

    def test_pm_cannot_impersonate_owner_in_batch(self):
        self.create('WORK'); self.change(); self.assess([{'action':'keep','task_id':'WORK'}])
        with self.assertRaisesRegex(pm.TaskError,'impersonate'):
            self.apply(pm_commands=[dict(op='update',actor='DEV-1')])

    def test_completed_task_keeps_history_when_new_rework_is_planned(self):
        self.create('WORK'); self.complete('WORK'); revision=self.t('WORK')['work_revision']; self.change()
        self.assess([{'action':'keep','task_id':'WORK'},{'action':'rework','task_id':'FIX','replaces':'WORK'}])
        task=dict(id='FIX',parent=None,title='SIM fix',owner='DEV-1',checker='QA-1',goal='SIM v2',inputs=['v2'],outputs=['new'],criteria=['ok'],next_action='fix',executor='DEV-1')
        self.apply(pm_commands=[dict(op='create',actor='PM',task=task)])
        old=self.t('WORK'); self.assertEqual('done',old['state']); self.assertEqual(revision,old['work_revision']); self.assertTrue(old['needs_recheck'])
        with self.assertRaisesRegex(pm.TaskError,'incomplete|analysis task is not complete'):
            self.call('close_change','PM',id='C',expected_revision=self.record('change','C')['revision'])

    def test_query_counts_project_work_once_and_groups_instances_by_role(self):
        for iid in ['DEV-1','DEV-2']:
            self.call('register_instance','PM',id=iid,instance=dict(role='engineering-build',endpoint='SIM-'+iid,write_roots=['code/'+iid]))
        self.create('ONE'); self.create('TWO',owner='DEV-2',executor='DEV-2'); self.create('CHILD','ONE')
        q=pm.execute(self.root,dict(op='query',role='engineering-build'))
        self.assertEqual(2,q['counts']['total']); self.assertEqual({'ONE','TWO'},{t['id'] for t in q['tasks']})
        q=pm.execute(self.root,dict(op='query',level='children',parent='ONE'))
        self.assertEqual(['CHILD'],[t['id'] for t in q['tasks']])
        q=pm.execute(self.root,dict(op='query',instance='DEV-2'))
        self.assertEqual(['TWO'],[t['id'] for t in q['tasks']])

    def test_explicit_project_task_under_stage_is_managed_by_pm(self):
        self.create('STAGE',kind='stage',owner='DES-1')
        self.create('WORK','STAGE',project_level=True)
        self.assertEqual('PM',self.t('WORK')['manager'])
        self.assertEqual(['WORK'],[t['id'] for t in pm.execute(self.root,{'op':'query'})['tasks']])

    def test_parallel_instances_cannot_write_same_registered_range(self):
        for iid in ['DEV-1','DEV-2']:
            self.call('register_instance','PM',id=iid,instance=dict(role='engineering-build',endpoint='SIM-'+iid,write_roots=['code/common']))
        self.create('ONE'); self.create('TWO',owner='DEV-2',executor='DEV-2')
        self.mutate('transition','ONE',state='running',reason='SIM',execution_receipt='SIM')
        with self.assertRaisesRegex(pm.TaskError,'instance_or_write_busy'):
            self.mutate('transition','TWO',state='running',reason='SIM',execution_receipt='SIM')

    def test_live_executor_cannot_be_silently_swapped(self):
        self.create('WORK'); self.mutate('transition','WORK',state='running',reason='SIM',execution_receipt='SIM')
        with self.assertRaisesRegex(pm.TaskError,'stop current executor'):
            self.mutate('update','WORK',changes={'executor':'DEV-2'},reason='SIM replacement')

    def test_interruption_returns_resume_candidate_without_starting_agent(self):
        self.create('WORK'); self.create('URGENT')
        self.mutate('transition','WORK',state='running',reason='SIM',execution_receipt='SIM')
        self.call('pause_task',id='P',task_id='WORK',task_revision=self.t('WORK')['revision'],checkpoint='SIM v1 point',remaining=['SIM rest'],resume_after='URGENT',resume_when='urgent verified',reason='SIM interruption',stop_evidence='SIM stopped')
        self.complete('URGENT')
        a=pm.execute(self.root,dict(op='audit',task_ids=['WORK']))
        self.assertTrue(a['resume_candidates'][0]['ready_to_review']); self.assertEqual('blocked',self.t('WORK')['state'])
        self.call('resume_task',id='P',expected_revision=1,task_revision=self.t('WORK')['revision'],reason='SIM resume')
        self.assertEqual('planned',self.t('WORK')['state'])

    def test_legacy_tasks_are_not_given_inferred_collection_obligations(self):
        self.create('LEGACY'); self.complete('LEGACY')
        self.assertFalse(self.t('LEGACY')['needs_recheck'])

    def test_replacement_input_inherits_unresolved_scope_and_participants(self):
        self.create('WORK'); self.change(parties=('DEV-1','DES-1'))
        (self.root/'second.txt').write_text('SIMULATED revised requirement')
        self.call('record_change','PM',id='C2',type='modify',source='second.txt',quote='SIM second',analysis_task='ANALYZE',participants=['PROD-1'],affected_tasks=[],scope_ids=[],supersedes='C',supersession_authorization='SIM explicit replacement')
        current=self.record('change','C2')
        self.assertEqual('superseded',self.record('change','C')['state'])
        self.assertIn('WORK',current['affected_tasks'])
        self.assertEqual({'DEV-1','DES-1','PROD-1'},set(current['participants']))
        with self.assertRaisesRegex(pm.TaskError,'change_plan_pending'):
            self.mutate('transition','WORK',state='running',reason='SIM',execution_receipt='SIM')

    def test_deferral_without_trigger_is_rejected(self):
        self.create('WORK'); self.change()
        with self.assertRaisesRegex(pm.TaskError,'trigger'):
            self.assess([{'action':'defer','task_id':'WORK'}])

    def test_unassessed_command_cannot_be_smuggled_into_plan(self):
        self.create('WORK'); self.create('OTHER'); self.change()
        c=dict(op='update',actor='DEV-1',task_id='OTHER',expected_revision=1,changes={'next_action':'SIM changed'},reason='SIM')
        self.assess([{'action':'keep','task_id':'WORK'}],[c])
        with self.assertRaisesRegex(pm.TaskError,'no assessed disposition'):
            self.apply()

    def test_old_done_parent_with_newly_registered_gap_is_not_current_complete(self):
        self.create('ALL'); self.complete('ALL'); self.scope(('MISSING',))
        self.assertEqual('done',self.t('ALL')['state'])
        self.assertTrue(self.t('ALL')['needs_recheck'])

    def test_new_requirement_can_create_several_professional_project_tasks(self):
        self.change(affected=(),parties=('PROD-1','DEV-1'))
        self.assess([{'action':'new','task_id':'PRODUCT'}],actor='PROD-1')
        self.assess([{'action':'new','task_id':'BUILD'}])
        commands=[]
        for tid,owner in [('PRODUCT','PROD-1'),('BUILD','DEV-1')]:
            task=dict(id=tid,parent=None,title='SIM '+tid,owner=owner,checker='QA-1',goal='SIM requirement',inputs=['SIM source'],outputs=['SIM output'],criteria=['SIM acceptance'],next_action='SIM next',executor=owner)
            commands.append(dict(op='create',actor='PM',task=task))
        self.apply(pm_commands=commands)
        self.assertEqual({'PRODUCT','BUILD'},{d['task_id'] for d in self.record('change','C')['dispositions']})

    def test_cancelling_exclusive_task_preserves_shared_work(self):
        self.create('WORK'); self.create('SHARED'); self.change(affected=('WORK','SHARED'))
        cancel=dict(op='transition',actor='PM',task_id='WORK',expected_revision=1,state='cancelled',reason='SIM explicit removal')
        self.assess([{'action':'cancel','task_id':'WORK'},{'action':'keep','task_id':'SHARED'}])
        self.apply(pm_commands=[cancel])
        self.assertEqual('deprecated',self.t('WORK')['state']); self.assertEqual('planned',self.t('SHARED')['state'])

    def test_change_numbers_are_automatic_unique_and_retry_stable(self):
        self.create('ANALYZE', owner='PROD-1')
        (self.root/'oral.txt').write_text('SIMULATED removal')
        command = dict(op='record_change', actor='PM', event_id='AUTO-1', type='remove',
                       title='附件上传', source='oral.txt', quote='SIM remove upload',
                       affected_tasks=[], participants=['DEV-1'], analysis_task='ANALYZE')
        first = pm.execute(self.root, command)
        self.assertEqual(first, pm.execute(self.root, command))
        second = pm.execute(self.root, dict(command, event_id='AUTO-2'))
        self.assertEqual('CHG-000001',first['record']['id'])
        self.assertEqual('CHG-000002',second['record']['change_no'])
        ledger = pm.execute(self.root, {'op':'changes'})
        self.assertEqual([1,2],[c['sequence'] for c in ledger['changes']])
        self.assertEqual(['附件上传','附件上传'],[c['title'] for c in ledger['changes']])
        self.assertTrue(all(c['created_at'] and c['source_sha256'] for c in ledger['changes']))
        path = self.root/'management/runtime/tasks.sqlite3'
        before = path.read_bytes()
        self.assertEqual(1,len(pm.execute(self.root, {'op':'changes','id':first['record']['change_no']})['changes']))
        self.assertEqual(before,path.read_bytes())

    def test_change_id_collision_cannot_overwrite_or_consume_a_number(self):
        self.change(affected=())
        with self.assertRaisesRegex(pm.TaskError,'new input requires a new change id'):
            self.call('record_change','PM',id='C',expected_revision=1)
        self.create('ANOTHER', owner='PROD-1')
        second = self.call('record_change','PM',type='add',source='oral.txt',quote='SIM new',
                          analysis_task='ANOTHER',participants=['DEV-1'])['record']
        self.assertEqual('CHG-000002',second['change_no'])

    def test_concurrent_change_registration_allocates_distinct_numbers(self):
        self.create('ANALYZE', owner='PROD-1')
        (self.root/'oral.txt').write_text('SIMULATED concurrent requirement inputs')
        def register(n):
            return pm.execute(self.root, dict(op='record_change',actor='PM',event_id='SIM-PARALLEL-'+str(n),
                              type='add',source='oral.txt',quote='SIM input '+str(n),
                              analysis_task='ANALYZE',participants=['DEV-1']))['record']['change_no']
        with ThreadPoolExecutor(max_workers=2) as pool:
            numbers=list(pool.map(register,range(2)))
        self.assertEqual({'CHG-000001','CHG-000002'},set(numbers))

    def deprecate_work(self, **command_fields):
        self.change()
        self.assess([{'action':'cancel','task_id':'WORK'}])
        cancel = dict(op='transition',actor='PM',task_id='WORK',expected_revision=self.t('WORK')['revision'],
                      state='cancelled',reason='SIM assessed removal',**command_fields)
        return self.apply(pm_commands=[cancel])

    def test_changed_task_is_deprecated_with_numbered_remark_and_visible_ledger(self):
        self.create('WORK')
        self.deprecate_work()
        task = self.t('WORK')
        expected = '受 （CHG-000001） SIMULATED requirement change 需求调整变更'
        self.assertEqual('deprecated',task['state'])
        self.assertEqual('已弃用',task['state_label'])
        self.assertEqual(expected,task['reason'])
        self.assertEqual(expected,task['deprecation']['remark'])
        self.assertEqual('C',task['deprecation']['change_id'])
        result = pm.execute(self.root, {'op':'query'})
        self.assertEqual(1,result['counts']['deprecated'])
        self.assertEqual(0,result['counts']['cancelled'])
        self.assertEqual(1,result['counts']['remaining'])  # analysis only
        row = pm.execute(self.root, {'op':'changes'})['changes'][0]
        self.assertEqual('planned',row['state'])
        self.assertEqual('deprecated',next(t for t in row['tasks'] if t['id']=='WORK')['state'])
        pm.render(self.root)
        view = (self.root/'management/views/changes.md').read_text()
        self.assertIn('CHG-000001',view)
        self.assertIn('已弃用',view)
        self.assertIn(expected,(self.root/'management/views/tasks/WORK.md').read_text())

    def test_deprecation_requires_assessed_change_and_is_not_ordinary_cancellation(self):
        self.create('WORK')
        with self.assertRaisesRegex(pm.TaskError,'assessed change'):
            self.mutate('transition','WORK','PM',state='deprecated',reason='SIM no basis')
        self.mutate('transition','WORK','PM',state='cancelled',reason='SIM ordinary cancellation')
        self.assertEqual('cancelled',self.t('WORK')['state'])
        self.assertNotIn('deprecation',self.t('WORK'))

    def test_unassessed_change_cannot_be_bypassed_by_plain_cancel(self):
        self.create('WORK'); self.change()
        with self.assertRaisesRegex(pm.TaskError,'assessed change'):
            self.mutate('transition','WORK','PM',state='cancelled',reason='SIM bypass attempt')
        self.assertEqual('planned',self.t('WORK')['state'])

    def test_completed_task_can_be_deprecated_without_erasing_done_history(self):
        self.create('WORK'); self.complete('WORK')
        old_review = self.t('WORK')['review']
        self.deprecate_work()
        self.assertEqual('deprecated',self.t('WORK')['state'])
        self.assertEqual(old_review,self.t('WORK')['review'])
        history = pm.execute(self.root, {'op':'events','limit':1000})['events']
        self.assertTrue(any(e['task_id']=='WORK' and (e['after_data'] or {}).get('state')=='done' for e in history))

    def test_reopened_retirement_cannot_be_used_to_close_the_old_change(self):
        self.create('WORK'); self.deprecate_work(); self.complete('ANALYZE')
        self.mutate('transition','WORK','PM',state='planned',reason='SIM explicit reopening')
        with self.assertRaisesRegex(pm.TaskError,'retirement changed'):
            self.call('close_change','PM',id='C',expected_revision=self.record('change','C')['revision'])

    def test_running_task_deprecation_still_requires_actual_stop_evidence(self):
        self.create('WORK')
        self.mutate('transition','WORK',state='running',reason='SIM start',execution_receipt='SIM start')
        with self.assertRaisesRegex(pm.TaskError,'stop/yield evidence'):
            self.deprecate_work()
        self.assertEqual('running',self.t('WORK')['state'])
        self.assertEqual('assessing',self.record('change','C')['state'])
        cancel = dict(op='transition',actor='PM',task_id='WORK',expected_revision=self.t('WORK')['revision'],
                      state='deprecated',reason='SIM removal',stop_evidence='SIM actual stop')
        self.apply(pm_commands=[cancel])
        self.assertEqual('deprecated',self.t('WORK')['state'])

    def test_deprecation_does_not_remove_required_delivery_or_fulfil_dependency(self):
        self.scope(('A',)); self.create('WORK','ALL',project_level=True); self.create('WAIT',dependencies=['WORK'])
        self.deprecate_work()
        self.bind('A','WORK')
        problems=pm.execute(self.root, {'op':'audit','task_ids':['ALL']})['issues']
        self.assertTrue(any(p['code']=='delivery_not_current' for p in problems))
        self.assertFalse(self.t('WAIT')['ready'])

    def test_disjoint_same_role_instances_can_start_independently(self):
        for iid in ['DEV-1','DEV-2']:
            self.call('register_instance','PM',id=iid,instance=dict(role='engineering-build',endpoint='SIM-'+iid,write_roots=['code/'+iid]))
        self.create('ONE'); self.create('TWO',owner='DEV-2',executor='DEV-2')
        for tid in ['ONE','TWO']:
            self.mutate('transition',tid,state='running',reason='SIM start',execution_receipt='SIM receipt')
        self.assertEqual(2,len([t for t in pm.execute(self.root,{'op':'query','role':'engineering-build'})['tasks'] if t['state']=='running']))

    def test_read_audit_does_not_migrate_legacy_database(self):
        path=self.root/'management/runtime/tasks.sqlite3'
        c=sqlite3.connect(path);c.execute('DROP TABLE pm_records');c.commit();c.close()
        before=hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual([],pm.execute(self.root,{'op':'audit'})['issues'])
        self.assertEqual(0,pm.execute(self.root,{'op':'query'})['counts']['total'])
        self.assertEqual(before,hashlib.sha256(path.read_bytes()).hexdigest())

    def test_read_query_does_not_create_an_uninitialized_database(self):
        with tempfile.TemporaryDirectory(prefix='pm-read-only-simulation-') as d:
            root=Path(d).resolve()
            with self.assertRaisesRegex(pm.TaskError,'database missing'):
                pm.execute(root,{'op':'query'})
            self.assertFalse((root/'management').exists())

    def test_pending_child_change_blocks_parent_close_but_not_sibling_work(self):
        self.create('PARENT');self.create('WORK','PARENT');self.create('SIBLING','PARENT')
        self.complete('WORK');self.complete('SIBLING');self.prepare('PARENT');self.change()
        with self.assertRaisesRegex(pm.TaskError,'change_plan_pending'):
            self.close('PARENT')
        self.create('INDEPENDENT','PARENT')
        self.mutate('transition','INDEPENDENT',state='running',reason='SIM',execution_receipt='SIM')

    def test_pending_change_to_external_bound_delivery_blocks_collection_close(self):
        self.scope(('A',));self.create('WORK');self.complete('WORK');self.bind('A','WORK');self.prepare('ALL');self.change()
        with self.assertRaisesRegex(pm.TaskError,'change_plan_pending'):
            self.close('ALL')


if __name__ == '__main__':
    unittest.main()
