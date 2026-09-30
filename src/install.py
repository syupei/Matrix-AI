#!/usr/bin/env python3
"""Preserving installation of the complete professional-agent test kit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parent
BEGIN='<!-- pm-agent-test:begin -->'
END='<!-- pm-agent-test:end -->'
BLOCK=BEGIN+'\n## 专业 Agent 入口\n\n按当前任务读取对应岗位：\n- [产品](.agents/skills/product-agent/SKILL.md)\n- [设计](.agents/skills/experience-design-agent/SKILL.md)\n- [工程承接](.agents/skills/engineering-intake-agent/SKILL.md)\n- [项目管理](.agents/skills/project-management-agent/SKILL.md)\n- [专业协作](.agents/skills/professional-agent-collaboration/SKILL.md)\n\n仅解析当前角色索引的项目说明及本轮阶段所需资料；从有效成果、确认和状态恢复。\n共同确认/步骤规则见 [用户交互](collaboration/USER-INTERACTION.md)，切换阶段检查见 [阶段关卡](collaboration/STAGE-GATES.md)。\n专业事实由原责任方维护；安装配置不等于启动Agent、批准成果或获得外部行动授权。\n'+END+'\n'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe(root,rel):
    p=root/rel
    if Path(rel).is_absolute() or '..' in Path(rel).parts or not p.resolve().is_relative_to(root):
        raise ValueError('unsafe destination: '+str(rel))
    for node in [p,*p.parents]:
        if node==root:break
        if node.is_symlink():raise ValueError('symlink destination: '+str(rel))
        if node!=p and node.exists() and not node.is_dir():raise ValueError('parent is not a directory: '+str(node))
    if p.exists() and not p.is_file():raise ValueError('destination is not file: '+str(rel))
    return p


def atomic(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.pm-install-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data)
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def install(target,apply=False):
    root=Path(target).resolve()
    if not root.is_dir():raise ValueError('target project must exist')
    bases=json.loads((ROOT/'upgrade-bases.json').read_text())
    manifest=json.loads((ROOT/'MANIFEST.json').read_text())
    plans=[]
    preserved=[]
    guidance=[]
    guidance_paths={".agents/skills/"+role+"/GUIDANCE-INDEX.md" for role in ['product-agent', 'experience-design-agent', 'engineering-intake-agent', 'project-management-agent', 'professional-agent-collaboration', 'content-design-review']}
    for rel,expected in sorted(manifest['files'].items()):
        if not (rel.startswith('.agents/skills/') or rel.startswith('collaboration/') or rel.startswith('shared/')):continue
        src=ROOT/rel
        data=src.read_bytes()
        if sha(data)!=expected:raise ValueError('package hash mismatch: '+rel)
        dest=safe(root,rel)
        before=dest.read_bytes() if dest.exists() else None
        if before==data:continue
        if before is not None and sha(before) not in bases.get(rel,[]):
            if rel in guidance_paths:
                guidance.append(rel)
                continue
            if rel.startswith('collaboration/') and rel not in ['collaboration/PM-REPORTING.md','collaboration/COPY-QUALITY.md','collaboration/STRUCTURED-HANDOFF.md']:
                preserved.append(rel)
                continue
            raise ValueError('custom/unknown existing file requires merge before install: '+rel)
        plans.append((rel,before,data))
    rel='AGENTS.md'
    dest=safe(root,rel)
    before=dest.read_bytes() if dest.exists() else None
    content=(before or b'').decode()
    if BEGIN in content or END in content:
        if content.count(BEGIN)!=1 or content.count(END)!=1 or content.index(BEGIN)>content.index(END):
            raise ValueError('malformed managed PM block')
        content=content[:content.index(BEGIN)]+BLOCK.rstrip('\n')+content[content.index(END)+len(END):]
    else:
        content=BLOCK+'\n'+content
    if content.encode()!=before:plans.append((rel,before,content.encode()))
    # Validate backups/receipt destinations before any mutation.
    for rel,before,data in plans:
        if before is not None:
            backup=safe(root,'management/install-backups/'+sha(before)+'/'+rel)
            if backup.exists() and backup.read_bytes()!=before:raise ValueError('backup conflict')
    safe(root,'management/install-receipt.json')
    if not apply:
        return {'dry_run':True,'target':str(root),'changes':[x[0] for x in plans],'preserved_custom_common':preserved,'preserved_custom_guidance':guidance,'guidance_review_required':guidance}
    written=[]
    for rel,before,data in plans:
        dest=safe(root,rel)
        current=dest.read_bytes() if dest.exists() else None
        if current!=before:raise ValueError('concurrent edit; retained earlier writes, rerun preflight: '+rel)
        if before is not None:
            backup=safe(root,'management/install-backups/'+sha(before)+'/'+rel)
            if not backup.exists():atomic(backup,before)
        atomic(dest,data)
        written.append({'path':rel,'before':sha(before) if before is not None else None,'after':sha(data)})
    result={'installed':True,'package':manifest['package'],'target':str(root),
            'at':datetime.now(timezone.utc).isoformat(),'written':written,
            'preserved_custom_common':preserved,'preserved_custom_guidance':guidance,
            'guidance_review_required':guidance,'runtime_initialized':False,
            'professional_business_sources_modified':False,
            'note':'Per-file atomic and rerunnable; not a project-wide transaction. Runtime/adoption verified separately.'}
    receipt=safe(root,'management/install-receipt.json')
    if written or not receipt.exists():atomic(receipt,json.dumps(result,ensure_ascii=False,indent=2).encode())
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--target',required=True)
    p.add_argument('--apply',action='store_true')
    args=p.parse_args()
    try:print(json.dumps(install(args.target,args.apply),ensure_ascii=False,indent=2))
    except (ValueError,OSError,KeyError) as e:
        print(json.dumps({'error':str(e)},ensure_ascii=False));raise SystemExit(1)
