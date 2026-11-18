"""Synthetic PM game chains using public task, confirmation and launch operations."""
import copy
import json
from test_pm_instances import Fixture, TEAM, pm  # noqa: E402
import test_v037_direction_recovery as recovery
import longchain_fixture as h3
from public_review_fixture import stage_receipt

GAME = dict(scene_centered='yes', appearance_target='yes', direct_manipulation='yes', timing_feedback='yes')


def show(label, fn):
    try:
        result = fn()
        print(f'[{label}] ALLOWED', flush=True)
        return result if result is not None else True
    except (ValueError, KeyError, TypeError, OSError, AttributeError) as error:
        print(f'[{label}] BLOCKED {type(error).__name__}: {str(error)[:300]}', flush=True)
        return None


class Team(Fixture):
    rows = None            # list of scope dicts; default: one game scope 'board'
    extra_entries = ()     # added instance-config entries

    def setUp(self):
        controller = recovery.DirectionRecovery()
        controller.extra_entries=[dict(id='code-executors',profession='code-engineering',level='T4',model='SIM-small',count=2),*copy.deepcopy(list(self.extra_entries))]
        controller.direction_rows = self.rows or [h3.feature_scope('board', **GAME)]
        controller.setUp()
        self.addCleanup(controller.doCleanups)
        brief,assigned=controller.setup_direction()
        rec=controller.call('direction_sample',id='DIR',brief=brief,admitted_inputs=['BRIEF'],profile='SIM game',
                            person='SIM-owner',combined_review_authorization='SIM combined review',assigned=assigned)['direction_sample']
        controller.complete_direction(rec,assigned)
        self.controller = controller
        self.root = controller.root; self.n = controller.n + 1000; self._business_fixture = getattr(controller, '_business_fixture', None)
        self.gate = pm.admission.load_gate(); self.tone = self.gate.tone; self.ev = self.tone.evidence
        self.D = controller.data
        self.C = dict(self.ev.ref(self.root, self.tone.DEFAULT_PATH), version=self.D['version'])
        self.serial = 0

    # ---- generic task transactions ------------------------------------------------
    def start(self, tid, actor=None):
        print('public PM start',tid,flush=True)
        return self.mutate('transition', tid, actor, state='running', reason='SIM actual start', execution_receipt='SIM process')

    def handover(self, tid, evidence, actor=None):
        return self.mutate('transition', tid, actor, state='waiting_review', reason='SIM handover', stop_evidence='SIM returned', evidence=evidence)

    def finish(self, tid, evidence):
        self.handover(tid, evidence)
        self.check(tid)
        result=self.close(tid)
        print('public PM closed',tid,flush=True)
        return result

    def status(self, tid):
        return next(t for t in pm.execute(self.root, {'op': 'status'})['tasks'] if t['id'] == tid)

    def put(self, name, value):
        return h3.put(self.root, name, value)

    # ---- stage completion with a human review point ----------------------------------
    def human(self, state, tid=None, *, controller_receipt=True):
        """Display the stage artifacts, record the real answer, bind it, write request/response."""
        self.serial += 1
        rid = f'R{self.serial}-{state["current"]}'
        digest = self.gate.artifact_digest(self.root, state['artifacts'])
        quote = f'SIM complete approval of {state["current"]} {self.serial}'
        shown = self.put(f'management/reviews/{rid}-shown.md', 'SIM displayed the complete current artifacts: ' + ', '.join(a['path'] for a in state['artifacts']))
        reply = self.put(f'management/reviews/{rid}-reply.md', quote)
        request = dict(request_id=rid, role=state['role'], stage=state['current'], scope=state['scope'], artifact_sha256=digest,
                       display_evidence=shown['path'], display_sha256=shown['sha256'])
        response = dict(request_id=rid, scope=state['scope'], artifact_sha256=digest, actor='user', choice='confirm', source=reply['path'],
                        quote=quote, display_sha256=shown['sha256'], message_sha256=self.ev.digest(quote))
        kw = dict(task_id=tid) if tid else {}
        att_scope = state['scope'] if controller_receipt else ' '.join(state['scope'])   # human_review op needs a scope string
        self.call('human_attention', id=rid, kind='confirmation', display=shown['path'], scope=att_scope,
                  inputs=[a['path'] for a in state['artifacts']], **kw)
        self.call('human_attention', id=rid, response=reply['path'])
        state['request'] = self.put(f'management/reviews/{rid}-request.json', request)['path']
        state['response'] = self.put(f'management/reviews/{rid}-response.json', response)['path']
        response['review_receipt'] = stage_receipt(self,state,rid,'SIM-owner')
        self.put(state['response'],response)
        return state

    def state(self, role, current, artifacts, evidence=None, *, scope=('board',), **extra):
        stages = self.gate.STAGES[role]
        nxt = stages[stages.index(current) + 1]
        self.serial += 1
        conv = self.put(f'management/conversation/{self.serial}-{current}.md', f'{current} → {nxt}')
        s = dict(role=role, current=current, next=nxt, scope=list(scope), blockers=[], artifacts=[h3.ref(a) for a in artifacts],
                 conversation_check=conv['path'], tone_contract=self.C, practice_evidence=copy.deepcopy(evidence or {}))
        s.update(extra)
        return s

    def gate_file(self, name, state):
        self.put(name, state)
        return name

    def frozen(self, tid):
        receipt = self.t(tid)['practice_receipt']
        view, _ = self.ev.verify_bundle(self.root, receipt['bundle'])
        return view, json.loads((view / receipt['state_path']).read_text())

    # ---- an independent fit review delivered as a review_for child ------------------
    def fit_child(self, parent, fid, checker, path, writer, qa='quality-engineering-001', stage=None):
        stage = stage or (('engineering', 'E-1.2') if checker.startswith('code-engineering') else ('quality', 'Q-3'))
        self.create(fid, parent=parent, actor='PM', owner=checker, executor=checker, checker=qa, review_for=parent,
                    outputs=[path], practice_stage={'role': stage[0], 'current': stage[1], 'scope': ['fit review']})
        self.start(fid)
        ref = writer()
        self.finish(fid, [path])
        return ref


