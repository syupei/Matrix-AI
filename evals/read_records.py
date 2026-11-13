#!/usr/bin/env python3
"""Read dependencies from tool inputs, with separate content and name observations.

Paths resolve against the evaluated project, never the maintainer's live filesystem.
Unknown dynamic paths remain conservative. Tool output filenames are observations of
names, not evidence that every listed file's contents were loaded.
"""
import argparse
import ast
import json
import posixpath
import re
import shlex
from pathlib import Path

SCHEMA = 'matrix-read-set/2'


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)


def codex_tools(events):
    for e in events:
        item = e.get('item', {})
        if item.get('type') in {'command_execution', 'file_change', 'mcp_tool_call', 'tool_call'}:
            yield item


def claude_tools(events):
    def walk(value):
        if isinstance(value, dict):
            if value.get('type') == 'tool_use':
                yield value
            for v in value.values():
                yield from walk(v)
        elif isinstance(value, list):
            for v in value:
                yield from walk(v)
    yield from walk(events)


def project_directory(events, tools, supplied):
    if supplied:
        return posixpath.normpath(str(supplied))
    # Subagent workflow instructions identify the project even though the host cwd
    # in the transcript envelope is the orchestrator's directory.
    for event in events:
        message = event.get('message', {})
        if message.get('role') == 'user' or event.get('type') == 'user':
            for text in strings(message.get('content', event.get('content', []))):
                match = re.search(r'临时项目目录：\s*(/[^\s]+)', text)
                if match:
                    return posixpath.normpath(match[1])
    for event in events:
        if event.get('type') == 'result' and event.get('project_root'):
            return posixpath.normpath(event['project_root'])
    roots = set()
    for tool in tools:
        for text in strings(tool.get('input', tool.get('command', ''))):
            roots.update(m[1] for m in re.finditer(r'(/[^\s\"\'`;|<>]+?)/kit(?:/|[\s\"\']|$)', text))
    return next(iter(roots)) if len(roots) == 1 else '/__matrix_project__'


