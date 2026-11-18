"""Long public single-conversation chain must not recursively copy evidence bundles."""
import copy
import json
import time
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from longchain_fixture import *

def run_chain(root):
    GAME = dict(scene_centered='yes', appearance_target='yes', direct_manipulation='yes', timing_feedback='yes')
    
    C, D = direction(root, [feature_scope('board', **GAME)])
    print('project root length:', len(str(root)), '|', root)
    
    
    def measure(label, fn, *a, **k):
        t0 = time.time()
        try:
            project,state=a
            state_path=project/('management/longchain-'+label+'.json')
            put(project,state_path.relative_to(project).as_posix(),state)
            run=subprocess.run([sys.executable,'-B',str(KIT/'matrix/base/tools/stage_gate.py'),
                                '--project',str(project),'--state',str(state_path)],capture_output=True,text=True)
            if run.returncode:raise ValueError(run.stdout+run.stderr)
            result=json.loads(run.stdout)
        except (ValueError, KeyError, TypeError, OSError, AttributeError) as error:
            print(f'[{label}] BLOCKED {type(error).__name__}: {str(error)[:160]} ... (len {len(str(error))})')
            raise
        dt = time.time() - t0
        files = [p for p in (root / 'management/evidence').rglob('*') if p.is_file()]
        rel = [p.relative_to(root).as_posix() for p in files]
        depth = max(r.count('management/evidence/') for r in rel)
        longest = max(len(r) for r in rel)
        size = sum(p.stat().st_size for p in files)
        print(f'[{label}] ALLOWED  {dt:6.1f}s  depth={depth:2d}  longest_rel_path={longest:4d}  abs={longest+len(str(root))+1:4d}  '
              f'evidence_files={len(files):6d}  bytes={size/1e6:7.1f}MB')
        return result
    
    
    # D-1, D-2 (design side)
    anchor = put(root, 'design/anchor.svg', '<svg>wood</svg>')
    d1 = [anchor]
    ev1 = {'direction_contribution': {'board': record(root, 'direction_contribution', C, d1, 'design/reviews/contrib.json')},
           'appearance_target': {'board': record(root, 'appearance_target', C, d1, 'design/reviews/appearance.json')},
           'design_fit': {'board': fit(root, C, d1, 'design/reviews/d1-fit.json', shot=put(root, 'design/reviews/d1.png', shotpng()), direction_data=D, comparison=False)}}
    r1 = measure('D-1', gate.check, root, human_stage(root, stage(root, 'design', 'D-1', 'D-2', C, d1, ev1), 'D1'))
    layout = put(root, 'design/structure.md', 'board layout')
    ev2 = {'appearance_target': r1['practice_evidence']['appearance_target'],
           'scene_structure': {'board': record(root, 'scene_structure', C, [layout], 'design/reviews/structure.json')},
           'design_fit': {'board': fit(root, C, [layout], 'design/reviews/d2-fit.json', shot=put(root, 'design/reviews/d2.png', shotpng()), direction_data=D, comparison=False)}}
    r2 = measure('D-2', gate.check, root, human_stage(root, stage(root, 'design', 'D-2', 'D-3', C, [layout], ev2), 'D2'))
    r3 = measure('D-3', gate.check, root, stage(root, 'design', 'D-3', 'D-4', C, [put(root, 'design/flows.md', 'flows')], {}))
    ev4 = {'appearance_target': r1['practice_evidence']['appearance_target'], 'scene_structure': r2['practice_evidence']['scene_structure']}
    r4 = measure('D-4', gate.check, root, human_stage(root, stage(root, 'design', 'D-4', 'D-5', C, [put(root, 'design/assets.md', 'assets')], ev4), 'D4'))
    r5 = measure('D-5', gate.check, root, stage(root, 'design', 'D-5', 'D-6', C, [put(root, 'design/spec.md', 'spec')], {}))
    
    # Engineering
    board1 = put(root, 'src/board.js', 'drawBoard() // trial')
    feel = put(root, 'src/trial/feel.js', 'feel() // throwaway')
    trial = [board1, feel]
    e = {'rendering_choice': {'board': record(root, 'rendering_choice', C, trial, 'engineering/solution/rendering-choice.json')},
         'appearance_proof': {'board': record(root, 'appearance_proof', C, trial, 'engineering/solution/appearance-proof.json',
                                              shot=put(root, 'engineering/solution/proof.png', shotpng()))},
         'playable_prototype': {'board': record(root, 'playable_prototype', C, trial, 'engineering/solution/prototype.json', stage='E-2.2')}}
    r22 = measure('E-2.2', gate.check, root, stage(root, 'solution', 'E-2.2', 'E-2.3', C, trial, e))
    board2 = put(root, 'src/board.js', 'drawBoard(); drawTrack(); drawPawns() // skeleton')
    main1 = put(root, 'src/main.js', 'import "./board.js"')
    index1 = put(root, 'index.html', '<main id=board></main>')
    (root / 'src/trial/feel.js').unlink()
    skel = [index1, board2, main1]
    e = copy.deepcopy(r22['practice_evidence'])
    e['core_scene_skeleton'] = {'board': record(root, 'core_scene_skeleton', C, skel, 'engineering/solution/skeleton.json', shot=put(root, 'engineering/solution/skeleton.png', shotpng()))}
    e['skeleton_fit'] = {'board': fit(root, C, skel, 'engineering/solution/skeleton-fit.json', shot=put(root, 'engineering/solution/skeleton-fit.png', shotpng()), direction_data=D)}
    r23 = measure('E-2.3', gate.check, root, stage(root, 'solution', 'E-2.3', 'E-2.4', C, skel, e))
    r24 = measure('E-2.4', gate.check, root, human_stage(root, stage(root, 'solution', 'E-2.4', 'complete', C,
                                                                     [put(root, 'engineering/solution/handover.md', 'Handover')], r23['practice_evidence']), 'E24'))
    up = dict(upstream=r24['upstream_state'], upstream_bundle=r24['review_bundle'])
    r31 = measure('E-3.1', gate.check, root, stage(root, 'build', 'E-3.1', 'E-3.2', C, [put(root, 'engineering/build/plan.md', 'INC-1')], r24['practice_evidence'], **up))
    board3 = put(root, 'src/board.js', 'drawBoard(); drawTrack(); drawPawns(); highlight() // INC-1')
    turn1 = put(root, 'src/turn.js', 'roll(); choose(); move()')
    inc = [index1, board3, main1, turn1]
    ev6 = {'implementation_walkthrough': {'board': record(root, 'implementation_walkthrough', C, inc, 'design/reviews/walkthrough.json')},
           'increment_fit': {'board': fit(root, C, inc, 'design/reviews/increment-fit.json', shot=put(root, 'design/reviews/inc.png', shotpng()), direction_data=D)}}
    r6 = measure('D-6', gate.check, root, human_stage(root, stage(root, 'design', 'D-6', 'D-7', C, inc, ev6), 'D6'))
    r7 = measure('D-7', gate.check, root, stage(root, 'design', 'D-7', 'complete', C, [put(root, 'design/maintenance.md', 'maintenance')], {}))
    ev32 = copy.deepcopy(r31['practice_evidence'])
    w = json.loads((root / 'design/reviews/walkthrough.json').read_text())
    w['design_review'] = {'bundle': r6['review_bundle'], 'state_path': r6['upstream_state']}
    ev32['implementation_walkthrough'] = {'board': ref(put(root, 'engineering/build/walkthrough.json', w))}
    ev32['increment_fit'] = {'board': fit(root, C, inc, 'engineering/build/increment-fit.json', shot=put(root, 'engineering/build/inc.png', shotpng()), direction_data=D)}
    r32 = measure('E-3.2', gate.check, root, stage(root, 'build', 'E-3.2', 'E-3.3', C, inc, ev32, **up))
    art33 = inc + [put(root, 'engineering/build/scope-review.md', 'Scope review pack')]
    ev33 = {'playable_prototype': {'board': record(root, 'playable_prototype', C, art33, 'engineering/build/play-e33.json', stage='E-3.3')}}
    r33 = measure('E-3.3', gate.check, root, human_stage(root, stage(root, 'build', 'E-3.3', 'complete', C, art33, ev33, **up), 'E33'))
    q1 = [put(root, 'quality/q1-plan.md', 'Q-1 plan')]
    evq1 = {k: {'board': record(root, k, C, q1, f'quality/{k}.json')} for k in ('direction_contribution', 'direction_acceptance_plan', 'motion_acceptance_plan')}
    rq1 = measure('Q-1', gate.check, root, stage(root, 'quality', 'Q-1', 'Q-2', C, q1, evq1))
    q2 = art33 + [put(root, 'quality/q2-report.md', 'Q-2 report')]
    evq2 = {'playable_prototype': {'board': record(root, 'playable_prototype', C, q2, 'quality/q2-play.json', stage='Q-2',
                                                    tested_stage=dict(bundle=r33['review_bundle'], state_path=r33['upstream_state']))}}
    rq2 = measure('Q-2', gate.check, root, stage(root, 'quality', 'Q-2', 'Q-3', C, q2, evq2))
    up33 = dict(upstream=r33['upstream_state'], upstream_bundle=r33['review_bundle'])
    r41 = measure('E-4.1', gate.check, root, stage(root, 'release', 'E-4.1', 'E-4.2', C, [put(root, 'release/plan.md', 'release plan')], {}, **up33))
    r42 = measure('E-4.2', gate.check, root, human_stage(root, stage(root, 'release', 'E-4.2', 'E-4.3', C, [put(root, 'release/decision.md', 'go')], {}, **up33), 'E42'))
    up42 = dict(upstream=r42['upstream_state'], upstream_bundle=r42['review_bundle'])
    r43 = measure('E-4.3', gate.check, root, stage(root, 'release', 'E-4.3', 'complete', C, [put(root, 'release/rollout.md', 'rolled out')], {}, **up42))
    return dict(files=len(list((root/'management/evidence').rglob('*'))), depth=max(p.relative_to(root).as_posix().count('management/evidence/') for p in (root/'management/evidence').rglob('*') if p.is_file()))

class LongChain(unittest.TestCase):
    def test_game_chain_to_release_keeps_bounded_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            result=run_chain(Path(temp).resolve())
            self.assertLessEqual(result["depth"],2)
            self.assertLess(result["files"],1800)