OUT_SOL = ['engineering/solution/', 'src/', 'trial/', 'index.html', 'management/reviews/', 'management/conversation/']
OUT_BUILD = ['engineering/build/', 'src/', 'index.html', 'management/reviews/', 'management/conversation/']
OUT_D = ['design/', 'management/reviews/', 'management/conversation/']


class Steps(Team):
    """Legitimate engineering steps E-2.2 .. E-3.1 (game scope 'board'), reusable by probes."""
    def stage_task(self, tid, role, current, owner, outputs, entry_evidence=None, deps=(), **stage_extra):
        practice_stage = dict(role=role, current=current, scope=['board'], tone_contract=self.C, **stage_extra)
        if entry_evidence:
            practice_stage['practice_evidence'] = entry_evidence
        completion = {'design': 'design/reviews/gate-', 'solution': 'engineering/solution/gate-', 'build': 'engineering/build/gate-',
                      'release': 'engineering/release/gate-'}[role] + tid + '.json'
        self.create(tid, owner=owner, executor=owner, practice_stage=practice_stage, practice_completion=completion,
                    outputs=outputs, dependencies=list(deps))
        return practice_stage, completion

    def complete(self, tid, completion, state, handed, human=False):
        if human:
            state = self.human(state, tid)
        self.gate_file(completion, state)
        self.finish(tid, [completion, *handed])

    def e22(self):
        root = self.root
        ps, comp = self.stage_task('T22', 'solution', 'E-2.2', 'code-engineering-001', OUT_SOL)
        self.start('T22')
        self.board1 = self.put('src/board.js', 'drawBoard() // trial renderer kept')
        feel = self.put('trial/feel.js', 'feelProbe() // throwaway')
        trial = [self.board1, feel]
        ev = {'rendering_choice': {'board': h3.record(root, 'rendering_choice', self.C, trial, 'engineering/solution/rendering.json')},
              'appearance_proof': {'board': h3.record(root, 'appearance_proof', self.C, trial, 'engineering/solution/proof.json',
                                                      shot=self.put('engineering/solution/proof.png', h3.shotpng()))},
              'playable_prototype': {'board': h3.record(root, 'playable_prototype', self.C, trial, 'engineering/solution/prototype.json', stage='E-2.2')}}
        self.complete('T22', comp, self.state('solution', 'E-2.2', trial, ev), [self.board1['path'], feel['path']])
        _, self.f22 = self.frozen('T22')

    def e23_dispatch(self):
        ps, comp = self.stage_task('T23', 'solution', 'E-2.3', 'code-engineering-001', OUT_SOL, self.f22['practice_evidence'], ['T22'])
        self.start('T23')
        self.board2 = self.put('src/board.js', 'drawBoard(); drawTrack(); drawPawns() // skeleton evolved from the trial')
        self.main1 = self.put('src/main.js', 'import "./board.js"')
        if (self.root / 'trial/feel.js').exists():
            (self.root / 'trial/feel.js').unlink()
        self.skel = [self.board2, self.main1]
        return comp

    def skeleton_record(self):
        return h3.record(self.root, 'core_scene_skeleton', self.C, self.skel, 'engineering/solution/skeleton.json',
                         shot=self.put('engineering/solution/skeleton.png', h3.shotpng()))

    def e23(self, checker='code-engineering-002'):
        root = self.root
        comp = self.e23_dispatch()
        ev = copy.deepcopy(self.f22['practice_evidence'])
        ev['core_scene_skeleton'] = {'board': self.skeleton_record()}
        ev['skeleton_fit'] = {'board': self.fit_child('T23', 'FIT23', checker, 'reviews/skeleton-fit.json',
            lambda: h3.fit(root, self.C, self.skel, 'reviews/skeleton-fit.json', shot=self.put('reviews/skeleton-fit.png', h3.shotpng()),
                           direction_data=self.D, mode='independent', checker=checker, producer='code-engineering-001', review_task='FIT23'))}
        self.complete('T23', comp, self.state('solution', 'E-2.3', self.skel, ev), [self.board2['path'], self.main1['path']])
        _, self.f23 = self.frozen('T23')

    def e24(self):
        ps, comp = self.stage_task('T24', 'solution', 'E-2.4', 'code-engineering-001', OUT_SOL, self.f23['practice_evidence'], ['T23'])
        self.start('T24')
        handover = self.put('engineering/solution/handover.md', 'Constraints, skeleton entry, limits')
        self.complete('T24', comp, self.state('solution', 'E-2.4', [handover], self.f23['practice_evidence']), [handover['path']], human=True)
        t24 = self.t('T24')
        self.up = {'upstream': t24['practice_receipt']['state_path'], 'upstream_bundle': t24['practice_receipt']['bundle']}
        _, self.f24 = self.frozen('T24')

    def e31(self):
        ps, comp = self.stage_task('T31', 'build', 'E-3.1', 'code-engineering-001', OUT_BUILD, self.f24['practice_evidence'], ['T24'], **self.up)
        self.start('T31')
        plan = self.put('engineering/build/plan.md', 'INC-1: first playable turn')
        self.complete('T31', comp, self.state('build', 'E-3.1', [plan], self.f24['practice_evidence'], **self.up), [plan['path']])
        _, self.f31 = self.frozen('T31')
