#!/usr/bin/env python3
"""Prepare and collect behavior turns that an orchestrating session runs as subagents ("claude subagent" runner).

The model under test is a fresh subagent per turn. This script does everything around it, as run.py does for a CLI:

  subagent_turns.py prepare --kit KIT --out OUT --case ID --turn N
      turn 0: a fresh project OUT/work/ID with the kit copied to kit/ and the case's fixture populated;
      every turn: OUT/inputs/ID-N.txt, the full input of that turn (the same wording as run.py, earlier turns of
      this case pasted in), and OUT/inputs/ID-N.prompt, the instruction to give the subagent.
  subagent_turns.py collect --kit KIT --out OUT --cases a,b --transcripts MAP.json
      copies each finished case's project files (all but kit/) to OUT/run/ID-artifacts and its replies to OUT/run/,
      ready for assemble_run.py --output OUT/run.

The subagent reads the input file, works only inside the project, writes its reply verbatim to OUT/replies/ID-N.md
and answers only "已保存". Replies are never edited here."""
import argparse, hashlib, importlib.util, json, shutil, sys
from read_records import claude_tools
from pathlib import Path

EVALS = Path(__file__).resolve().parent
SUITE = EVALS / 'cases/suite.json'


def spec(cid):
    return next(c for c in json.loads(SUITE.read_text(encoding='utf-8'))['cases'] if c['id'] == cid)


def resolve(kit, case):
    roles = case['role'] if isinstance(case['role'], list) else [case['role']]
    role = next((r for r in roles if (kit / '.agents/skills' / r / 'SKILL.md').is_file()), roles[-1])
    entry = next((e for e in case.get('entry', []) if (kit / e).is_file()), None)
    return role, entry


def prepare(a):
    kit, out, case = Path(a.kit).resolve(), Path(a.out).resolve(), spec(a.case)
    work = out / 'work' / case['id']
    (out / 'inputs').mkdir(parents=True, exist_ok=True); (out / 'replies').mkdir(parents=True, exist_ok=True)
    if a.turn == 0:
        if work.exists():
            raise SystemExit(f'{work} exists; a case starts from a fresh project')
        work.mkdir(parents=True)
        shutil.copytree(kit, work / 'kit', ignore=shutil.ignore_patterns('__pycache__'))
        if case.get('fixture'):
            fixture = EVALS / 'fixtures' / (case['fixture'] + '.py')
            if hashlib.sha256(fixture.read_bytes()).hexdigest() != case.get('fixture_sha256'):
                raise SystemExit('fixture changed; update suite')
            m = importlib.util.spec_from_file_location('fixed_fixture', fixture); mod = importlib.util.module_from_spec(m)
            m.loader.exec_module(mod); mod.populate(work.resolve(), case['id'])
    role, entry = resolve(kit, case)
    start = f'kit/{entry}' if entry else f'kit/.agents/skills/{role}/SKILL.md'
    # Same wording as run.py, so subagent turns and CLI turns get the same input.
    prompt = f"在此临时项目中使用 {start} 处理用户请求。读取所需本地规则。仅在此目录写本轮必要成果，不访问外部业务项目、不联网、不启动其他Agent。这里没有可用原生提问控件，使用技能允许的回退方式。只处理当前用户输入，等真实下一条消息，不替用户回答。\n"
    history = []
    for n in range(a.turn):
        reply = out / 'replies' / f"{case['id']}-{n}.md"
        if not reply.is_file():
            raise SystemExit(f'missing reply of turn {n}: {reply}')
        history += [{'role': 'user', 'text': case['turns'][n]}, {'role': 'assistant', 'text': reply.read_text(encoding='utf-8')}]
    if history:
        prompt += '此前真实对话：\n' + json.dumps(history, ensure_ascii=False) + '\n'
    prompt += '用户：' + case['turns'][a.turn]
    inp = out / 'inputs' / f"{case['id']}-{a.turn}.txt"
    inp.write_text(prompt, encoding='utf-8')
    reply = out / 'replies' / f"{case['id']}-{a.turn}.md"
    instruction = (f"你在一次行为评测中作为被测 Agent 运行，只处理一轮。\n\n"
                   f"1. 临时项目目录：{work} 。所有相对路径都相对这个目录（用 Bash 时先 cd 到这里，用文件工具时用绝对路径）。只在这个目录内读写，其中 kit/ 是被测的技能包。不读这个目录以外的文件，不联网，不启动其他 Agent。\n"
                   f"2. 读 {inp} ：那是这一轮的完整输入（开头是对你的要求，\"用户：\"后面是用户的原话）。严格按它处理，就像直接回复这位用户。\n"
                   f"3. 处理完后，把你给用户的完整回复原样写入 {reply} ：只写回复正文，不加任何评测说明。\n"
                   f"4. 最后只回答\"已保存\"。")
    (out / 'inputs' / f"{case['id']}-{a.turn}.prompt").write_text(instruction, encoding='utf-8')
    print(json.dumps({'case': case['id'], 'turn': a.turn, 'turns': len(case['turns']), 'role': role, 'prompt': str(out / 'inputs' / f"{case['id']}-{a.turn}.prompt")}, ensure_ascii=False))


