#!/usr/bin/env python3
"""Topic ledger tests. People, quotes and evidence here are SIMULATED, never real approval.
Run: python3 -m unittest discover -s <this directory> -p test_topics.py -v
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from kit import KIT
spec = importlib.util.spec_from_file_location('coordination_topics', KIT / 'matrix/orchestration/tools/coordination.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
CoordinationError, execute = module.CoordinationError, module.execute

HEADER = {'id', 'initiator', 'item', 'kind', 'state', 'effect', 'plan_impact', 'view'}
LANDING = {'path': 'decisions/T1.md', 'version': 'v1'}


class TopicTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for path, text in {'skills/p.md': 'product', 'skills/e.md': 'engineering', 'skills/d.md': 'design',
                           'skills/q.md': 'quality', 'skills/m.md': 'project management',
                           'product/rules.md': 'SIMULATED rule v1', 'decisions/T1.md': 'SIMULATED conclusion record',
                           'notes/excerpt.md': 'SIMULATED excerpt'}.items():
            (self.root / path).parent.mkdir(parents=True, exist_ok=True)
            (self.root / path).write_text(text)
        execute(self.root, {'op': 'init', 'config': {'protocol': 'professional-collaboration/0.1', 'authorization': 'SIMULATED TEST ONLY',
                                                     'frontdoor_id': 'test-topics'}})
        # product decides, engineering initiates, design takes part, qa owns an affected deliverable, pm only plans.
        for name, skill in [('product', 'skills/p.md'), ('engineering', 'skills/e.md'), ('design', 'skills/d.md'),
                            ('qa', 'skills/q.md'), ('pm', 'skills/m.md')]:
            self.register(name, skill, [name])

    def register(self, name, skill, roots):
        execute(self.root, {'op': 'register', 'actor': 'coordinator', 'role': {'id': name, 'skill': skill, 'write_roots': roots, 'endpoint': None}})

    def runop(self, op, actor, tid='T1', **kwargs):
        return execute(self.root, {'op': op, 'actor': actor, 'id': tid, **kwargs})

    def open_topic(self, tid='T1', actor='engineering', **extra):
        topic = {'id': tid, 'kind': 'discuss', 'cause': {'item': 'REQ-7', 'version': 'v1'}, 'purpose': 'SIMULATED: agree on export retention',
                 'participants': [{'id': 'engineering', 'tier': 'internal'}, {'id': 'design', 'tier': 'internal'},
                                  {'id': 'vendor-security', 'tier': 'external'}],
                 'decider': 'product', 'visibility': {'affected_owners': ['qa'], 'confidential': False}}
        topic.update(extra)
        return execute(self.root, {'op': 'topic_open', 'actor': actor, 'topic': topic})

    def note(self, actor, summary='SIMULATED point', tid='T1', **extra):
        return self.runop('topic_note', actor, tid, note={'summary': summary, **extra})

    def conclude(self, actor='product', tid='T1', **extra):
        conclusion = {'text': 'SIMULATED: retain exports for 30 days', 'effect': 'binding', 'applies_to': ['REQ-7'],
                      'lands_in': LANDING, 'plan_impact': False}
        conclusion.update(extra)
        return self.runop('topic_conclude', actor, tid, conclusion=conclusion)

    def adopt(self, actor, tid='T1', **adoption):
        return self.runop('topic_adopt', actor, tid, adoption=adoption)

    def escalate(self, actor, to='human', summary='SIMULATED: needs a person', tid='T1'):
        return self.runop('topic_escalate', actor, tid, to=to, summary=summary)

    def close(self, actor='engineering', tid='T1'):
        return self.runop('topic_close', actor, tid)

    def view(self, actor, tid='T1'):
        return next(t for t in execute(self.root, {'op': 'topics', 'actor': actor})['topics'] if t['id'] == tid)

    def request(self, rid, source, topic='T1'):
        payload = {'id': rid, 'source': source, 'target': 'product', 'topic': topic, 'question': 'SIMULATED question',
                   'expected_output': 'Sourced answer', 'authorization': 'SIMULATED', 'sources': ['product/rules.md']}
        return execute(self.root, {'op': 'request', 'actor': source, 'request': payload})

    def events(self):
        con = sqlite3.connect(str(self.root / 'management/runtime/coordination.sqlite3'))
        try:
            return [kind for (kind,) in con.execute('SELECT kind FROM events ORDER BY seq') if kind.startswith('topic_')]
        finally:
            con.close()

    def test_open_records_initiator_rounds_and_defaults(self):
        topic = self.open_topic()
        self.assertEqual((topic['state'], topic['round'], topic['initiator'], topic['max_rounds'], topic['deadline']),
                         ('open', 0, 'engineering', 3, None))
        self.assertEqual(self.open_topic('T2', kind='notify', max_rounds=10, deadline='2999-12-31')['max_rounds'], 10)

    def test_open_rejects_invalid_kind_cause_rounds_deadline_and_fields(self):
        for extra in [dict(kind='chat'), dict(kind=None), dict(cause={'item': 'REQ-7'}), dict(cause='REQ-7'), dict(purpose=''),
                      dict(max_rounds=0), dict(max_rounds=11), dict(max_rounds='3'), dict(deadline='30/11/2026'),
                      dict(deadline='2026-02-30'), dict(transcript='SIMULATED whole conversation')]:
            with self.subTest(extra=extra), self.assertRaises(CoordinationError):
                self.open_topic(**extra)
        self.assertEqual(execute(self.root, {'op': 'topics', 'actor': 'pm'}), {'topics': []})

    def test_open_checks_participants_initiator_and_decider(self):
        inner = lambda *ids: [{'id': i, 'tier': 'internal'} for i in ids]
        cases = {'initiator missing': dict(participants=inner('design', 'product')),
                 'initiator external': dict(participants=[{'id': 'engineering', 'tier': 'external'}] + inner('design')),
                 'internal not registered': dict(participants=inner('engineering', 'ghost')),
                 'duplicate': dict(participants=inner('engineering', 'design') + [{'id': 'design', 'tier': 'external'}]),
                 'unknown tier': dict(participants=inner('engineering') + [{'id': 'design', 'tier': 'guest'}]),
                 'nobody else': dict(participants=inner('engineering')),
                 'decider not registered': dict(decider='ghost'), 'decider missing': dict(decider=None),
                 'human without id': dict(decider='human:'),
                 'owner not registered': dict(visibility={'affected_owners': ['ghost'], 'confidential': False}),
                 'confidential unset': dict(visibility={'affected_owners': ['qa']})}
        for name, extra in cases.items():
            with self.subTest(name), self.assertRaises(CoordinationError):
                self.open_topic(**extra)
        with self.assertRaises(CoordinationError):
            self.open_topic(actor='coordinator')
        topic = self.open_topic(participants=inner('engineering') + [{'id': 'any free label', 'tier': 'external'}], decider='human:alice')
        self.assertEqual((topic['participants'][1]['id'], topic['decider']), ('any free label', 'human:alice'))

    def test_open_is_idempotent_and_rejects_changed_content(self):
        first = self.open_topic()
        self.assertEqual(first, self.open_topic())
        with self.assertRaises(CoordinationError):
            self.open_topic(purpose='SIMULATED: a different purpose')
        with self.assertRaises(CoordinationError):
            self.open_topic(actor='design')  # same content from another initiator
        self.assertEqual(self.view('engineering')['purpose'], first['purpose'])

    def test_initiator_notes_open_rounds_up_to_the_limit(self):
        self.open_topic(max_rounds=2)
        with self.assertRaises(CoordinationError):
            self.note('design', 'Reply before any round')
        self.assertEqual(self.note('engineering', 'Round 1 question')['round'], 1)
        self.assertEqual(self.note('design', 'Round 1 reply')['round'], 1)
        self.assertEqual(self.note('design', 'Round 1 second reply')['round'], 1)
        self.assertEqual(self.note('engineering', 'Round 2 question')['round'], 2)
        self.note('design', 'Round 2 reply')
        with self.assertRaisesRegex(CoordinationError, 'concluded or escalated'):
            self.note('engineering', 'Round 3 question')
        self.assertEqual([n['round'] for n in self.view('engineering')['notes']], [1, 1, 1, 2, 2])
        self.assertEqual(self.escalate('engineering')['state'], 'escalated')

    def test_deadline_passed_rejects_notes_but_not_conclusion(self):
        self.open_topic(deadline='2000-01-01')
        for actor in ['engineering', 'design']:
            with self.subTest(actor=actor), self.assertRaisesRegex(CoordinationError, 'concluded or escalated'):
                self.note(actor)
        self.assertEqual(self.conclude()['state'], 'concluded')
        self.open_topic('T2', deadline='2999-12-31')
        self.assertEqual(self.note('engineering', tid='T2')['round'], 1)

    def test_only_internal_participants_post_notes(self):
        self.open_topic()
        self.note('engineering', 'Round 1 question')
        for actor in ['product', 'qa', 'pm', 'coordinator', 'vendor-security']:  # decider, owner, PM, external label
            with self.subTest(actor=actor), self.assertRaisesRegex(CoordinationError, 'only internal participants'):
                self.note(actor)
        self.assertEqual(len(self.view('engineering')['notes']), 1)

    def test_notes_keep_a_short_summary_and_pinned_references(self):
        self.open_topic()
        for extra in [dict(summary='x' * 501), dict(summary=' '), dict(transcript=['SIMULATED whole conversation']),
                      dict(references='notes/excerpt.md'), dict(references=[{'path': 'notes/excerpt.md', 'sha256': '0' * 64}]),
                      dict(references=[{'path': 'notes/excerpt.md', 'text': 'SIMULATED pasted text'}]),
                      dict(references=[{'path': '../outside.md'}]), dict(references=[{'path': 'notes/missing.md'}])]:
            with self.subTest(extra=extra), self.assertRaises(CoordinationError):
                self.note('engineering', **extra)
        excerpt, rules = (hashlib.sha256((self.root / p).read_bytes()).hexdigest() for p in ['notes/excerpt.md', 'product/rules.md'])
        topic = self.note('engineering', 'x' * 500, references=[{'path': 'notes/excerpt.md'}, {'path': 'product/rules.md', 'sha256': rules}])
        self.assertEqual(topic['round'], 1)  # the rejected notes left nothing behind
        self.assertEqual(topic['notes'][0]['references'], [{'path': 'notes/excerpt.md', 'sha256': excerpt},
                                                           {'path': 'product/rules.md', 'sha256': rules}])

    def test_note_retry_is_idempotent_and_keeps_the_round(self):
        self.open_topic(max_rounds=1)
        first = self.note('engineering', 'Question', id='N1')
        self.assertEqual(first, self.note('engineering', 'Question', id='N1'))
        for actor, summary in [('engineering', 'Changed question'), ('design', 'Question')]:
            with self.subTest(actor=actor), self.assertRaises(CoordinationError):
                self.note(actor, summary, id='N1')
        topic = self.view('engineering')
        self.assertEqual((topic['round'], len(topic['notes'])), (1, 1))

    def test_notes_only_while_open(self):
        self.open_topic()
        self.note('engineering')
        self.escalate('engineering')
        with self.assertRaises(CoordinationError):
            self.note('design')
        self.open_topic('T2')
        self.conclude(tid='T2')
        with self.assertRaises(CoordinationError):
            self.note('engineering', tid='T2')

    def test_conclusion_by_decider_with_effect_items_and_landing(self):
        self.open_topic()
        for actor in ['engineering', 'design', 'coordinator']:
            with self.subTest(actor=actor), self.assertRaises(CoordinationError):
                self.conclude(actor)
        for extra in [dict(effect='final'), dict(text=''), dict(applies_to=[]), dict(applies_to='REQ-7'),
                      dict(lands_in={'path': 'decisions/missing.md', 'version': 'v1'}), dict(lands_in={'path': 'decisions/T1.md'}),
                      dict(lands_in={'path': '../escape.md', 'version': 'v1'}), dict(plan_impact='no'),
                      dict(promote={'id': 'K1', 'text': 'SIMULATED'}), dict(evidence='SIMULATED whole thread')]:
            with self.subTest(extra=extra), self.assertRaises(CoordinationError):
                self.conclude(**extra)
        promote = {'id': 'K1', 'text': 'SIMULATED: exports are kept 30 days', 'scope': 'all exports'}
        topic = self.conclude(promote=promote, plan_impact=True)
        self.assertEqual((topic['state'], topic['conclusion']['by'], topic['conclusion']['promote']), ('concluded', 'product', promote))

    def test_conclusion_is_idempotent_and_final(self):
        self.open_topic()
        first = self.conclude()
        self.assertEqual(first, self.conclude())
        with self.assertRaisesRegex(CoordinationError, 'already concluded'):
            self.conclude(effect='advice')

    def test_human_decision_is_recorded_by_initiator_with_quote(self):
        self.open_topic(decider='human:alice')
        for actor, extra in [('engineering', {}), ('design', dict(quote='SIMULATED: keep 30 days')),
                             ('human:alice', dict(quote='SIMULATED: keep 30 days'))]:
            with self.subTest(actor=actor), self.assertRaises(CoordinationError):
                self.conclude(actor, **extra)
        topic = self.conclude('engineering', quote='SIMULATED: keep 30 days')
        self.assertEqual((topic['conclusion']['by'], topic['conclusion']['quote']), ('engineering', 'SIMULATED: keep 30 days'))
        self.assertEqual(self.view('human:alice')['view'], 'full')

    def test_registry_without_binding_types_limits_role_to_advice(self):
        professions = self.root / 'matrix/professions'
        professions.mkdir(parents=True)
        for role, skill, binding in [('desk', 'matrix-front-desk', []), ('product-lead', 'matrix-product', ['SIMULATED confirmed rules'])]:
            (professions / skill).mkdir()
            (professions / skill / 'profession.json').write_text(json.dumps(
                {'id': skill, 'skills': [skill], 'decisions': {'own': ['SIMULATED'], 'escalate': ['SIMULATED'], 'binding': binding}}))
            (self.root / '.agents/skills' / skill).mkdir(parents=True)
            (self.root / '.agents/skills' / skill / 'SKILL.md').write_text(skill)
            self.register(role, '.agents/skills/' + skill + '/SKILL.md', [role])
        self.open_topic('T1', decider='desk')
        with self.assertRaisesRegex(CoordinationError, 'registry'):
            self.conclude('desk')
        self.assertEqual(self.conclude('desk', effect='advice')['conclusion']['effect'], 'advice')
        self.open_topic('T2', decider='product-lead')
        self.assertEqual(self.conclude('product-lead', 'T2')['conclusion']['effect'], 'binding')
        self.open_topic('T3')  # product's skill is in no registry
        self.assertEqual(self.conclude(tid='T3')['conclusion']['effect'], 'binding')
        # A person's decision recorded by a role is not limited by that role's registry.
        self.open_topic('T4', actor='desk', decider='human:alice',
                        participants=[{'id': 'desk', 'tier': 'internal'}, {'id': 'engineering', 'tier': 'internal'}])
        self.assertEqual(self.conclude('desk', 'T4', quote='SIMULATED: this binds')['conclusion']['effect'], 'binding')

    def test_binding_is_satisfied_or_risk_accepted_by_a_person(self):
        self.open_topic(visibility={'affected_owners': ['qa', 'design'], 'confidential': False})
        with self.assertRaises(CoordinationError):
            self.adopt('qa', outcome='satisfied', how='Before any conclusion')
        self.conclude()
        for actor, record in [('engineering', dict(outcome='satisfied', how='Not an affected owner')),
                              ('qa', dict(outcome='declined', reason='Binding cannot be declined')),
                              ('qa', dict(outcome='satisfied')), ('qa', dict(outcome='risk_accepted', person='alice')),
                              ('qa', dict(outcome='risk_accepted', quote='SIMULATED: accepted')), ('qa', dict(outcome='ignored')),
                              ('qa', dict(outcome='satisfied', how='SIMULATED', transcript='SIMULATED'))]:
            with self.subTest(actor=actor, record=record), self.assertRaises(CoordinationError):
                self.adopt(actor, **record)
        self.adopt('qa', outcome='satisfied', how='SIMULATED: tests now expect 30 days')
        accepted = dict(outcome='risk_accepted', person='alice', quote='SIMULATED: I accept the remaining gap')
        topic = self.adopt('design', **accepted)
        self.assertEqual(set(topic['adoptions']), {'qa', 'design'})
        self.assertEqual(topic, self.adopt('design', **accepted))
        with self.assertRaisesRegex(CoordinationError, 'already recorded'):
            self.adopt('design', outcome='satisfied', how='Changed my mind')

    def test_advice_may_be_declined_with_a_reason(self):
        self.open_topic()
        self.conclude(effect='advice')
        for record in [dict(outcome='declined'), dict(outcome='risk_accepted', person='alice', quote='SIMULATED')]:
            with self.subTest(record=record), self.assertRaises(CoordinationError):
                self.adopt('qa', **record)
        topic = self.adopt('qa', outcome='declined', reason='SIMULATED: conflicts with the confirmed test plan')
        self.assertEqual(topic['adoptions']['qa']['outcome'], 'declined')
        self.assertEqual(self.close()['state'], 'closed')

    def test_decision_and_disagreement_need_no_adoption(self):
        for tid, effect in [('T1', 'decision'), ('T2', 'disagreement')]:
            self.open_topic(tid)
            self.conclude(tid=tid, effect=effect)
            with self.subTest(effect=effect), self.assertRaises(CoordinationError):
                self.adopt('qa', tid, outcome='satisfied', how='Nothing to adopt')
            self.assertEqual(self.close(tid=tid)['state'], 'closed')

    def test_escalation_by_initiator_or_decider_can_still_be_concluded(self):
        self.open_topic()
        for actor, to, summary in [('design', 'human', 'Participant only'), ('qa', 'human', 'Owner only'),
                                   ('engineering', 'nobody', 'Unknown target'), ('engineering', 'human', '')]:
            with self.subTest(actor=actor, to=to), self.assertRaises(CoordinationError):
                self.escalate(actor, to, summary)
        topic = self.escalate('product', 'owner', 'SIMULATED: the export owner must decide')
        self.assertEqual((topic['state'], topic['escalations'][0]['by']), ('escalated', 'product'))
        self.assertEqual(topic, self.escalate('product', 'owner', 'SIMULATED: the export owner must decide'))
        self.assertEqual(len(self.escalate('engineering', 'human', 'SIMULATED: the owner lacks authority')['escalations']), 2)
        self.assertEqual(self.conclude(effect='decision')['state'], 'concluded')

    def test_escalated_topic_closes_with_its_escalation(self):
        self.open_topic()
        with self.assertRaisesRegex(CoordinationError, 'conclude or escalate'):
            self.close()
        self.escalate('engineering', 'change', 'SIMULATED: schedule impact; PM registers a change')
        with self.assertRaises(CoordinationError):
            self.close('design')
        topic = self.close()
        self.assertEqual((topic['state'], topic['conclusion'], topic['escalations'][0]['to']), ('closed', None, 'change'))
        for action in [self.conclude, lambda: self.escalate('engineering', 'human', 'SIMULATED: again')]:
            with self.assertRaises(CoordinationError):
                action()

    def test_close_waits_for_every_affected_owner(self):
        self.open_topic(visibility={'affected_owners': ['qa', 'design'], 'confidential': False})
        self.conclude()
        self.adopt('qa', outcome='satisfied', how='SIMULATED: tests updated')
        with self.assertRaisesRegex(CoordinationError, 'design'):
            self.close()
        self.adopt('design', outcome='satisfied', how='SIMULATED: screens updated')
        with self.assertRaises(CoordinationError):
            self.close('product')  # the decider does not close
        closed = self.close()
        self.assertEqual(closed['state'], 'closed')
        self.assertEqual(closed, self.close())
        with self.assertRaises(CoordinationError):
            self.note('engineering')

    def test_pm_and_outsiders_see_only_headers(self):
        self.open_topic()
        self.note('engineering', 'SIMULATED detail for participants only')
        for actor in ['engineering', 'design', 'product']:
            with self.subTest(actor=actor):
                full = self.view(actor)
                self.assertEqual((full['view'], full['notes'][0]['summary']), ('full', 'SIMULATED detail for participants only'))
        for actor in ['coordinator', 'pm', 'vendor-security', 'qa']:  # qa is an affected owner, but nothing is concluded yet
            with self.subTest(actor=actor):
                head = self.view(actor)
                self.assertEqual(set(head), HEADER)
                self.assertEqual([head[k] for k in ['view', 'initiator', 'item', 'kind', 'state', 'effect', 'plan_impact']],
                                 ['header', 'engineering', 'REQ-7', 'discuss', 'open', None, None])
        with self.assertRaises(CoordinationError):
            execute(self.root, {'op': 'topics'})

    def test_affected_owner_sees_conclusion_unless_confidential(self):
        self.open_topic()
        self.conclude(plan_impact=True)
        owner = self.view('qa')
        self.assertEqual(set(owner), HEADER | {'conclusion', 'lands_in'})
        self.assertEqual([owner[k] for k in ['view', 'effect', 'plan_impact', 'conclusion', 'lands_in']],
                         ['owner', 'binding', True, 'SIMULATED: retain exports for 30 days', LANDING])
        self.assertEqual(set(self.view('pm')), HEADER)
        self.open_topic('T2', visibility={'affected_owners': ['qa'], 'confidential': True})
        self.conclude(tid='T2')
        self.assertEqual(set(self.view('qa', 'T2')), HEADER)
        self.assertEqual(self.view('design', 'T2')['view'], 'full')

    def test_requests_group_under_an_open_topic_by_participants(self):
        self.open_topic()
        self.assertEqual(self.request('Q1', 'engineering')['payload']['topic'], 'T1')
        self.request('Q2', 'design')
        self.assertEqual(self.view('engineering')['requests'], ['Q1', 'Q2'])
        self.assertNotIn('requests', self.view('pm'))
        for rid, source, topic in [('Q3', 'qa', 'T1'), ('Q4', 'engineering', 'T9')]:
            with self.subTest(rid=rid), self.assertRaises(CoordinationError):
                self.request(rid, source, topic)
        self.escalate('engineering')
        with self.assertRaises(CoordinationError):
            self.request('Q5', 'engineering')
        self.assertEqual(self.request('Q1', 'engineering')['state'], 'ready')  # replay of an already recorded request

    def test_lifecycle_events_are_recorded(self):
        self.open_topic()
        self.note('engineering')
        self.escalate('engineering', 'owner', 'SIMULATED: owner decides')
        self.conclude()
        self.adopt('qa', outcome='satisfied', how='SIMULATED: tests updated')
        self.close()
        self.open_topic()  # replays add no events
        self.close()
        self.assertEqual(self.events(), ['topic_opened', 'topic_noted', 'topic_escalated', 'topic_concluded', 'topic_adopted', 'topic_closed'])

    def test_unknown_topic_is_rejected(self):
        for op in ['topic_note', 'topic_conclude', 'topic_adopt', 'topic_escalate', 'topic_close']:
            with self.subTest(op=op), self.assertRaisesRegex(CoordinationError, 'unknown topic'):
                self.runop(op, 'engineering', 'T9')

    def test_ledger_initialized_without_topics_gains_the_table(self):
        con = sqlite3.connect(str(self.root / 'management/runtime/coordination.sqlite3'))
        con.execute('DROP TABLE topics')
        con.commit()
        con.close()
        self.assertEqual(execute(self.root, {'op': 'topics', 'actor': 'pm'}), {'topics': []})
        self.assertEqual(self.open_topic()['state'], 'open')


if __name__ == '__main__':
    unittest.main()
