"""Read-only producer prechecks for the isolated imported-expert evaluation.

These inspect structure and current bytes. They never submit reviews, approvals,
fix blockers, edit producer outputs, or replace the final common stage gate.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile

CONTRACT='product/specs/00-方向样张.md'
STAGE='product/reviews/P-1-gate.json'
FIT='product/reviews/方向贴合.json'
AUTHOR='ADMISSION'
REVIEWER='SIM-INDEPENDENT-REVIEWER'


def require(value,message):
    if not value:raise ValueError(message)


def load_gate(project):
    spec=importlib.util.spec_from_file_location('import_precheck_gate',project/'matrix/base/tools/stage_gate.py')
    gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
    return gate


def author_stage(gate,public):
    state=json.loads(gate.tone.evidence.file(public,STAGE).read_text())
    require((state.get('role'),state.get('current'),state.get('next'),state.get('scope'))==('product','P-1','P-2',['race']),
            'author stage must retain the bounded P-1 race scenario')
    require(state.get('blockers')==[], 'business blockers must be resolved before independent review; keep workflow pending in author self-check')
    for ref in [*state.get('artifacts',[]),state.get('tone_contract')]:gate.tone.evidence.verify_ref(public,ref)
    require(state['tone_contract']['path']==CONTRACT, 'stage must bind its actual direction draft')
    return state


def reviewer_structure(project,checker_public):
    gate=load_gate(project);tone=gate.tone
    database=project/'management/runtime/tasks.sqlite3'
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
        records=[json.loads(row[0]) for row in db.execute("SELECT data FROM pm_records WHERE kind='launch'")]
        checks=[row for row in records if row.get('purpose')=='check' and row.get('instance')==REVIEWER and row.get('state')=='running']
        require(len(checks)==1,'one actual active independent check run required for the read-only precheck')
        check=checks[0]
        authors=[row for row in records if row.get('purpose')=='start' and row.get('task_id')==check['task_id'] and row.get('handed') is True]
        require(len(authors)==1,'actual author handback required')
    author=authors[0];author_public=project/'management/instances'/author['instance']/'workspace/public'
    private=checker_public.parent/'private';private.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fit-readonly-',dir=private) as temp:
        view=Path(temp)
        for name,expected in author['handover']['files'].items():
            path=tone.evidence.verify_ref(project,dict(path=name,sha256=expected))
            logical=path.relative_to(author_public);target=view/logical;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
        for path in checker_public.rglob('*'):
            if path.is_file() and '_evaluation' not in path.relative_to(checker_public).parts:
                tone.evidence.file(checker_public,path.relative_to(checker_public).as_posix())
                target=view/path.relative_to(checker_public);require(not target.exists(),'checker output cannot replace author bytes')
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
        stage=author_stage(gate,view);draft=tone.read(view,CONTRACT)
        fit=json.loads(tone.evidence.file(view,FIT).read_text())
        require(fit.get('producer')==author['instance'] and fit.get('checker')==REVIEWER and fit.get('mode')=='independent'
                and fit.get('review_task')==check['task_id'],'fit must name the actual author/checker/task')
        require(fit.get('outcome') in {'passed','failed'} and fit.get('binding_mode')=='pre_confirmation_direction'
                and fit.get('tone_contract')==tone.direction_binding(CONTRACT,draft),'fit must bind the actual unconfirmed draft')
        require(all(isinstance(fit.get(key),str) and fit[key].strip() for key in ('viewport','capture','genre_fit','application_drift','copy_fit')),
                'fit requires viewport, capture, genre_fit, application_drift and copy_fit')
        require(fit['viewport']==draft.get('viewport'),'fit viewport must match the direction draft')
        observed=[draft['parts'][key] for key in ('scene','preview','samples','practice_profile')]
        expected={(row['path'],row['sha256']) for row in observed}
        require({(row['path'],row['sha256']) for row in fit.get('artifacts',[])}==expected,'fit must cover all actual author materials')
        for ref in fit['artifacts']:tone.evidence.verify_ref(view,ref)
        tone.check_capture(view,fit,None,artifacts=fit['artifacts'],registry_root=project)
        fit_source=(checker_public/FIT).relative_to(project).as_posix()
        return dict(structure_valid=True,professional_outcome=fit['outcome'],author_stage=dict(path=(author_public/STAGE).relative_to(project).as_posix(),
            sha256=hashlib.sha256((author_public/STAGE).read_bytes()).hexdigest()),
            fit=dict(path=fit_source,sha256=hashlib.sha256((checker_public/FIT).read_bytes()).hexdigest()),
            final_gate='not run: actual review submission and controller confirmation remain pending')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True);parser.add_argument('--author-public',type=Path);parser.add_argument('--checker-public',type=Path)
    args=parser.parse_args()
    try:
        root=args.project.resolve()
        result=reviewer_structure(root,args.checker_public.resolve()) if args.checker_public else dict(
            structure_valid=True,state=author_stage(load_gate(root),args.author_public.resolve()),final_gate='pending independent review and control projection')
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (ValueError,KeyError,TypeError,OSError) as error:
        print(json.dumps(dict(structure_valid=False,error=str(error)),ensure_ascii=False));raise SystemExit(1)