class Reads:
    def __init__(self, files, root):
        self.manifest = files
        self.root = root
        self.kit = posixpath.join(root, 'kit')
        self.files, self.scopes, self.names, self.name_scopes = set(), set(), set(), set()
        self.opaque = False
        self.seen = False

    def path(self, value, cwd, names=False):
        if not isinstance(value, str) or not value or value == '-':
            return None
        brace = re.search(r'\{([^{}]+,[^{}]+)\}', value)
        if brace:
            for part in brace[1].split(','):
                self.path(value[:brace.start()] + part + value[brace.end():], cwd, names)
            return None
        if re.search(r'\$|`|~|\{.*\}', value):
            self.opaque = True
            return None
        if cwd is None and not value.startswith('/'):
            self.opaque = True
            return None
        path = posixpath.normpath(value if value.startswith('/') else posixpath.join(cwd, value))
        # Wildcard matches are conservatively covered by their directory prefix.
        glob = re.search(r'[?*\[]', path)
        if glob:
            path = path[:glob.start()].rsplit('/', 1)[0] or '/'
        if path == self.kit or self.kit.startswith(path.rstrip('/') + '/'):
            rel = ''
        elif path.startswith(self.kit + '/'):
            rel = path[len(self.kit) + 1:]
        else:
            return None  # absolute or resolved project paths outside the kit
        values, scopes = (self.names, self.name_scopes) if names else (self.files, self.scopes)
        if glob or not rel or any(p.startswith(rel.rstrip('/') + '/') for p in self.manifest):
            scopes.add(rel)
        else:
            values.add(rel)  # absent files matter when later added
        return rel

    def shell(self, command, cwd):
        self.seen = True
        # Unwrap first: a quoted outer command may contain an entire heredoc.
        try:
            outer = shlex.split(command)
        except ValueError:
            outer = []
        if outer and posixpath.basename(outer[0]) in {'sh', 'bash', 'zsh'}:
            option = next((i for i, a in enumerate(outer[1:], 1) if a.startswith('-') and 'c' in a), None)
            if option is not None and option + 1 < len(outer):
                self.shell(outer[option + 1], cwd)
                return
        # Separate heredoc bodies from shell syntax. Writing a document containing
        # package links is not a content read. Inline programs are handled below.
        bodies = []
        lines = command.splitlines(keepends=True)
        clean = []
        n = 0
        while n < len(lines):
            line = lines[n]
            match = re.search(r'<<-?\s*[\'\"]?(\w+)[\'\"]?', line)
            if match:
                body = []
                n += 1
                while n < len(lines) and lines[n].strip() != match[1]:
                    body.append(lines[n]); n += 1
                bodies.append((''.join(body), bool(re.search(r'\b(?:python\d*|node|perl|ruby)\b', line))))
            clean.append(line)
            n += 1
        command = ''.join(clean)
        # A static find substitution has a known file domain, even if its exact
        # matches depend on the tree. The consuming command determines read kind.
        def find_sub(match):
            body = match[1]
            try: parts = shlex.split(body)
            except ValueError: return match[0]
            if not parts or parts[0] != 'find' or any(x in body for x in ('$','`',';','-exec')):
                return match[0]
            paths = []
            for value in parts[1:]:
                if value.startswith('-') or value == '|': break
                paths.append(value.rstrip('/') + '/**')
            return ' '.join(shlex.quote(p) for p in paths) if paths else match[0]
        command = re.sub(r'\$\(([^()]+)\)', find_sub, command)
        try:
            lexer = shlex.shlex(command, posix=True, punctuation_chars=';&|()< >')
            lexer.whitespace_split = True
            tokens = list(lexer)
        except ValueError:
            self.opaque = True
            return
        # Shell launchers in Codex traces wrap the actual command as one argument.
        if tokens and posixpath.basename(tokens[0]) in {'sh', 'bash', 'zsh'}:
            for i, token in enumerate(tokens[1:], 1):
                if token.startswith('-') and 'c' in token and i + 1 < len(tokens):
                    self.shell(tokens[i + 1], cwd)
                    return
        groups, current, piped = [], [], False
        for token in tokens + [';']:
            if token in {';', '&&', '||', '|', '&', '(', ')'}:
                if current:
                    groups.append((current, piped)); current = []
                piped = token == '|'
            else:
                current.append(token)
        bindings = {}
        for args, piped in groups:
            if args and args[0] == 'do': args = args[1:]
            if args and args[0] == 'done':
                bindings.clear(); continue
            if args and args[0] == 'for' and len(args) > 3 and args[2] == 'in':
                bindings[args[1]] = args[3:]; continue
            expanded = []
            for arg in args:
                arg = arg.replace('${PWD}', cwd or '$PWD').replace('$PWD', cwd or '$PWD')
                match = re.fullmatch(r'\$\{?(\w+)\}?', arg)
                if match and match[1] in bindings:
                    expanded.extend(bindings[match[1]])
                else:
                    for name, values in bindings.items():
                        if len(values) == 1:
                            arg = re.sub(r'\$\{' + re.escape(name) + r'\}|\$' + re.escape(name) + r'\b', lambda _: values[0], arg)
                    expanded.append(arg)
            args = expanded
            if len(args) == 1 and re.match(r'^[A-Za-z_]\w*=', args[0]):
                name, value = args[0].split('=', 1)
                bindings[name] = [value]
                continue
            if not args:
                continue
            executable = posixpath.basename(args[0])
            if executable in {'echo', 'printf', 'true', 'false', 'pwd', 'mkdir', 'touch'}:
                continue
            if executable == 'cd':
                target = args[1] if len(args) == 2 else None
                if not target or re.search(r'[$`~]', target) or target == '-':
                    self.opaque = True; cwd = None
                else:
                    cwd = posixpath.normpath(target if target.startswith('/') else posixpath.join(cwd or self.root, target))
                continue
            if executable in {'eval', 'source', '.'} or re.search(r'\$(?:[A-Za-z_0-9@*#?!-]|\{|\()|`', ' '.join(args)):
                self.opaque = True
                continue
            if executable in {'sh', 'bash', 'zsh'}:
                option = next((i for i, a in enumerate(args) if a.startswith('-') and 'c' in a), None)
                if option is not None and option + 1 < len(args):
                    self.shell(args[option + 1], cwd)
                else:
                    rel = self.path(args[-1], cwd)
                    if rel: self.scopes.add('matrix')
                    else: self.opaque = True
                continue
            # Redirection targets are writes. The input side of '<' is a read.
            operands = []
            for i, arg in enumerate(args[1:], 1):
                if arg in {'>', '>>', '<<', '<<<', '<', '>&', '2>&'}:
                    continue
                if i > 1 and args[i - 1] in {'>', '>>', '<<', '<<<', '>&', '2>&'}:
                    continue
                operands.append(arg)
            if executable == 'git' and any(x in args for x in ('status', 'ls-files', 'ls-tree')):
                target = args[args.index('-C') + 1] if '-C' in args else '.'
                self.path(target, cwd, names=True)
                continue
            names = executable in {'ls', 'find'} or (executable == 'rg' and '--files' in args)
            if executable == 'find' and any(a in {'-exec', '-execdir', '-ok'} for a in args):
                names = False  # the nested command may read every match
            if executable in {'ls', 'find', 'rg', 'grep'}:
                paths = []
                for index, arg in enumerate(operands[:-1]):
                    if arg in {'-f', '--file'}: self.path(operands[index + 1], cwd)
                skip = False
                pattern_pending = executable in {'rg', 'grep'} and not names
                takes_value = {'--glob', '-g', '--type', '-t', '--type-not', '-T', '--max-count', '-m', '-A', '-B', '-C', '--encoding', '-maxdepth', '-mindepth', '-name', '-iname', '-path', '-type'}
                for a in operands:
                    if skip:
                        skip = False; continue
                    if a in {'-e', '--regexp'}:
                        pattern_pending = False; skip = True; continue
                    if a in {'-f', '--file'}:
                        pattern_pending = False; skip = True; continue
                    if a in takes_value:
                        skip = True; continue
                    if a.startswith('-'):
                        continue
                    if pattern_pending:
                        pattern_pending = False; continue
                    paths.append(a)
                for path in paths or ([] if piped and not names and executable in {'rg', 'grep'} else ['.']):
                    self.path(path, cwd, names=names)
            else:
                for arg in operands:
                    if arg.startswith('-'):
                        continue
                    # Expressions/inline code are not paths. Static literal package
                    # paths embedded in those arguments still count below.
                    if not re.search(r'[\s\n]', arg):
                        program = executable.startswith('python') or executable in {'node', 'perl', 'ruby'}
                        if program and not (arg.endswith(('.py', '.js', '.rb', '.pl')) or 'kit/' in arg):
                            continue
                        rel = self.path(arg, cwd)
                        if rel and (executable.startswith('python') or executable in {'node', 'perl', 'ruby'} or arg == args[0]) and rel.endswith(('.py', '.js', '.sh')):
                            self.scopes.add('matrix')
                            self.scopes.add(posixpath.dirname(rel))
                if args[0].startswith(('kit/', './kit/', self.kit + '/')):
                    rel = self.path(args[0], cwd)
                    self.scopes.add('matrix')
                    if rel: self.scopes.add(posixpath.dirname(rel))
            # Command arguments with paths in code/quoted search expressions count,
            # but listing commands never become content reads through this fallback.
            for arg in operands:
                for m in re.finditer(r'(?:^|[\s\"\'=(])((?:/[^\s\"\';|]+/)?kit/[^\s\"\';|)]+)', arg):
                    self.path(m[1], cwd, names=names)
            if executable.startswith('python') or executable in {'node', 'perl', 'ruby'}:
                if '-c' in args:
                    self.program(args[args.index('-c') + 1], cwd)
        for body, program in bodies:
            if program: self.program(body, cwd)

    def program(self, text, cwd):
        # Resolve literal Python paths and assignments without executing code.
        try:
            tree = ast.parse(text)
        except SyntaxError:
            if re.search(r'readFile|open\(', text): self.opaque = True
            return
        values = {}
        assignments = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                for target in getattr(node, 'targets', [getattr(node, 'target', None)]):
                    if isinstance(target, ast.Name): assignments[target.id] = assignments.get(target.id, 0) + 1
        def literal(node):
            if isinstance(node, ast.Constant) and isinstance(node.value, str): return node.value
            if isinstance(node, ast.Name): return values.get(node.id)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'Path' and node.args:
                return literal(node.args[0])
            if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.Add)):
                left, right = literal(node.left), literal(node.right)
                if left is not None and right is not None:
                    return posixpath.join(left, right) if isinstance(node.op, ast.Div) else left + right
            return None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        values[target.id] = literal(node.value) if assignments[target.id] == 1 and node in tree.body else None
            if not isinstance(node, ast.Call): continue
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ''
            path = None
            if name in {'eval', 'exec', 'chdir', 'system', 'Popen'} or (name == 'run' and isinstance(node.func, ast.Attribute)):
                self.opaque = True
                continue
            if name == 'open':
                receiver = literal(node.func.value) if isinstance(node.func, ast.Attribute) else None
                mode_index = 0 if receiver is not None else 1
                mode = literal(node.args[mode_index]) if len(node.args) > mode_index else next((literal(k.value) for k in node.keywords if k.arg == 'mode'), 'r')
                if mode and any(c in mode for c in 'wax') and '+' not in mode: continue
                path = receiver if receiver is not None else literal(node.args[0]) if node.args else None
                if path is None and node.args and isinstance(node.args[0], ast.Subscript) and ast.unparse(node.args[0]).startswith('sys.argv'):
                    continue  # argv paths are counted by the shell argument parser
            elif name in {'read_text', 'read_bytes', 'glob', 'rglob', 'iterdir'} and isinstance(node.func, ast.Attribute):
                path = literal(node.func.value)
            elif name == 'spec_from_file_location' and len(node.args) > 1:
                path = literal(node.args[1])
                if path: self.scopes.add('matrix')
            else:
                continue
            if path is None:
                self.opaque = True
            else:
                self.path(path, cwd, names=name in {'glob', 'rglob', 'iterdir'})


