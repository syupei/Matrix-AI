"""Reject external inputs as deliverables, shared by stages and task handback.

This identifies paths and identical bytes, not whether rewriting involved real
professional analysis. A sealed stage keeps the external index checked at close.
"""
import hashlib
import re
from pathlib import Path

DEFINITION = {'version':1,'record':'artifacts','submission':{
    'version':1,'when':'before handover or stage completion',
    'reject':['external/ paths','byte-identical copies of external/ files'],
    'rule':'matrix/base/CORE.md#1-优先级',
    'limitation':'Changed copies require professional review; byte checks do not certify authorship.'}}


def file(root,name):
    root=Path(root).resolve();rel=Path(name)
    if rel.is_absolute() or '..' in rel.parts:raise ValueError('project-relative deliverable required: '+str(name))
    path=root/rel
    if not path.resolve().is_relative_to(root) or any(p.is_symlink() for p in [path,*path.parents] if p!=root and root in p.parents):
        raise ValueError('linked external input or deliverable rejected: '+str(name))
    if not path.is_file():raise ValueError('missing external input or deliverable: '+str(name))
    return path


def snapshot(root):
    root=Path(root).resolve();folder=root/'external';result={}
    if folder.is_symlink():raise ValueError('external/ must be a local project directory')
    if not folder.exists():return result
    if not folder.is_dir():raise ValueError('external/ must be a local project directory')
    for path in sorted(folder.rglob('*')):
        if path.is_symlink():raise ValueError('external/ contains a symbolic link: '+str(path.relative_to(root)))
        if path.is_file():
            name=path.relative_to(root).as_posix()
            result[name]=hashlib.sha256(file(root,name).read_bytes()).hexdigest()
    return result


def check(root,paths,external_inputs=None):
    root=Path(root).resolve()
    index=snapshot(root) if external_inputs is None else external_inputs
    if not isinstance(index,dict):raise ValueError('external input index required')
    originals={}
    for name,digest in index.items():
        if not isinstance(name,str) or not name.startswith('external/') or not isinstance(digest,str) or not re.fullmatch(r'[0-9a-f]{64}',digest):
            raise ValueError('invalid frozen external input index')
        originals.setdefault(digest,[]).append(name)
    for name in paths:
        rel=Path(name)
        if rel.parts and rel.parts[0]=='external':
            raise ValueError('外部输入不能作为交接成果：'+str(name)+'；外部材料作为输入引用，不要列进成果；由对应专家分析并形成本项目成果后再交接（CORE §1）。')
        digest=hashlib.sha256(file(root,name).read_bytes()).hexdigest()
        if digest in originals:
            raise ValueError('交接成果与外部输入逐字节相同：'+str(name)+' ← '+', '.join(originals[digest])+'；外部材料作为输入引用，不要列进成果；由对应专家分析后形成项目成果。')
    return dict(schema='handover-origin/1',external_inputs=index,
                limitation='Only registered external paths and identical bytes are checked; professional analysis and modified copies still require review.')
