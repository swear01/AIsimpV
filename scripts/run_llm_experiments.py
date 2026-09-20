#!/usr/bin/env python3
"""Prepare audited inputs and run the two pre-registered, bounded Codex pilots."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
sys.dont_write_bytecode = True

from llm_pilot import initialize, generate, load, record_verification, file_hashes, save

CORE = ('__init__.py', 'checker.py', 'frontend.py', 'formal.py', 'ir.py', 'solver.py', 'properties.py', 'witness.py')
SYNTAX = '''# Frozen task and certificate interface
The JSON model's symbols map exact IDs to origin names, widths, signedness, and
kind (input, state, nondet). init and next define the synchronous transition;
observe defines public outputs. Do not bind identifiers by guesswork.

Certificate JSON has exactly these keys: version (integer 1), concrete_sha256,
abstract_sha256, contract_sha256, h, J, w. Each hash is SHA256 of the corresponding
JSON object serialized by Python json.dumps(obj,sort_keys=True,separators=(",",":"),
allow_nan=False). This differs from hashing pretty-printed file bytes.

h maps EVERY abstract state ID to an expression over current concrete states.
J is a Bool expression over current concrete states. w maps EVERY abstract nondet
ID to an expression over current concrete states and public inputs. There are no
abstract-state references in these expressions. Concrete state references have
form {"ref":"c.EXACT_CONCRETE_STATE_ID"}; witness public input references have
form {"ref":"u.PUBLIC_INPUT_PORT_NAME"}. Mapping keys are abstract symbol IDs
without a prefix. State mapping and J cannot depend on public inputs.

Constants: {"bool":true} or {"bool":false}; {"bv":NUMBER,"width":BITS} with unsigned
0 <= NUMBER < 2**BITS. Operations are {"op":NAME,"args":[EXPRESSIONS]}.
Bool-only unary not; Bool-only binary and/or/xor; equality eq (equal operand types,
Bool result); ite (Bool condition and equal-type branches); unary bvnot; binary
bvand/bvor/bvxor/add/sub (same-width BV arguments/results, modular arithmetic);
ult/ule (same-width unsigned BV arguments, Bool result); binary concat (high,low);
extract (one argument plus integer high/low fields); zext/sext (one argument plus
integer width field giving result width). Bool and BV1 are distinct. All listed
operations have the stated fixed arity. No Python or executable expressions.

The independent gate establishes nonempty concrete initialization, initial J,
one-step preservation of J, initial mapping, one-step matching using w, and
observation equality under J. Both designs share exactly the contract's public
inputs. The contract is immutable and clocks/reset/sampling cannot change.
Witness substitution is used only in the certificate harness. Property proof
on A keeps nondeterminism free on every step. A rejected certificate is not a bug.

RTL subset: one positive-edge clock with the exact contract clock name; explicit
constant initialization for every state; finite two-valued bitvectors; no memory,
multiple clocks, asynchronous reset, X/Z, latch, delay, initial processes beyond
constant initialization, assume/assert/cover, external modules, preprocessing
(backtick), or system task/function ($). Maximum candidate RTL or certificate
file size is 65536 bytes. The trusted frontend is Yosys 0.69 -> BTOR2; it may reject
unsupported constructs. Use /usr/bin/python3 if local calculations are useful.
'''

CERT_PROMPT = '''Read all files in this input bundle. Produce a valid h/J/w certificate for the
fixed concrete.json and abstract.json pair, respecting contract.json and syntax.md.
Derive the relationship yourself. Write only certificate.json in the candidate
path specified by the runner. The first response and every repair count as one
of at most four attempts; the total generation and verification budget is 900
seconds. You receive actual formal feedback between attempts. No gold certificate
or solution is available. Do not change either design or the contract.
'''

REWRITE_PROMPT = '''Read all files in this input bundle. Propose a simpler abstract RTL design and
a corresponding h/J/w certificate using syntax.md. Preserve all concrete behavior
visible under contract.json. The abstraction may change the internal state
representation and add nondeterminism, but it must preserve the frozen cycle,
clock, reset, input, observation and safety-property semantics.

Write abstract.v and certificate.json only in the candidate paths specified by
the runner. Use top module abstract_design and exactly the public input/output
ports and widths in contract.json plus its clock input. Additionally declare one
unconstrained input wire [7:0] z; this is the only registered nondeterministic port.
Do not constrain z. Its witness belongs only in the certificate.

The pre-registered successful rewrite must have fewer exported state bits than
the concrete design's 18 bits, pass the independent certificate gate, and prove
the frozen property with z free. Merely renaming registers is insufficient.
Choose the state representation and relationship yourself; there is no supplied
abstract design, mapping, invariant, witness or rewrite recipe.

The parent exports each new abstract.v to the actual transition model and symbol
manifest before checking the certificate. It provides this model, its canonical
hash and actual errors as feedback. Do not invent manifest IDs or assume hashes
will be patched for you. If the first abstract model is not yet known, a provisional
certificate may fail; such a submission still consumes an attempt. A repair can
retain exactly the previous RTL while correcting the certificate against the
returned model. A changed RTL is always re-exported; stale certificates fail.

The first response and every repair count toward a maximum of four attempts and
900 seconds of total generation, frontend and formal verification work. No gold
solution is available. Do not modify the contract or emit an acceptance verdict.
'''


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def prepare(source_root, qualification, workspace):
    source_root, qualification, workspace = map(lambda p: Path(p).resolve(), (source_root, qualification, workspace))
    gate = json.loads((qualification / 'gate/report.json').read_text())
    property_result = json.loads((qualification / 'property/formal.json').read_text())
    if gate['status'] != 'ACCEPTED':
        raise ValueError('fixed gold pair has not passed the certificate gate')
    if property_result['status'] != 'SAFE':
        raise ValueError('fixed gold abstraction property has not been proved')
    for name in ('concrete', 'abstract', 'contract'):
        obj = json.loads((qualification / f'{name}.json').read_text())
        canonical = hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        if canonical != gate[name + '_sha256']:
            raise ValueError(f'qualification {name} canonical hash mismatch')
        if name == 'contract' and canonical != property_result['contract_sha256']:
            raise ValueError('qualification property contract hash mismatch')
    for name in ('concrete', 'abstract'):
        actual = hashlib.sha256((qualification / f'frontend/{name}/normalized.v').read_bytes()).hexdigest()
        metadata = json.loads((qualification / f'frontend/{name}/frontend.json').read_text())
        if actual != metadata['normalized_sha256'] or (name == 'abstract' and actual != property_result['source_sha256']):
            raise ValueError(f'qualification {name} normalized RTL hash mismatch')
    workspace.mkdir(parents=True, exist_ok=False)
    snapshot = workspace / 'snapshot'
    (snapshot / 'rtl_relate').mkdir(parents=True)
    (snapshot / 'scripts').mkdir()
    for name in CORE:
        shutil.copyfile(source_root / 'rtl_relate' / name, snapshot / 'rtl_relate' / name)
    for name in ('llm_pilot.py', 'run_llm_experiments.py'):
        shutil.copyfile(Path(__file__).with_name(name), snapshot / 'scripts' / name)
    for name in ('concrete', 'abstract', 'contract'):
        shutil.copyfile(qualification / f'{name}.json', snapshot / f'{name}.json')
    for name in ('concrete', 'abstract'):
        shutil.copyfile(qualification / f'frontend/{name}/normalized.v', snapshot / f'{name}.v')
    for mode in ('certificate', 'rewrite'):
        bundle = workspace / f'bundle-{mode}'
        bundle.mkdir()
        for name in ('concrete.json', 'concrete.v', 'contract.json') + (('abstract.json', 'abstract.v') if mode == 'certificate' else ()):
            shutil.copyfile(snapshot / name, bundle / name)
        (bundle / 'syntax.md').write_text(SYNTAX)
        (workspace / f'prompt-{mode}.txt').write_text(CERT_PROMPT if mode == 'certificate' else REWRITE_PROMPT)
    write_json(workspace / 'audit.json', {'status': 'AWAITING_ROOT_AUDIT',
        'snapshot_sha256': file_hashes(snapshot),
        'bundles': {m: file_hashes(workspace / f'bundle-{m}') for m in ('certificate', 'rewrite')},
        'prompts': {m: hashlib.sha256((workspace / f'prompt-{m}.txt').read_bytes()).hexdigest() for m in ('certificate', 'rewrite')},
        'rewrite_success': 'gate ACCEPTED and free-choice property SAFE and exported state bits < 18',
        'no_gold_certificate_copied': True})
    for root in (snapshot, workspace / 'bundle-certificate', workspace / 'bundle-rewrite'):
        for path in root.rglob('*'):
            path.chmod(0o555 if path.is_dir() else 0o444)
        root.chmod(0o555)
    return workspace


def validate_candidate_rtl(source):
    content = Path(source).read_bytes()
    if len(content) > 65536 or b'`' in content or b'$' in content:
        raise ValueError('candidate RTL exceeds 65536 bytes or contains forbidden backtick/$')


def phase(snapshot, mode, candidate, out, action, seconds):
    # Called in a fresh subprocess; never import the changing development checkout.
    sys.path.insert(0, str(snapshot))
    from rtl_relate.ir import digest, load_json, symbols_of
    from rtl_relate.checker import check
    from rtl_relate.frontend import export_rtl
    from rtl_relate.formal import prove_rtl
    concrete, contract = (load_json(snapshot / f'{n}.json') for n in ('concrete', 'contract'))
    if action == 'export':
        source = candidate / 'abstract.v'
        validate_candidate_rtl(source)
        abstract = export_rtl(source, 'abstract_design', out / 'frontend', nondet=('z',), clock=contract['clock']['name'], timeout=max(0.1, seconds / 3))
        if [s['type'] for s in abstract['symbols'].values() if s['kind'] == 'nondet'] != [8]:
            raise ValueError('the sole registered nondeterministic port must be z:BV8')
        write_json(out / 'abstract.json', abstract)
        return {'status': 'EXPORTED', 'abstract_model': abstract, 'abstract_sha256': digest(abstract),
                'abstract_state_bits': sum(symbols_of(abstract, 'state').values())}
    abstract = load_json(snapshot / 'abstract.json' if mode == 'certificate' else out / 'abstract.json')
    if action == 'gate':
        if (candidate / 'certificate.json').stat().st_size > 65536:
            raise ValueError('candidate certificate exceeds 65536 bytes')
        certificate = load_json(candidate / 'certificate.json')
        return check(concrete, abstract, contract, certificate, out / 'gate', timeout_ms=min(10000, max(1, int((seconds - 12) * 1000 / 6))))
    if action == 'replay':
        from rtl_relate.witness import extract_counterexample
        from rtl_relate.properties import replay
        timeout = min(5000, max(1, int((seconds - 4) * 500)))
        extracted = extract_counterexample(abstract, contract, out / 'property', out / 'witness', timeout_ms=timeout)
        if extracted['status'] != 'VALIDATED':
            return {'status': 'ABSTRACT_CEX', 'replay_status': 'UNRESOLVED', 'extraction': extracted}
        concrete_replay = replay(concrete, contract, extracted['trace'], out / 'concrete-replay', timeout_ms=timeout)
        status = {'INFEASIBLE': 'SPURIOUS_TRACE', 'FEASIBLE': 'BUG'}.get(concrete_replay['status'], 'ABSTRACT_CEX')
        return {'status': status, 'extraction': extracted, 'concrete_replay': concrete_replay}
    source = snapshot / 'abstract.v' if mode == 'certificate' else candidate / 'abstract.v'
    top = 'skid_abstract' if mode == 'certificate' else 'abstract_design'
    return prove_rtl(source, top, contract, out / 'property', nondet=('z',), timeout_seconds=max(0.1, seconds - 1))


def evaluate(snapshot, mode, candidate, out, remaining):
    snapshot, candidate, out = (Path(p).resolve() for p in (snapshot, candidate, out))
    sys.path.insert(0, str(snapshot))
    from rtl_relate.formal import _run
    out.mkdir()
    deadline = time.monotonic() + remaining
    result = {'status': 'ERROR', 'stages': {}}
    actions = ([('export', 60)] if mode == 'rewrite' else []) + [('gate', 120), ('property', 120)]
    for action, cap in actions:
        budget = min(cap, deadline - time.monotonic())
        if budget <= 1:
            result.update(status='UNKNOWN', reason='shared pilot budget exhausted')
            break
        target = out / f'{action}-result.json'
        command = [sys.executable, str(snapshot / 'scripts/run_llm_experiments.py'), 'phase',
                   '--snapshot', str(snapshot), '--mode', mode, '--candidate', str(candidate),
                   '--out', str(out), '--action', action, '--seconds', str(budget), '--target', str(target)]
        row, _ = _run(command, out, action + '-process', time.monotonic() + budget)
        result['stages'][action] = row
        payload = json.loads(target.read_text()) if target.exists() and row['returncode'] == 0 and not row['timeout'] else {'status': 'UNKNOWN' if row['timeout'] else 'ERROR', 'reason': 'phase did not complete normally'}
        result[action] = payload
        status = payload['status']
        if action == 'export' and status != 'EXPORTED' or action == 'gate' and status != 'ACCEPTED':
            result.update(status=status, reason=payload.get('reason', action + ' failed'))
            break
        if action == 'property':
            bits = result.get('export', {}).get('abstract_state_bits', 18)
            result['status'] = 'SUCCESS' if status == 'SAFE' and (mode == 'certificate' or bits < 18) else ('NOT_REDUCED' if status == 'SAFE' else 'ABSTRACT_CEX' if status == 'CEX' else status)
            if status == 'CEX':
                actions.append(('replay', 30))
        if action == 'replay':
            result['status'] = payload['status']
    write_json(out / 'evaluation.json', result)
    return result


def run(workspace, mode):
    workspace = Path(workspace).resolve()
    snapshot = Path(__file__).resolve().parents[1]
    if snapshot.parent != workspace or not snapshot.name.startswith('snapshot'):
        raise ValueError('run the immutable snapshot script, not the development copy')
    audit_path = workspace / ('audit.json' if snapshot.name == 'snapshot' else snapshot.name + '-audit.json')
    audit = json.loads(audit_path.read_text())
    if audit['status'] != 'APPROVED_BY_ROOT':
        raise ValueError('root must audit the exact prompts and bundle before model calls')
    if file_hashes(snapshot) != audit['snapshot_sha256'] or file_hashes(workspace / f'bundle-{mode}') != audit['bundles'][mode]:
        raise ValueError('audited snapshot or bundle changed')
    prompt_path = workspace / f'prompt-{mode}.txt'
    if hashlib.sha256(prompt_path.read_bytes()).hexdigest() != audit['prompts'][mode]:
        raise ValueError('audited prompt changed')
    run_dir = workspace / f'run-{mode}'
    if run_dir.exists():
        _, ledger = load(run_dir)
        ledger['trusted'][str(snapshot)] = file_hashes(snapshot)
        ledger['human_intervention'].append({'type': 'runner_infrastructure_fix', 'description': 'Continue same budget/attempt ledger with separately frozen runtime disabling code_mode_host and unified_exec; filesystem/network permissions unchanged', 'snapshot': snapshot.name})
        save(run_dir, ledger)
    else:
        ledger = initialize(run_dir, workspace / f'bundle-{mode}', [snapshot], mode)
    prompt = prompt_path.read_text()
    if ledger['attempts']:
        last = ledger['attempts'][-1]
        previous = {p.name: p.read_text() for p in (run_dir / f'attempt-{last["number"]:02d}/candidate').iterdir()}
        prompt += '\nPrevious raw candidate:\n' + json.dumps(previous) + '\nActual independent verification feedback:\n' + json.dumps(last['verification'])
        prompt += '\nInfrastructure update: code_mode_host and unified_exec are disabled, with identical filesystem/network limits. Verify a permitted bundle read and candidate write through the actual tool before deriving the certificate. No relationship hints were supplied.\n'
    for _ in range(len(ledger['attempts']), 4):
        record = generate(run_dir, prompt)
        _, ledger = load(run_dir)
        candidate = run_dir / f'attempt-{record["number"]:02d}/candidate'
        started = time.monotonic()
        if record['status'] == 'GENERATED':
            feedback = evaluate(snapshot, mode, candidate, run_dir / f'evaluation-{record["number"]:02d}', max(0, 900 - ledger['charged_seconds']))
        else:
            feedback = {'status': record['status'], 'reason': 'generation did not complete normally'}
        record_verification(run_dir, feedback, time.monotonic() - started)
        print(json.dumps({'mode': mode, 'attempt': record['number'], 'status': feedback['status']}), flush=True)
        _, ledger = load(run_dir)
        if feedback['status'] == 'SUCCESS' or ledger['charged_seconds'] >= 900 or record['status'] == 'ISOLATION_OR_RUNNER_ERROR':
            break
        # Only this run's raw output and real verifier feedback enter its next fresh context.
        previous = {p.name: p.read_text() for p in candidate.iterdir()}
        prompt = prompt_path.read_text() + '\nPrevious raw candidate:\n' + json.dumps(previous) + '\nActual independent verification feedback:\n' + json.dumps(feedback) + '\nRepair using only this feedback; retain RTL exactly if only the certificate needs repair.\n'
    return load(run_dir)[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare')
    for name in ('source-root', 'qualification', 'workspace'):
        prep.add_argument('--' + name, type=Path, required=True)
    pilot = sub.add_parser('run')
    pilot.add_argument('--workspace', type=Path, required=True)
    pilot.add_argument('--mode', choices=('certificate', 'rewrite'), required=True)
    worker = sub.add_parser('phase')
    for name in ('snapshot', 'candidate', 'out', 'target'):
        worker.add_argument('--' + name, type=Path, required=True)
    worker.add_argument('--mode', choices=('certificate', 'rewrite'), required=True)
    worker.add_argument('--action', choices=('export', 'gate', 'property', 'replay'), required=True)
    worker.add_argument('--seconds', type=float, required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        print(prepare(args.source_root, args.qualification, args.workspace))
    elif args.command == 'run':
        run(args.workspace, args.mode)
    else:
        try:
            result = phase(args.snapshot, args.mode, args.candidate, args.out, args.action, args.seconds)
        except Exception as error:
            result = {'status': 'ERROR', 'reason': str(error)}
        write_json(args.target, result)


if __name__ == '__main__':
    main()
