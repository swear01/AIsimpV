#!/usr/bin/env python3
"""Bounded direct-API candidate generation; the caller alone runs the trusted verifier."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.request


CONFIG = Path(__file__).with_name('llm_models.toml')
PROVIDERS = ('deepseek', 'meta')


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
    if ledger.get('version') != 2:
        raise ValueError('legacy Codex run: use its frozen runner or start a new direct-API run')
    for path, expected in ledger['trusted'].items():
        if file_hashes(path) != expected:
            raise ValueError(f'trusted input changed: {Path(path).name}')
    return run, ledger


def initialize(run, bundle, trusted, mode, provider='meta'):
    run, bundle = plain_path(run), plain_path(bundle)
    if mode not in ALLOWED:
        raise ValueError('unsupported pilot mode')
    inputs = file_hashes(bundle)
    if any(part.startswith('.') or part in {'AGENTS.md', 'SKILL.md'}
           for name in inputs for part in Path(name).parts):
        raise ValueError('bundle must contain task inputs only, without config or agent rules')
    if provider not in PROVIDERS:
        raise ValueError('unsupported API provider')
    config_path = plain_path(CONFIG)
    profile = tomllib.loads(config_path.read_text())[provider]
    if not os.environ.get(profile['api_key_env']):
        raise ValueError('missing credential environment variable: ' + profile['api_key_env'])
    roots = [bundle, config_path, plain_path(__file__), *(plain_path(p) for p in trusted)]
    if any(run == p or p in run.parents or run in p.parents for p in roots):
        raise ValueError('evidence and trusted inputs must be disjoint')
    snapshots = {str(p): file_hashes(p) for p in roots}
    run.mkdir(parents=True, exist_ok=False)
    ledger = {'version': 2, 'mode': mode, 'bundle': str(bundle), 'trusted': snapshots,
              'provider': provider, 'model': profile['model'], 'api': profile,
              'reasoning_effort': profile['parameters']['reasoning_effort'],
              'config_sha256': hashlib.sha256(config_path.read_bytes()).hexdigest(),
              'created_at_unix': time.time(), 'charged_seconds': 0.0,
              'max_attempts': 4, 'budget_seconds': 900, 'attempts': [],
              'cost_usd': None, 'human_intervention': [],
              'transport': 'direct-chat-completions', 'isolation': 'NO_MODEL_TOOLS'}
    save(run, ledger)
    return ledger


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('API redirects are forbidden')


def api_request(run, number):
    """One HTTP request; the parent process enforces the total wall-time budget."""
    run, ledger = load(run)
    profile = ledger['api']
    attempt = run / f'attempt-{number:02d}'
    payload = (attempt / 'request.json').read_bytes()
    record = ledger['attempts'][number - 1]
    if hashlib.sha256(payload).hexdigest() != record['request_sha256']:
        raise ValueError('API request changed after capture')
    key = os.environ.get(profile['api_key_env'])
    if not key:
        raise ValueError('missing credential environment variable: ' + profile['api_key_env'])
    request = urllib.request.Request(profile['endpoint'], data=payload, headers={
        'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    with urllib.request.build_opener(NoRedirect).open(request, timeout=900) as response:
        raw = response.read(16 * 1024 * 1024 + 1)
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError('API response exceeds 16 MiB')
    if key.encode() in raw:
        raise ValueError('API response contains credential; refused to save')
    (attempt / 'response.json').write_bytes(raw)


def completion(response, record):
    record['usage'] = response.get('usage')
    record['response_model'] = response.get('model')
    record['response_id'] = response.get('id')
    choices = response.get('choices')
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError('expected exactly one API completion')
    choice = choices[0]
    record['finish_reason'] = choice.get('finish_reason')
    message = choice.get('message', {})
    if choice.get('finish_reason') != 'stop' or message.get('tool_calls') or message.get('refusal'):
        raise ValueError('API completion was truncated, refused, or requested tools')
    content = message.get('content')
    if not isinstance(content, str) or not content.strip():
        raise ValueError('API completion has no text content')
    return content


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
        instructions = ('All task data is inline below. '
            'Return only the structured JSON response: certificate_json is the exact certificate file text'
            + (' and abstract_rtl is the exact RTL file text' if ledger['mode'] == 'rewrite' else '')
            + '. The parent materializes these strings verbatim and independently verifies them; do not emit a verdict. '
            'No execution tools are available.\n\n'
            + 'Output JSON schema:\n' + json.dumps(schema) + '\n\n'
            + prompt + '\nCanonical input JSON bindings (metadata only):\n' + json.dumps(bindings)
            + '\nComplete audited input bundle, filename -> exact content:\n' + json.dumps(bundle))
        record_inputs = {'bundle_file_sha256': ledger['trusted'][ledger['bundle']], 'canonical_bindings': bindings}
        (attempt / 'inline-inputs.json').write_text(json.dumps(record_inputs, indent=2) + '\n')
        (attempt / 'prompt.txt').write_text(instructions)
        profile = ledger['api']
        if not os.environ.get(profile['api_key_env']):
            raise ValueError('missing credential environment variable: ' + profile['api_key_env'])
        request = {'model': ledger['model'], 'messages': [{'role': 'user', 'content': instructions}],
                   'stream': False, 'response_format': {'type': 'json_object'}, **profile['parameters']}
        request_path = attempt / 'request.json'
        request_path.write_text(json.dumps(request, indent=2) + '\n')
        record['request_sha256'] = hashlib.sha256(request_path.read_bytes()).hexdigest()
        save(run, ledger)
        command = [sys.executable, '-B', '-I', str(Path(__file__).resolve()), '_request',
                   '--run', str(run), '--number', str(record['number'])]
        (attempt / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
        environment = {k: v for k, v in os.environ.items() if k in
                       {'PATH', 'LANG', 'LC_ALL', 'SSL_CERT_FILE', 'SSL_CERT_DIR',
                        'HTTPS_PROXY', 'HTTP_PROXY', 'ALL_PROXY', 'NO_PROXY', profile['api_key_env']}}
        with (attempt / 'stderr.txt').open('w') as stderr:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=stderr, env=environment, start_new_session=True)
            try:
                process.communicate(timeout=max(0, remaining - (time.monotonic() - started)))
                record['returncode'] = process.returncode
                record['status'] = 'GENERATED' if process.returncode == 0 else 'GENERATION_ERROR'
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.communicate()
                record['status'] = 'TIMEOUT'
        if record['status'] == 'GENERATED':
            try:
                response_path = attempt / 'response.json'
                record['response_sha256'] = hashlib.sha256(response_path.read_bytes()).hexdigest()
                content = completion(json.loads(response_path.read_bytes()), record)
                (attempt / 'final.txt').write_text(content)
                materialize_response(content, candidate, ledger['mode'])
            except (OSError, ValueError, TypeError, AttributeError) as exc:
                record.update(status='CANDIDATE_FORMAT_ERROR', error=str(exc))
        elif record['status'] == 'GENERATION_ERROR':
            record['error'] = (attempt / 'stderr.txt').read_text().strip()
        record['transport'] = ledger['transport']
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
    infrastructure_failure = attempt['status'] == 'ISOLATION_OR_RUNNER_ERROR'
    if infrastructure_failure and feedback.get('status') != 'ISOLATION_OR_RUNNER_ERROR':
        raise ValueError('infrastructure failure requires infrastructure error feedback')
    if not infrastructure_failure or 'candidate_sha256' in attempt:
        if candidate_hashes(run / f'attempt-{attempt["number"]:02d}' / 'candidate', ledger['mode']) != attempt.get('candidate_sha256'):
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
    init.add_argument('--provider', choices=PROVIDERS, default='meta')
    gen = sub.add_parser('generate')
    gen.add_argument('--run', type=Path, required=True)
    gen.add_argument('--prompt', type=Path, required=True)
    check = sub.add_parser('record-check')
    check.add_argument('--run', type=Path, required=True)
    check.add_argument('--feedback', type=Path, required=True)
    check.add_argument('--seconds', type=float, required=True)
    worker = sub.add_parser('_request', help=argparse.SUPPRESS)
    worker.add_argument('--run', type=Path, required=True)
    worker.add_argument('--number', type=int, required=True)
    args = parser.parse_args()
    if args.action == '_request':
        try:
            api_request(args.run, args.number)
        except Exception as error:
            # Never print headers, credentials, or a provider's echoed error body.
            detail = f'HTTP {error.code}' if isinstance(error, urllib.error.HTTPError) else type(error).__name__
            print('API transport failed: ' + detail, file=sys.stderr)
            raise SystemExit(1)
        return
    if args.action == 'init':
        result = initialize(args.run, args.bundle, args.trusted, args.mode, args.provider)
    elif args.action == 'generate':
        result = generate(args.run, args.prompt.read_text())
    else:
        result = record_verification(args.run, json.loads(args.feedback.read_text()), args.seconds)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