def extract(events, runner, files, entry=None, project_root=None):
    tools = list(codex_tools(events) if runner == 'codex exec' else claude_tools(events) if runner in {'claude -p', 'claude subagent'} else [])
    root = project_directory(events, tools, project_root)
    reads = Reads(files, root)
    for tool in tools:
        inp = tool.get('input') or tool.get('arguments') or {}
        if isinstance(inp, str):
            try: inp = json.loads(inp)
            except ValueError: reads.opaque = True; continue
        command = tool.get('command') or inp.get('command') or inp.get('cmd')
        cwd = inp.get('cwd') or inp.get('workdir') or root
        if command:
            reads.shell(command, cwd)
            continue
        name = tool.get('name', '').split('__')[-1]
        if name in {'Read', 'Edit', 'Write', 'Grep', 'Glob'}:
            reads.seen = True
            if name == 'Write': continue
            names = name == 'Glob'  # Grep reads contents even when returning filenames.
            path = inp.get('file_path') if name in {'Read', 'Edit'} else inp.get('path', '.')
            if name == 'Glob' and str(inp.get('pattern', '')).startswith('/'):
                path = inp['pattern']
            reads.path(path, cwd, names=names)
        elif tool.get('type') == 'file_change':
            reads.seen = True
            for change in tool.get('changes', []): reads.path(change.get('path'), cwd)
        elif name not in {'SubagentHandback', 'TodoWrite', 'TaskUpdate'}:
            reads.opaque = True
    if reads.opaque:
        reads.scopes.add('')
    if entry:
        reads.files.add(entry)
    for scope in reads.scopes:
        reads.files.update(p for p in files if not scope or p.startswith(scope + '/'))
    return dict(schema=SCHEMA, complete=reads.seen, files=sorted(reads.files), scopes=sorted(reads.scopes),
                names=sorted(reads.names), name_scopes=sorted(reads.name_scopes))


