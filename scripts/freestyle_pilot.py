#!/usr/bin/env python3
"""One isolated API request for the axilxbar rewrite or blind analysis pilot."""
import argparse
from difflib import unified_diff
import hashlib
import json
from pathlib import Path
import signal
import sys
import time
import tomllib
import urllib.error
import urllib.request
import uuid

from llm_pilot import NoRedirect, api_key, completion


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / 'experiments/freestyle_axilxbar'
LIMIT = 16 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def original_files(case, task, mode):
    return {(f'original/{name.removeprefix("original/")}' if mode == 'analyze' else name):
            (case / name).read_text()
            for name in task['files']}


def validated_output(mode, result, outputs=None):
    outputs = outputs or {'axilxbar_v': 'axilxbar.v', 'property_v': 'property.v',
                          'explanation': 'explanation.md', 'environment_changes': 'environment.md'}
    required = (set(outputs) if mode == 'rewrite' else {'summary', 'changes', 'open_questions'})
    if not isinstance(result, dict) or set(result) != required:
        raise ValueError(f'{mode} response fields must be {sorted(required)}')
    if mode == 'rewrite':
        if any(not isinstance(value, str) or len(value.encode()) > 512000 for value in result.values()):
            raise ValueError('rewrite values must be bounded strings')
    elif (not isinstance(result['summary'], str) or not isinstance(result['changes'], list)
          or not isinstance(result['open_questions'], list)):
        raise ValueError('analysis fields have invalid types')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('rewrite', 'repair', 'analyze'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, help='candidate directory for blind analysis')
    parser.add_argument('--provider', choices=('deepseek', 'meta'), default='deepseek')
    parser.add_argument('--case', type=Path, default=CASE, help='frozen experiment case')
    args = parser.parse_args()
    if args.mode in ('repair', 'analyze') and args.candidate is None:
        parser.error('--candidate is required for repair or analysis')
    if args.out.exists():
        parser.error('output directory already exists')
    case = args.case.resolve()
    task = json.loads((case / 'task.json').read_text())
    outputs = task.get('candidate_outputs', {
        'axilxbar_v': 'axilxbar.v', 'property_v': 'property.v',
        'explanation': 'explanation.md', 'environment_changes': 'environment.md'})
    files = original_files(case, task, args.mode)
    files['task.json'] = (case / 'task.json').read_text()
    if args.mode in ('repair', 'analyze'):
        candidate = args.candidate.resolve()
        for name in task.get('analysis_inputs', ('axilxbar.v', 'property.v', 'environment.md')):
            files[f'candidate/{name}'] = (candidate / name).read_text()
        files['candidate/frontend.txt'] = (candidate / 'frontend.txt').read_text()
        if args.mode == 'analyze':
            design_name = outputs['axilxbar_v']
            original_name = next(name for name in files
                                 if name.startswith('original/') and name.endswith('/' + design_name))
            files['candidate/diff.patch'] = ''.join(unified_diff(
                files[original_name].splitlines(True), files[f'candidate/{design_name}'].splitlines(True),
                original_name, f'candidate/{design_name}'))
        if args.mode == 'repair':
            frontend = json.loads(files['candidate/frontend.txt'])
            log_name = frontend.get('candidate', {}).get('log')
            if not log_name or not Path(log_name).is_file():
                raise FileNotFoundError('Yosys log is unavailable; rerun the frontend check '
                                        'on this candidate before repair')
            files['candidate/yosys.log'] = Path(log_name).read_text()
    prompt_name = 'analysis' if args.mode == 'analyze' else args.mode
    prompt = (case / f'{prompt_name}_prompt.txt').read_text()
    schema = ({key: '' for key in outputs} if args.mode != 'analyze'
              else {'summary': '', 'changes': [], 'open_questions': []})
    message = prompt + '\nReturn JSON with these exact fields:\n' + json.dumps(schema) + '\n\nFrozen input bundle:\n' + json.dumps(files)
    profile = tomllib.loads((ROOT / 'scripts/llm_models.toml').read_text())[args.provider]
    key = api_key(profile)
    payload = {'model': profile['model'], 'messages': [{'role': 'user', 'content': message}],
               'stream': False, 'response_format': {'type': 'json_object'}, **profile['parameters']}
    request_bytes = json.dumps(payload).encode()
    args.out.mkdir(parents=True)
    (args.out / 'request.json').write_bytes(request_bytes)
    (args.out / 'inputs.sha256.json').write_text(json.dumps(
        {name: digest(content.encode()) for name, content in files.items()}, indent=2) + '\n')
    headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}
    handlers = [NoRedirect]
    if profile.get('auth') == 'local-gateway':
        headers['x-opencode-session'] = uuid.uuid4().hex
        handlers.append(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(profile['endpoint'], data=request_bytes, headers=headers)
    started = time.monotonic()
    def expired(_signum, _frame):
        raise TimeoutError('600-second request budget exceeded')

    previous_alarm = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 600)
    try:
        try:
            response = urllib.request.build_opener(*handlers).open(request, timeout=600)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            metadata = {'http_status': response.status, 'provider': args.provider,
                        'endpoint': profile['endpoint'],
                        'requested_model': profile['model'], 'request_sha256': digest(request_bytes),
                        'gateway_headers': {name: response.headers[name]
                                            for name in ('X-Gateway-Active-Endpoint', 'X-Gateway-Attempt')
                                            if name in response.headers}}
            (args.out / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
            if isinstance(response, urllib.error.HTTPError):
                raise RuntimeError(f'API HTTP {response.status}')
            raw = response.read(LIMIT + 1)
        if len(raw) > LIMIT or (profile.get('api_key_env') and key.encode() in raw):
            raise ValueError('response is too large or contains credential')
        (args.out / 'response.json').write_bytes(raw)
        record = {}
        result = validated_output('analyze' if args.mode == 'analyze' else 'rewrite',
                                  json.loads(completion(json.loads(raw), record)), outputs)
        metadata.update({key: record.get(key) for key in ('response_model', 'response_id', 'usage', 'finish_reason')})
        metadata['response_sha256'] = digest(raw)
        metadata['elapsed_seconds'] = time.monotonic() - started
        (args.out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        if args.mode != 'analyze':
            candidate = args.out / 'candidate'
            candidate.mkdir()
            for key, name in outputs.items():
                (candidate / name).write_text(result[key])
        (args.out / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    except Exception as error:
        if (args.out / 'metadata.json').exists():
            metadata = json.loads((args.out / 'metadata.json').read_text())
            metadata['elapsed_seconds'] = time.monotonic() - started
            (args.out / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
        (args.out / 'error.txt').write_text(f'{type(error).__name__}: {error}\n')
        print((args.out / 'error.txt').read_text().strip(), file=sys.stderr)
        raise SystemExit(1)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_alarm)


if __name__ == '__main__':
    main()
