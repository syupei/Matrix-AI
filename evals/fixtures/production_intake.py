"""Synthetic external input supplied identically to both compared kits."""

from pathlib import Path
import json
import subprocess
import sys


def populate(root, case):
    (root/'external').mkdir()
    (root/'external/PRD.md').write_text('合成外部规格，版本 1：员工只能看到自己的申请。没有产品确认。',encoding='utf-8')
    people=root/'management'
    people.mkdir()
    (people/'people.json').write_text(json.dumps({'people':[{'id':'review-owner','name':'合成项目负责人','decides':['project']}]}),encoding='utf-8')
    tool=root/'kit/matrix/orchestration/tools/pm_tasks.py'

    def call(op, index, **fields):
        subprocess.run([sys.executable,'-B',str(tool),'--project',str(root)],
                       input=json.dumps(dict(op=op,actor='PM',event_id='fixture-'+str(index),**fields)),
                       capture_output=True,text=True,check=True)

    call('init',1,config={'project':'合成准入项目','pm_actor':'PM','frontdoor_id':'Review','max_slots':3,
                         'authorization':'合成测试，仅验证工具行为'})
    if case=='prod_direct_instruction':
        call('create',2,task={'id':'E-touched','owner':'worker','executor':'worker','checker':'PM',
                             'title':'已派发说明','goal':'仅写现有规则的影响说明',
                             'inputs':['现有规则说明'],'outputs':['engineering/impact.md'],
                             'criteria':['只说明既有规则'],'next_action':'准备影响说明'})