def record_reads(run_path, record, files):
    run = json.loads(run_path.read_text())
    parts = []
    entry = record.get('entry') or ('.agents/skills/' + record['role'] + '/SKILL.md' if record.get('role') else None)
    for turn in record['turns']:
        events = [json.loads(line) for line in (run_path.parent / turn['events']).read_text().splitlines() if line.strip()]
        parts.append(extract(events, run['runner'], files, entry, turn.get('project_root')))
    return dict(schema=SCHEMA, complete=bool(parts) and all(p['complete'] for p in parts),
                **{k: sorted({item for part in parts for item in part[k]}) for k in ('files', 'scopes', 'names', 'name_scopes')})


def changes(old, new):
    return {p: 'added' if p not in old else 'deleted' if p not in new else 'modified'
            for p in set(old) | set(new) if old.get(p) != new.get(p)}


def intersects(reads, changed):
    # Legacy callers with only paths cannot prove an edit was content-only.
    name_changes = {p for p in changed if not isinstance(changed, dict) or changed[p] != 'modified'}
    return sorted(p for p in changed if p in reads['files'] or any(not s or p == s or p.startswith(s + '/') for s in reads['scopes'])
                  or (p in name_changes and (p in reads.get('names', []) or any(not s or p == s or p.startswith(s + '/') for s in reads.get('name_scopes', [])))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    args = parser.parse_args()
    files = json.loads(args.manifest.read_text())['files']
    run = json.loads(args.run.read_text())
    print(json.dumps({c['id']: record_reads(args.run, c, files) for c in run['cases']}, ensure_ascii=False, indent=2))
