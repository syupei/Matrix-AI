#!/usr/bin/env python3
"""Conservative package read sets from actual Codex/Claude tool traces.

Directory observations include future additions under that directory. Opaque commands
fall back to the whole kit; absent tool traces are not proof that nothing was read.
"""
import argparse, json, posixpath, re
from pathlib import Path
SCHEMA='matrix-read-set/1'

def strings(value):
    if isinstance(value,str):yield value
    elif isinstance(value,dict):
        for v in value.values():yield from strings(v)
    elif isinstance(value,list):
        for v in value:yield from strings(v)

def codex_tools(events):
    for e in events:
        item=e.get('item',{})
        if item.get('type') in {'command_execution','file_change','mcp_tool_call','tool_call'}:yield item

def claude_tools(events):
    def walk(value):
        if isinstance(value,dict):
            if value.get('type')=='tool_use':yield value
            for v in value.values():yield from walk(v)
        elif isinstance(value,list):
            for v in value:yield from walk(v)
    yield from walk(events)

def extract(events, runner, files, entry=None):
    tools=list(codex_tools(events) if runner=='codex exec' else claude_tools(events) if runner in {'claude -p','claude subagent'} else [])
    observed=set();scopes=set();opaque=False
    for tool in tools:
        texts=list(strings(tool))
        if tool.get('type') in {'mcp_tool_call','tool_call'}:opaque=True
        command=tool.get('command') or tool.get('input',{}).get('command','')
        if command and 'kit' not in command and re.search(r'\b(?:python\d*|node|bash|sh|cat|sed|awk|head|tail|find|rg|ls)\b',command):opaque=True
        for text in texts:
            # A changed shell cwd or dynamic file expression cannot be resolved reliably.
            if re.search(r'\bcd\s+[^;&\n]*\bkit\b',text) or ('kit' in text and re.search(r'\$|\beval\b',text)):
                opaque=True
            if re.search(r'\b(?:ls|find|rg)\b',text) and not re.search(r'\bkit/',text):opaque=True
            # Include arguments AND tool results; outputs may reveal additional paths.
            for match in re.finditer(r'(?<![\w.-])kit(?:/([^\s\"\'`<>;|)\]}]+))?',text):
                rel=(match.group(1) or '').rstrip(':,')
                if re.search(r'[?*\[]',rel):
                    rel=rel[:re.search(r'[?*\[]',rel).start()].rsplit('/',1)[0] if '/' in rel else ''
                    scopes.add('' if posixpath.normpath(rel)=='.' else posixpath.normpath(rel));continue
                rel=posixpath.normpath(rel)
                if rel in {'.',''}:scopes.add('');continue
                if rel.startswith('../'):opaque=True;continue
                if rel in files:observed.add(rel)
                elif any(p.startswith(rel.rstrip('/')+'/') for p in files):scopes.add(rel.rstrip('/'))
                else:observed.add(rel)  # missing paths still matter if later added
            # Host Read/Grep/Glob paths relative to a package cwd are otherwise ambiguous.
        if not any('kit' in t for t in texts) and tool.get('name') in {'Read','Grep','Glob'}:opaque=True
    if opaque:scopes.add('')
    if entry:observed.add(entry)
    for scope in scopes:observed.update(p for p in files if not scope or p.startswith(scope+'/'))
    return {'schema':SCHEMA,'complete':bool(tools),'files':sorted(observed),'scopes':sorted(scopes)}

def record_reads(run_path, record, files):
    run=json.loads(run_path.read_text());events=[]
    for t in record['turns']:
        events.extend(json.loads(l) for l in (run_path.parent/t['events']).read_text().splitlines() if l.strip())
    entry=record.get('entry') or ('.agents/skills/'+record['role']+'/SKILL.md' if record.get('role') else None)
    return extract(events,run['runner'],files,entry)

def intersects(reads,changed):
    return sorted(p for p in changed if p in reads['files'] or any(not s or p.startswith(s+'/') for s in reads['scopes']))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);a=p.parse_args()
    files=json.loads(a.manifest.read_text())['files'];run=json.loads(a.run.read_text())
    print(json.dumps({c['id']:record_reads(a.run,c,files) for c in run['cases']},ensure_ascii=False,indent=2))
