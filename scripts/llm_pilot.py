#!/usr/bin/env python3
"""Bounded Codex candidate generation; the caller alone runs the trusted verifier."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import tempfile
import time
import tomllib


ALLOWED = {'certificate': ('certificate.json',), 'rewrite': ('abstract.v', 'certificate.json')}


def plain_path(path):
    path = Path(path).absolute()
    if '..' in path.parts:
        raise ValueError('parent traversal is forbidden')
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError(f'symlinks are forbidden: {path.name}')
    return path


def file_hashes(root):
    root = plain_path(root)
    paths = [root] if root.is_file() else sorted(root.rglob('*'))
    result = {}
    for path in paths:
        plain_path(path)
        if path.is_dir():
            continue
        if not stat.S_ISREG(path.stat().st_mode):
            raise ValueError('only regular files are allowed')
        result[str(path.relative_to(root)) if path != root else root.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not result:
        raise ValueError(f'empty trusted input: {root.name}')
    return result


def save(run, ledger):
    ledger['wall_seconds'] = time.time() - ledger['created_at_unix']
    payload = json.dumps(ledger, indent=2) + '\n'
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=run, prefix='.ledger-', delete=False) as output:
            temporary = Path(output.name)
            output.write(payload)
        os.replace(temporary, run / 'ledger.json')
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load(run):
    run = plain_path(run)
    ledger = json.loads((run / 'ledger.json').read_text())
    for path, expected in ledger['trusted'].items():
        if file_hashes(path) != expected:
            raise ValueError(f'trusted input changed: {Path(path).name}')
    return run, ledger


def initialize(run, bundle, trusted, mode):
    run, bundle = plain_path(run), plain_path(bundle)
    if mode not in ALLOWED:
        raise ValueError('unsupported pilot mode')
    inputs = file_hashes(bundle)
    if any(part.startswith('.') or part in {'AGENTS.md', 'SKILL.md'}
           for name in inputs for part in Path(name).parts):
        raise ValueError('bundle must contain task inputs only, without config or agent rules')
    config_path = Path.home() / '.codex/config.toml'
    config = tomllib.loads(config_path.read_text())
    if config.get('model_provider', 'openai') != 'openai':
        raise ValueError('pilot supports the already configured OpenAI Codex provider only')
    model, effort = config.get('model'), config.get('model_reasoning_effort')
    if not model or not effort:
        raise ValueError('freeze explicit existing model and reasoning effort first')
    codex = shutil.which('codex')
    if not codex:
        raise ValueError('Codex CLI is not installed')
    # The npm wrapper's package holds the native sandbox executable.
    runtime = Path(codex).resolve()
    if runtime.suffix == '.js':
        runtime = runtime.parent.parent
    roots = [bundle, *(plain_path(p) for p in trusted)]
    if any(run == p or p in run.parents or run in p.parents for p in roots):
        raise ValueError('evidence and trusted inputs must be disjoint')
    snapshots = {str(p): file_hashes(p) for p in roots}
    run.mkdir(parents=True, exist_ok=False)
    ledger = {'version': 1, 'mode': mode, 'bundle': str(bundle), 'trusted': snapshots,
              'model': model, 'reasoning_effort': effort, 'provider': 'openai',
              'codex': codex, 'runtime': str(runtime),
              'codex_version': subprocess.check_output([codex, '--version'], text=True).strip(),
              'config_sha256': hashlib.sha256(config_path.read_bytes()).hexdigest(),
              'created_at_unix': time.time(), 'charged_seconds': 0.0,
              'max_attempts': 4, 'budget_seconds': 900, 'attempts': [],
              'cost_usd': None, 'human_intervention': [], 'transport': 'inline-json', 'isolation': 'REQUIRES_PROBE'}
    save(run, ledger)
    return ledger


def permissions(ledger, candidate):
    rules = {':minimal': 'read', ledger['runtime']: 'read', ledger['bundle']: 'read', str(candidate): 'write'}
    return ['-c', 'permissions.pilot.filesystem={' + ','.join(json.dumps(k) + '=' + json.dumps(v) for k, v in rules.items()) + '}',
            '-c', 'permissions.pilot.network.enabled=false']


def probe(run, ledger, candidate):
    # Probe exactly the profile generation will use, before consuming model budget.
    script = '''import pathlib, socket, sys
bundle, candidate, forbidden = map(pathlib.Path, sys.argv[1:])
assert (bundle / 'input.txt').read_text() == 'public input'
(candidate / 'certificate.json').write_text('{}')
for p, mode in [(bundle / 'input.txt', 'w'), (forbidden, 'r')]:
 try:
  with p.open(mode): pass
 except OSError: pass
 else: raise SystemExit('sandbox boundary failed: ' + str(p))
link = candidate / 'escape'
link.symlink_to(forbidden)
try: link.read_text()
except OSError: pass
else: raise SystemExit('symlink exposed hidden data')
link.unlink()
for p in [forbidden, forbidden.parent / 'parent-verdict.json']:
 try: p.write_text('tamper')
 except OSError: pass
try:
 s = socket.socket()
 s.settimeout(0.2)
 s.connect(('1.1.1.1', 443))
except OSError: pass
else: raise SystemExit('network boundary failed')
print('READ_WRITE_NETWORK_BOUNDARY_OK')
'''
    # A separate synthetic input avoids overwriting the real read-only bundle.
    public = run / 'boundary-input'
    public.mkdir()
    (public / 'input.txt').write_text('public input')
    forbidden = run / 'boundary-gold.txt'
    forbidden.write_text('do not expose')
    test_ledger = ledger | {'bundle': str(public)}
    command = [ledger['codex'], 'sandbox', *permissions(test_ledger, candidate), '-P', 'pilot', '-C', str(public),
               '--', '/usr/bin/python3', '-c', script, str(public), str(candidate), str(forbidden)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=20)
    (run / 'boundary.stdout.txt').write_text(result.stdout)
    (run / 'boundary.stderr.txt').write_text(result.stderr)
    if (result.returncode or 'READ_WRITE_NETWORK_BOUNDARY_OK' not in result.stdout
            or forbidden.read_text() != 'do not expose'
            or (run / 'parent-verdict.json').exists()
            or (public / 'input.txt').read_text() != 'public input'):
        raise ValueError('Codex sandbox boundary probe failed; generation refused')
    ledger['isolation'] = 'LOCAL_COMMAND_READ_WRITE_NETWORK_PROBE_PASSED'


def candidate_hashes(candidate, mode):
    candidate = plain_path(candidate)
    if {p.name for p in candidate.iterdir()} != set(ALLOWED[mode]):
        raise ValueError('candidate contains unauthorized paths')
    for path in candidate.iterdir():
        plain_path(path)
        if not path.is_file():
            raise ValueError('candidate outputs must be regular files')
    return file_hashes(candidate)



def materialize_response(text, candidate, mode):
    outputs = {'certificate_json': 'certificate.json'}
    if mode == 'rewrite':
        outputs['abstract_rtl'] = 'abstract.v'
    response = json.loads(text)
    if (not isinstance(response, dict) or set(response) != set(outputs)
            or any(not isinstance(v, str) or len(v.encode()) > 65536 for v in response.values())):
        raise ValueError('response does not match the bounded string output schema')
    candidate_hashes(candidate, mode)
    directory = os.open(candidate, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for key, name in outputs.items():
            descriptor = os.open(name, os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            try:
                output = os.fdopen(descriptor, 'wb')
            except BaseException:
                os.close(descriptor)
                raise
            with output:
                info = os.fstat(output.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ValueError('candidate output must be a private regular file')
                output.truncate(0)
                output.write(response[key].encode('utf-8'))
    finally:
        os.close(directory)


def generate(run, prompt):
    run, ledger = load(run)
    if len(ledger['attempts']) >= ledger['max_attempts']:
        raise ValueError('four-attempt budget exhausted')
    if ledger['attempts'] and 'verification' not in ledger['attempts'][-1]:
        raise ValueError('parent must record the previous verification before generating again')
    remaining = ledger['budget_seconds'] - ledger['charged_seconds']
    if remaining <= 0:
        raise ValueError('900-second shared budget exhausted')
    attempt = run / f'attempt-{len(ledger["attempts"]) + 1:02d}'
    candidate = attempt / 'candidate'
    record = {'number': len(ledger['attempts']) + 1, 'status': 'RUNNING', 'usage': None}
    ledger['attempts'].append(record)
    save(run, ledger)  # Reserve the attempt even if the process crashes.
    started = time.monotonic()
    try:
        attempt.mkdir()
        candidate.mkdir()
        for name in ALLOWED[ledger['mode']]:
            (candidate / name).write_text('')
        if ledger['isolation'] == 'REQUIRES_PROBE':
            probe(run, ledger, candidate)
            (candidate / 'certificate.json').write_text('')
        bundle = {name: (Path(ledger['bundle']) / name).read_text()
                  for name in ledger['trusted'][ledger['bundle']]}
        bindings = {name.removesuffix('.json') + '_sha256': hashlib.sha256(
            json.dumps(json.loads(content), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
            for name, content in bundle.items() if name in {'concrete.json', 'abstract.json', 'contract.json'}}
        outputs = {'certificate_json': 'certificate.json'}
        if ledger['mode'] == 'rewrite':
            outputs['abstract_rtl'] = 'abstract.v'
        schema = {'type': 'object', 'additionalProperties': False,
                  'properties': {key: {'type': 'string'} for key in outputs}, 'required': list(outputs)}
        schema_path = attempt / 'output-schema.json'
        schema_path.write_text(json.dumps(schema, indent=2) + '\n')
        instructions = ('All task data is inline below. DO NOT CALL TOOLS or read files; no tools are needed. '
            'Return only the structured JSON response: certificate_json is the exact certificate file text'
            + (' and abstract_rtl is the exact RTL file text' if ledger['mode'] == 'rewrite' else '')
            + '. The parent materializes these strings verbatim and independently verifies them; do not emit a verdict. '
            'This transport instruction replaces file-writing instructions below without changing the task.\n\n'
            + prompt + '\nCanonical input JSON bindings (metadata only):\n' + json.dumps(bindings)
            + '\nComplete audited input bundle, filename -> exact content:\n' + json.dumps(bundle))
        record_inputs = {'bundle_file_sha256': ledger['trusted'][ledger['bundle']], 'canonical_bindings': bindings}
        (attempt / 'inline-inputs.json').write_text(json.dumps(record_inputs, indent=2) + '\n')
        (attempt / 'prompt.txt').write_text(instructions)
        command = [ledger['codex'], 'exec', '--ignore-user-config', '--ignore-rules', '--ephemeral',
                   '--skip-git-repo-check', '--json', '--color', 'never', '-C', ledger['bundle'],
                   '-o', str(attempt / 'final.txt'), '-m', ledger['model'],
                   '-c', 'model_reasoning_effort=' + json.dumps(ledger['reasoning_effort']),
                   '-c', 'approval_policy="never"', '-c', 'default_permissions="pilot"',
                   '-c', 'project_doc_max_bytes=0', '-c', 'web_search="disabled"',
                   '-c', 'memories.use_memories=false', '-c', 'memories.generate_memories=false',
                   '-c', 'shell_environment_policy.inherit="none"',
                   '--disable', 'apps', '--disable', 'plugins', '--disable', 'hooks',
                   '--disable', 'multi_agent', '--disable', 'multi_agent_v2',
                   '--disable', 'code_mode_host', '--disable', 'unified_exec', '--disable', 'shell_tool',
                   '--output-schema', str(schema_path),
                   '--enable', 'skip_host_skill_discovery', *permissions(ledger, candidate), '-']
        (attempt / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
        environment = {k: v for k, v in os.environ.items() if k in
                       {'PATH', 'HOME', 'USER', 'LOGNAME', 'SHELL', 'LANG', 'LC_ALL', 'TERM',
                        'SSL_CERT_FILE', 'SSL_CERT_DIR', 'HTTPS_PROXY', 'HTTP_PROXY', 'ALL_PROXY', 'NO_PROXY'}}
        with (attempt / 'events.jsonl').open('w') as stdout, (attempt / 'stderr.txt').open('w') as stderr:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                       text=True, env=environment, start_new_session=True)
            try:
                process.communicate(instructions, timeout=max(0, remaining - (time.monotonic() - started)))
                record['returncode'] = process.returncode
                record['status'] = 'GENERATED' if process.returncode == 0 else 'GENERATION_ERROR'
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
                record['status'] = 'TIMEOUT'
        for line in (attempt / 'events.jsonl').read_text().splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get('type') == 'turn.completed':
                record['usage'] = event.get('usage')
        if record['status'] == 'GENERATED':
            try:
                materialize_response((attempt / 'final.txt').read_text(), candidate, ledger['mode'])
            except (OSError, ValueError) as exc:
                record.update(status='CANDIDATE_FORMAT_ERROR', error=str(exc))
        record['transport'] = 'inline-json'
        record['candidate_sha256'] = candidate_hashes(candidate, ledger['mode'])
        load(run)  # Recheck C, contracts, checker and harness after generation.
    except Exception as exc:
        record['status'] = 'ISOLATION_OR_RUNNER_ERROR'
        record['error'] = str(exc)
    finally:
        record['generation_seconds'] = time.monotonic() - started
        ledger['charged_seconds'] += record['generation_seconds']
        save(run, ledger)
    return record


def record_verification(run, feedback, seconds):
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError('verification cost must be a finite nonnegative number')
    run, ledger = load(run)
    if not ledger['attempts'] or 'verification' in ledger['attempts'][-1]:
        raise ValueError('no unverified attempt')
    attempt = ledger['attempts'][-1]
    if attempt['status'] == 'RUNNING':
        raise ValueError('generation has not terminated')
    if attempt['status'] == 'ISOLATION_OR_RUNNER_ERROR' and 'candidate_sha256' not in attempt:
        if feedback.get('status') != 'ISOLATION_OR_RUNNER_ERROR':
            raise ValueError('infrastructure failure requires infrastructure error feedback')
    elif candidate_hashes(run / f'attempt-{attempt["number"]:02d}' / 'candidate', ledger['mode']) != attempt.get('candidate_sha256'):
        raise ValueError('raw candidate changed after generation')
    attempt['verification'] = feedback
    attempt['verification_seconds'] = seconds
    ledger['charged_seconds'] += seconds
    save(run, ledger)
    return attempt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    init = sub.add_parser('init')
    init.add_argument('--run', type=Path, required=True)
    init.add_argument('--bundle', type=Path, required=True)
    init.add_argument('--trusted', type=Path, action='append', required=True)
    init.add_argument('--mode', choices=ALLOWED, required=True)
    gen = sub.add_parser('generate')
    gen.add_argument('--run', type=Path, required=True)
    gen.add_argument('--prompt', type=Path, required=True)
    check = sub.add_parser('record-check')
    check.add_argument('--run', type=Path, required=True)
    check.add_argument('--feedback', type=Path, required=True)
    check.add_argument('--seconds', type=float, required=True)
    args = parser.parse_args()
    if args.action == 'init':
        result = initialize(args.run, args.bundle, args.trusted, args.mode)
    elif args.action == 'generate':
        result = generate(args.run, args.prompt.read_text())
    else:
        result = record_verification(args.run, json.loads(args.feedback.read_text()), args.seconds)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
