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
BLOCK=BEGIN+'''
## PM 全流程组织与分层任务

本项目已接入 PM 测试版及专业子任务上报。项目启动/统筹/进度/调度/续做时读取
[project-management-agent](.agents/skills/project-management-agent/SKILL.md)。
PM 从一句话需求或当前有效阶段接管，规划可定义顶层任务；专业角色自管子任务，按
[PM-REPORTING](collaboration/PM-REPORTING.md) 上报、记录事件并提供展开入口。

产品、设计、研发承接分别使用现有对应 skill，不因 PM 接入重做有效成果或扩大专业权限：
[产品](.agents/skills/product-agent/SKILL.md)、
[设计](.agents/skills/experience-design-agent/SKILL.md)、
[研发 E1](.agents/skills/engineering-intake-agent/SKILL.md)。
具体问询与实际唤醒沿用 [公共运行入口](collaboration/RUNTIME.md)。
普通子计划调整与授权内接续自主执行；需要人时由当前主任务统一合批展示真实成果和确认范围。
保留既有授权、免审范围、专业基线、人的修改和待审状态；安装不代表候选通过或 E2/E3 已接入。

可读项目入口由任务源生成在 `management/views/index.md`，未初始化前不得伪造任务进度。
启动时恢复实际阶段及责任，登记当前和后续可规划任务，不从头再做一次。

所有角色按 [全量文案转译与校核](collaboration/COPY-QUALITY.md) 处理产出与引用文字。
用户表达要求贯穿正文、辅助、状态与风险；保留事实不等于逐字冻结上游，产品成稿与设计
完整扩展都需核对并回读，PM检查实际覆盖证据，E1承接语义与来源，协作维护版本和合并。
设计优先读取并实际使用适用的项目配置/已安装设计 skill（如 Figma），无适用 skill 或
已有明确替代授权时才自行制作，工具受阻不静默改写本地页面。安装不表示旧文案已修复。
旧入口把项目管理称为未来角色的历史说明由本段已安装能力范围替代；用户现行授权优先。
产品 S6/S7 及下游接收、变更回查按 [结构化交付](collaboration/STRUCTURED-HANDOFF.md)
使用当前有效源、候选快照和实际核对报告；结构检查不替代专业结论或人的确认。
'''+END+'\n'


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
    for rel,expected in sorted(manifest['files'].items()):
        if not (rel.startswith('.agents/skills/') or rel.startswith('collaboration/')):continue
        src=ROOT/rel
        data=src.read_bytes()
        if sha(data)!=expected:raise ValueError('package hash mismatch: '+rel)
        dest=safe(root,rel)
        before=dest.read_bytes() if dest.exists() else None
        if before==data:continue
        if before is not None and sha(before) not in bases.get(rel,[]):
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
        return {'dry_run':True,'target':str(root),'changes':[x[0] for x in plans],'preserved_custom_common':preserved}
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
            'preserved_custom_common':preserved,'runtime_initialized':False,
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
