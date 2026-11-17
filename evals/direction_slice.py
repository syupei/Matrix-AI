#!/usr/bin/env python3
"""Run a paired, mixed-model front-half slice with a separated synthetic stakeholder."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import secrets
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from run import fingerprint
from scoring import blinded_value
from team_live import run
from visual_evidence import capture

ROLES = {
    'product':'matrix-product',
    'design':'matrix-experience-design',
    'content':'matrix-content-design',
}
INITIAL = '做一个桌面单机掷骰走格子游戏，要有游戏感、好玩、文字有趣。'
HIDDEN = '''这是经授权的合成需求，模拟项目负责人。主要活动是直接操作骰子并观察棋子、回合和分数。
不要普通表单和成排操作按钮；用轻松短句，但失分等后果要直说。一局约十分钟，两名本地玩家。
除一开始已说的要点，其余事实只在被追问时披露。回复真实呈现的材料。
'''


def usage(path):
    counts = {}
    for line in path.read_text().splitlines():
        record=json.loads(line)
        if record.get('type') == 'turn.completed':
            for key,value in record.get('usage',{}).items():
                if type(value) is int:
                    counts[key]=counts.get(key,0)+value
    if not counts:
        raise ValueError('completed model usage missing: '+str(path))
    return counts


def turn(root, log, name, model, effort, prompt, image=None):
    log.mkdir(parents=True, exist_ok=True)
    reply=log/(name+'.md')
    events=log/(name+'.jsonl')
    command=['codex','exec','--skip-git-repo-check','--ephemeral','--sandbox','workspace-write',
             '--json','-C',str(root),'-o',str(reply),'-m',model,'-c','model_reasoning_effort='+json.dumps(effort)]
    if image:
        command += ['-i',str(image)]
    started=time.monotonic()
    with events.open('x') as stream:
        subprocess.run(command+['-'], input=prompt, text=True, stdout=stream, cwd=root, timeout=480, check=True)
    return {'name':name,'model':model,'seconds':round(time.monotonic()-started,2),
            'characters':len(reply.read_text()),'usage':usage(events),'reply':reply.name}


def ask(path):
    data=json.loads(path.read_text())
    answer=data.get('answer')
    if data.get('decision') not in {'confirm','correct','answer'} or not isinstance(answer,str) or not answer.strip():
        raise ValueError('synthetic stakeholder response needs a supported decision and answer')
    return data


def stage(role, detail):
    return f'读取 .agents/skills/{ROLES[role]}/SKILL.md 及本任务需要的局部规则。你只负责 {role}。保留其他专业的文件。仅在这个合成项目写必要文件，不联网、不启动其他 Agent。\n{detail}'


def slice_run(kit, output, models, effort):
    output.mkdir(parents=True,exist_ok=False)
    logs=output/'turns'
    records=[]
    requests=[]
    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='matrix-direction-') as temporary:
        work=Path(temporary).resolve()
        project=work/'project'
        project.mkdir()
        stakeholder=work/'stakeholder'
        stakeholder.mkdir()
        run(str(kit/'install.py'),'--target',str(project),'--apply',cwd=project)
        tool='matrix/orchestration/tools/pm_tasks.py'

        def pm(op, **data):
            return run(tool,'--project','.',cwd=project,data=dict(op=op,actor='PM',event_id='slice-'+op+'-'+str(len(requests))+'-'+('answer' if 'response' in data else 'open'),**data))

        pm('init',config={'project':'合成方向切片','pm_actor':'PM','authorization':'仅合成评测',
                          'frontdoor_id':'Slice','max_slots':3})
        brief=project/'需求.md'
        brief.write_text(INITIAL)
        records.append(turn(project,logs,'product-clarify',models['product'],effort,stage('product',
            '读需求.md，先提出必要的澄清。把实际问题保存为 澄清.md；没有问题写“无需澄清”。不要替人回答。')))
        questions=(project/'澄清.md').read_text().strip()

        def owner(kind, shown, image=None):
            display='审阅材料-'+str(len(requests)+1)+'.md'
            (project/display).write_text(shown)
            rid='same-brief-'+str(len(requests)+1)
            opened=time.monotonic()
            # Use the new recorder when it is installed, keep identical external measurements on both versions.
            supports=(project/'matrix/orchestration/tools/pm_direction.py').is_file()
            if supports:
                pm('human_attention',id=rid,kind=kind,display=display)
            name='stakeholder-'+str(len(requests)+1)
            prompt=HIDDEN+'\n只根据以下已展示材料作答。保存纯 JSON 到当前目录的 response.json，字段 decision（answer、confirm、correct）和 answer（实际回复）。澄清时用 answer。审阅时，项目方向合适才 confirm，否则 correct 并写具体更正。\n'+shown
            response=stakeholder/'response.json'
            if response.exists():
                response.unlink()
            records.append(turn(stakeholder,logs,name,models['stakeholder'],effort,prompt,image))
            reply=ask(response)
            ref='收到答复-'+str(len(requests)+1)+'.md'
            (project/ref).write_text(reply['answer'],encoding='utf-8')
            requests.append(dict(id=rid, kind=kind, characters=len(shown),
                                 seconds=round(time.monotonic()-opened,2), decision=reply['decision'],response=ref))
            if supports:
                pm('human_attention',id=rid,response=ref)
            return reply,ref

        if questions!='无需澄清':
            owner('clarification', questions)
        records.append(turn(project,logs,'product-brief',models['product'],effort,stage('product',
            '根据需求.md、澄清及已有答复形成方向简报，保存为 product/direction-brief.md，供设计与内容读取。标明还需人决定的事项。')))
        columns=[
            ('design','读 product/direction-brief.md，制作可点核心场景 design/preview.html。保留设计依据和核心操作的可试性。'),
            ('content','读 product/direction-brief.md，写关键时刻的文案样句到 content/samples.md。如采用两种语气，保留各自分组。'),
        ]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(turn,project,logs,role+'-first',models[role],effort,stage(role,instruction)) for role,instruction in columns]
            records += [f.result() for f in futures]
        first=capture(project)
        if first['status'] != 'captured':
            raise ValueError('paired slice needs actual browser screenshot: '+str(first))
        # Keep the initial frame for the blinded comparison before any corrections.
        shutil.copyfile(project/first['screenshot'], output/'first-preview.png')
        def material():
            return (project/'product/direction-brief.md').read_text()+'\n'+(project/'content/samples.md').read_text()

        def fit(capture_result, index):
            checker=work/('fit-'+str(index))
            checker.mkdir()
            (checker/'material.md').write_text(material(),encoding='utf-8')
            focus = ('只查看 material.md 和附带截图，对照方向简报与样句。'
                     '标出品类是否贴合、哪些地方像普通应用、哪句像说明书，写到位置。'
                     '保存 fit.json，字段 decision（confirm 或 correct）和 answer（实际检查结论）。'
                     '不更改作品，不访问材料以外的文件。')
            records.append(turn(checker,logs,'fit-'+str(index),models.get('checker',models['stakeholder']),
                                effort,focus,project/capture_result['screenshot']))
            return ask(checker/'fit.json')

        captured = first
        decision = None
        ref = None
        internal_reviews = []
        if (project/'matrix/orchestration/tools/pm_direction.py').is_file():
            for i in range(3):
                result=fit(captured,i+1)
                internal_reviews.append(result)
                if result['decision']=='confirm':
                    break
                if i==2:
                    decision={'decision':'blocked_fit'}
                    break
                feedback=f'贴合检查-{i+1}.md'
                (project/feedback).write_text(result['answer'],encoding='utf-8')
                for role,detail in [('design','复核或修改 design/preview.html。'),
                                    ('content','复核或修改 content/samples.md。')]:
                    records.append(turn(project,logs,role+'-fit-rework-'+str(i+1),models[role],effort,
                        stage(role,f'读取 {feedback}，按实际发生的问题{detail}')))
                (project/captured['screenshot']).unlink()
                captured=capture(project)
                if captured['status']!='captured':
                    raise ValueError('capture after fit rework failed: '+str(captured))
        if decision is None:
            decision,ref=owner('confirmation', material(), project/captured['screenshot'])
        for n in range(2):
            if decision['decision'] in {'confirm','blocked_fit'}:
                break
            for role,detail in [('product','按收到的意见更新自己的方向简报。'),
                                ('design','按收到的意见复核或更新 design/preview.html。'),
                                ('content','按收到的意见复核或更新 content/samples.md。')]:
                records.append(turn(project,logs,role+'-correction-'+str(n+1),models[role],effort,stage(role,
                    f'读取 {ref}、已有简报与自己产物。{detail}')))
            (project/captured['screenshot']).unlink()
            captured=capture(project)
            if captured['status']!='captured':
                raise ValueError('capture after feedback failed: '+str(captured))
            if internal_reviews:
                result=fit(captured,len(internal_reviews)+1)
                internal_reviews.append(result)
                if result['decision']!='confirm':
                    decision={'decision':'blocked_fit'}
                    break
            decision,ref=owner('correction', material(), project/captured['screenshot'])
        final_direction = project/first['screenshot']
        if decision['decision']=='confirm' and final_direction.is_file():
            shutil.copyfile(final_direction,output/'accepted-direction.png')
        review_a = None
        if decision['decision']=='confirm':
            records.append(turn(project,logs,'product-baseline',models['product'],effort,stage('product',
                f'依据模拟决定人的 {ref} 和已存在的材料准备产品基线，记录确认范围、文件版本和未决事项。只采用实际批准范围。')))
            records.append(turn(project,logs,'design-review-a',models['design'],effort,stage('design',
                f'依据模拟决定人的 {ref} 及实际产品基线，交回可进入设计审阅 A 的可点原型首稿 design/review-a.html。安装包要求先核对的项目，按实际证据处理。')))
            final_direction.unlink()
            review_a = capture(project,'design/review-a.html')
            if review_a['status']=='captured':
                shutil.copyfile(project/review_a['screenshot'],output/'review-a.png')
        for part in ('product','design','content','visual-evidence'):
            if (project/part).is_dir():
                shutil.copytree(project/part,output/part)
        report={'source_hash':fingerprint(kit),'synthetic_stakeholder':True,'effort':effort,'first_visual':first,
                'last_decision':decision['decision'],'requests':requests,'turns':records,'seconds':round(time.monotonic()-started,2),
                'corrections':sum(req['decision']=='correct' for req in requests),'review_a':review_a,'fit_reviews':internal_reviews}
        if (project/'matrix/orchestration/tools/pm_direction.py').is_file():
            report['pm_attention']=pm('human_attention_status')
        (output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')


def blind(output):
    root = output / 'blind'
    sides = ['baseline','candidate']
    secrets.SystemRandom().shuffle(sides)
    labels = dict(zip(('X','Y'), sides))
    for label, side in labels.items():
        source, target = output/side, root/label
        target.mkdir(parents=True, exist_ok=False)
        for name in ('first-preview.png','accepted-direction.png','review-a.png'):
            if (source/name).is_file():
                shutil.copyfile(source/name,target/name)
        for name in ('content/samples.md','product/direction-brief.md'):
            if (source/name).is_file():
                (target/Path(name).name).write_text(blinded_value((source/name).read_text(),None))
        data = json.loads((source/'result.json').read_text())
        (target/'session.json').write_text(json.dumps({k:data[k] for k in ('last_decision','corrections','seconds','requests')},
                                                      ensure_ascii=False,indent=2))
    (output/'blind-labels.json').write_text(json.dumps(labels,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for label in ('baseline','candidate','output'):
        parser.add_argument('--'+label,type=Path,required=True)
    for label in ('product','design','content','stakeholder'):
        parser.add_argument('--'+label+'-model',required=True)
    parser.add_argument('--effort',default='medium',choices=['low','medium','high','xhigh'])
    parser.add_argument('--checker-model')
    args=parser.parse_args()
    models={label:getattr(args,label+'_model') for label in ('product','design','content','stakeholder')}
    models['checker']=args.checker_model or models['stakeholder']
    if len({models[role] for role in ROLES}) < 2:
        parser.error('use a mixed model team for the three professional roles')
    for side in ('baseline','candidate'):
        slice_run(getattr(args,side).resolve(),args.output.resolve()/side,models,args.effort)
    blind(args.output.resolve())


if __name__=='__main__':
    main()