def transcript(mapping, key, base):
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise SystemExit(key + ': transcript mapping missing; use {"case-0":"path/to/raw.jsonl"}')
    path = (base / value).resolve()
    if not path.is_file():
        raise SystemExit(key + ': raw transcript does not exist')
    raw = path.read_bytes()
    try:
        events = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
    except (ValueError, UnicodeError) as error:
        raise SystemExit(key + ': invalid raw JSONL transcript: ' + str(error))
    if not list(claude_tools(events)):
        raise SystemExit(key + ': raw transcript has no tool_use records')
    def results(value):
        if isinstance(value, dict):
            return value.get('type') == 'tool_result' or any(results(v) for v in value.values())
        return isinstance(value, list) and any(results(v) for v in value)
    if not results(events):
        raise SystemExit(key + ': raw transcript has no tool_result records')
    return raw, path


def collect(a):
    kit, out = Path(a.kit).resolve(), Path(a.out).resolve()
    map_path = Path(a.transcripts).resolve()
    mapping = json.loads(map_path.read_text(encoding='utf-8'))
    if not isinstance(mapping, dict):
        raise SystemExit('transcripts must be an object mapping case-turn to a raw JSONL path')
    prepared, assigned = [], set()
    # Validate every mapping before changing the collected evidence bundle.
    for cid in a.cases.split(','):
        case = spec(cid)
        turns = []
        for n in range(len(case['turns'])):
            key = f'{cid}-{n}'
            reply = out / 'replies' / (key + '.md')
            if not reply.is_file():
                raise SystemExit(key + ': reply missing')
            raw, source = transcript(mapping, key, map_path.parent)
            if source in assigned:
                raise SystemExit(key + ': each fresh subagent turn needs its own transcript')
            assigned.add(source)
            turns.append((key, reply, raw, source))
        if not (out / 'work' / cid).is_dir():
            raise SystemExit(cid + ': project directory missing')
        prepared.append((cid, turns))
    run = out / 'run'; run.mkdir(parents=True, exist_ok=True)
    for cid, turns in prepared:
        for key, reply, raw, source in turns:
            shutil.copy2(reply, run / reply.name)
            completion = dict(type='result', runner='claude subagent', recorded_by='orchestrator',
                              note='Collected original subagent transcript after its reply was saved',
                              case_turn=key, project_root=str(out / 'work' / cid),
                              transcript_sha256=hashlib.sha256(raw).hexdigest(), transcript_source=str(source))
            # Keep the raw prefix byte-for-byte, including tool_use and tool_result
            # envelopes. Only append a clearly attributed completion record.
            (run / (key + '.jsonl')).write_bytes(raw + (b'' if raw.endswith(b'\n') else b'\n') +
                                                json.dumps(completion, ensure_ascii=False).encode('utf-8') + b'\n')
        art = run / f'{cid}-artifacts'
        shutil.rmtree(art, ignore_errors=True); art.mkdir()
        for item in (out / 'work' / cid).iterdir():
            if item.name == 'kit':
                continue
            (shutil.copytree(item, art / item.name) if item.is_dir() else shutil.copy2(item, art / item.name))
        print(cid, 'collected', len(turns), 'turns with original tool traces')
    snapshot = run / 'suite.snapshot.json'
    snapshot.write_bytes(SUITE.read_bytes())
    files = json.loads((kit / 'MANIFEST.json').read_text())['files']
    context = dict(candidate_files=files, suite_snapshot={'path': snapshot.name, 'sha256': hashlib.sha256(snapshot.read_bytes()).hexdigest()})
    (run / 'comparison-context.json').write_text(json.dumps(context, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest='command', required=True)
    q = s.add_parser('prepare'); q.add_argument('--kit', required=True); q.add_argument('--out', required=True); q.add_argument('--case', required=True); q.add_argument('--turn', type=int, default=0)
    c = s.add_parser('collect'); c.add_argument('--kit', required=True); c.add_argument('--out', required=True); c.add_argument('--cases', required=True); c.add_argument('--transcripts', required=True, help='JSON mapping case-turn to the original subagent JSONL path; relative paths resolve beside the mapping')
    a = p.parse_args()
    {'prepare': prepare, 'collect': collect}[a.command](a)
