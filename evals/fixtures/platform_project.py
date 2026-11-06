"""Synthetic project on the platform: a scheduler is running it, so tasks carry run records (all SYNTHETIC: no process
was started, no model ran, no person approved anything).

platform_pm_wakeup    the PM is woken: A handed over for its check, B ready (the scheduler's to start), C ended
                      without handover because its model does not exist, and an answer from the person about A.
platform_desk_stopped the front desk is asked why work stopped: the unattended launch limit is used up.
platform_worker_packet an instance reads the task packet of its run and works on W.
"""
import importlib.util
import json
import os
from pathlib import Path

LAYOUT = Path(__file__).resolve().with_name('layout.py')


def populate(root, case_id):
    if case_id not in {'platform_pm_wakeup', 'platform_desk_stopped', 'platform_worker_packet'}:
        raise ValueError('unknown platform fixture case: ' + case_id)
    spec = importlib.util.spec_from_file_location('platform_layout', LAYOUT)
    layout = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(layout)
    pm = layout.tool('pm_tasks')
    n = [0]

    def call(op, actor='PM', **kw):
        n[0] += 1
        return pm.execute(root, dict(op=op, actor=actor, event_id='FIXTURE-' + str(n[0]), **kw))

    def task(tid):
        return next(t for t in pm.execute(root, {'op': 'status'})['tasks'] if t['id'] == tid)

    def write(rel, text):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    write('BRIEF.md', '合成项目：内部意见箱。已确定：员工提交意见、管理员查看列表。未定：是否匿名、附件大小上限。')
    call('init', config=dict(project='SYNTHETIC suggestion box', pm_actor='PM', authorization='BRIEF.md', frontdoor_id='SYNTHETIC', max_slots=3))
    call('configure', frontdesk_actor='DESK')
    entries = [{'id': 'P-M', 'profession': 'product', 'level': 'T7', 'model': 'SYNTHETIC-model-a', 'count': 1, 'master': True},
               {'id': 'C-M', 'profession': 'content-design', 'level': 'T6', 'model': 'SYNTHETIC-model-b', 'count': 1, 'master': True}]
    write('management/instance-config.json', json.dumps({'entries': entries}))
    call('confirm_config', person='SYNTHETIC-owner', quote='SYNTHETIC: 按这个配置', presented_ref='BRIEF.md',
         choices={e['id']: 'acknowledge_unregistered' for e in entries})
    for e in entries:
        call('derive', entry=e['id'], endpoint='platform')
    common = dict(parent=None, checker='PM', inputs=['BRIEF.md'], criteria=['只用 BRIEF.md 已确定的规则', '未定的列为待人决定'], next_action='制作候选')

    def create(tid, owner, title, **extra):
        call('create', task=dict(id=tid, title=title, owner=owner, executor=owner, goal=title, outputs=[title + '（工作区内）'], **common, **extra))

    def run(tid, rid, model):
        call('launch_start', id=rid, purpose='start', task_id=tid, instance=task(tid)['executor'], model=model, session='SYNTHETIC-' + rid,
             command=['SYNTHETIC-host'], log='management/runtime/logs/' + rid + '.log')
        call('launch_started', id=rid, pid=os.getpid())

    if case_id == 'platform_pm_wakeup':
        create('A', 'product-001', '意见提交流程候选')
        create('B', 'content-design-001', '提交成功与失败的提示文字', dependencies=[])
        create('C', 'product-001', '管理员列表的筛选规则候选')
        run('A', 'run-fixture-A', 'SYNTHETIC-model-a')
        write('management/instances/product-001/workspace/A-候选.md',
              '# 意见提交流程候选（合成）\n\n1. 员工填写意见并提交。\n2. 管理员在列表里看到新意见。\n\n待人决定：是否匿名；附件大小上限。\n')
        call('hand_over', 'product-001', run='run-fixture-A', evidence=['management/instances/product-001/workspace/A-候选.md'], summary='合成：自检完成')
        call('launch_exit', 'launcher', id='run-fixture-A', exit_code=0)
        run('C', 'run-fixture-C', 'missing-model')
        call('launch_exit', 'launcher', id='run-fixture-C', exit_code=1)
        write('management/instances/product-001/runs/run-fixture-C-result.md',
              '# 运行 run-fixture-C 的结果\n\n- 退出代码：1\n\n宿主报告：模型 missing-model 不存在，请求没有开始。\n')
        call('inbox', 'DESK', id='IN-1', kind='answer', text='A 的流程先不做匿名，附件上限以后再定', ref='A', person='SYNTHETIC-owner',
             quote='SYNTHETIC: 先不做匿名，附件以后再说')
    elif case_id == 'platform_desk_stopped':
        call('configure', limits={'unattended_launches': 2}, person='SYNTHETIC-owner', quote='SYNTHETIC: 先最多自动拉起两次')
        create('A', 'product-001', '意见提交流程候选')
        create('B', 'content-design-001', '提交成功与失败的提示文字')
        create('D', 'product-001', '按 A 写验收情境', dependencies=['A'])
        for tid, rid, model in [('A', 'run-fixture-A', 'SYNTHETIC-model-a'), ('B', 'run-fixture-B', 'SYNTHETIC-model-b')]:
            run(tid, rid, model)
            path = 'management/instances/' + task(tid)['executor'] + '/workspace/' + tid + '-候选.md'
            write(path, '# ' + tid + ' 候选（合成）\n\n只用已确定的规则；匿名与附件上限待人决定。\n')
            call('hand_over', task(tid)['executor'], run=rid, evidence=[path], summary='合成：自检完成')
            call('launch_exit', 'launcher', id=rid, exit_code=0)
            t = task(tid)
            call('review', task_id=tid, expected_revision=t['revision'], outcome='passed', criteria_checked=t['criteria'], evidence=[path])
            call('transition', task_id=tid, expected_revision=task(tid)['revision'], state='done', reason='合成：检验通过，采用')
        pm.render(root)
    else:
        create('W', 'product-001', '意见提交的异常与提示候选')
        run('W', 'run-fixture-W', 'SYNTHETIC-model-a')
        write('management/instances/product-001/runs/run-fixture-W.md', '\n'.join([
            '# 任务包 run-fixture-W（平台运行：执行）', '',
            '你是本项目的 product-001（产品，T7，master）。平台为下面的事拉起你；只做这件事，做完或受阻就结束本次运行。', '',
            '- 工作目录是项目根目录。先读：kit/.agents/skills/matrix-product/SKILL.md；management/instances/product-001/profile.md；'
            '其余规则按技能的指引索引用到时再打开。汇报只用下面写好的命令，不必读任务工具的说明；不搜索项目里的运行记录。',
            '- 只写自己的工作区 management/instances/product-001/workspace/ 与登记的写入范围，检查点也放在工作区。不联网，不安装软件，不启动其他 Agent，不改别人的成果与记录。',
            '- 任务工具：python3 kit/matrix/orchestration/tools/pm_tasks.py --project . --command <命令文件>（命令文件写在你的工作区），actor 写 product-001。', '',
            '## 任务 W：意见提交的异常与提示候选', '', '- 目标：意见提交的异常与提示候选', '- 输入：BRIEF.md', '- 成果：意见提交的异常与提示候选（工作区内）',
            '- 判据：只用 BRIEF.md 已确定的规则；未定的列为待人决定', '- 下一步：制作候选', '', '## 回报', '',
            '- 交出（自检完成）：{"op":"hand_over","actor":"product-001","event_id":"run-fixture-W-handover","run":"run-fixture-W",'
            '"evidence":["<成果与证据的路径>"],"summary":"<一句话说明>"}',
            '- 受阻：{"op":"report_blocked","actor":"product-001","event_id":"run-fixture-W-blocked","run":"run-fixture-W","reason":"<卡在哪、需要谁做什么>"}',
            '- 不写"完成"：交出后由派发者检验、采用。', '']))
    layout.adapt(root)
