#!/usr/bin/env python3
"""Bounded native-RTL abstraction search, with immutable generation and proof logs."""
import argparse
import json
import math
from pathlib import Path
import shutil
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rtl_relate.formal import _run
from scripts import llm_pilot
from scripts.native_abstraction import (cut_candidates, cut_model, export_json, normalize,
    prepare_candidate, property_source, witnessed_product)
from scripts.screen_baselines import prove, save, sha

SYNTAX = '''The original RTL and normalized concrete_design are task inputs, not a solution.
The normalized model preserves symbolic/partial memory initialization. Original
assertions have exact A/EN outputs __ar_a and __ar_en; a violation is EN & ~A.
The independent property harness proves every enabled predicate on every cycle.
Original anyconst choices are exposed as the contract's constant_inputs: they
are fixed but arbitrary for the entire execution. All other inputs are free.

For the full search, return abstract_rtl (module abstract_design) with exactly
the frozen ports/directions/widths, plus any new nondeterministic input ports.
Do not use preprocessing, system tasks (only $signed/$unsigned/$clog2 are allowed),
assumptions/assertions/cover, internal anyseq/anyconst,
multiple clocks, negative edges or asynchronous resets/writes. Uninitialized
state/memory is allowed and remains unknown; never assume it has value zero.
Raw-byte preflight rejects forbidden tasks and backticks even in comments.
Maximum each output string is 65536 UTF-8 bytes. Choose the representation
yourself. Fewer state bits is not required; optimize actual proof cost.

The native certificate is JSON with exactly witnesses and invariants.
witnesses maps EVERY extra abstract input port to the exact name of a current
concrete signal from signal_manifest.json, of the same width. These witnesses
are used ONLY in an independent synchronous product; the final abstract
property sees free values on these inputs every cycle.
invariants is a list of optional Bool expressions over c.SIGNAL and a.SIGNAL
names from the concrete and actual prepared abstract netlists. They are checked
as additional assertions, NEVER assumptions. Both designs' initial states are
universally checked in the product. Use guarded relations when appropriate;
an unconstrained initial register is not known to equal a separately chosen one.

Expressions: {"ref":"c.EXACT_SIGNAL"}, {"bool":true},
{"bv":0,"width":8}, or {"op":"eq","args":[EXPR,EXPR]}.
Bool unary not, Bool binary and/or/xor; eq compares equal types and returns Bool;
ite takes Bool condition and equal-type branches. BV unary bvnot, BV binary
bvand/bvor/bvxor/add/sub (equal widths, modular); ult/ule (unsigned, Bool);
concat(high,low); extract with one argument and integer high/low fields;
zext/sext with one argument and integer width. Bool and BV1 are different.
No raw SMT/Verilog expressions in the certificate. Empty invariants is allowed.
The parent binds raw outputs and all immutable inputs by hashes, and never
repairs your RTL or semantic certificate. It returns actual errors, CEXs and
timings. Do not output hashes or verdicts in the certificate.
'''

FULL_PROMPT = '''Find an effective property-directed overapproximation of the supplied RTL.
You may change state representation and preserve relationships across signals.
Use the provided native certificate interface. No manually prepared abstraction
or gold certificate is provided. Seek a large reduction in proof time, subject
to complete independent correctness and property proofs. There are at most four
generations and 900 seconds total generation plus verification. Every failed
attempt counts. The same complete assertion set must be verified. Return the
requested structured output; the parent runs every tool independently.
'''

CUT_PROMPT = '''Select useful abstraction cutpoints using the original RTL, its assertions,
normalized RTL and eligible_cutpoints.json. Return certificate_json containing
exactly {"cuts":["EXACT_SIGNAL_NAME", ...]}. The trusted transformer replaces
the selected vector drivers with independent unconstrained inputs, preserving
every assertion/monitor and uncut initialization. Cuts must not overlap bits.
No hand-written abstract RTL is requested. On spurious counterexamples, refine
by restoring relevant cuts, or propose a different selection. Minimize measured
proof time. An empty set is permitted but is an unchanged baseline. Four calls
and 900 seconds of generation plus verification are available.
This is a NeuroAbs-inspired netlist-cutting comparison, not the original tool:
AST-local expression rewriting and its published CEX-reduction algorithm are
not reproduced. Your refinement is guided by the actual retained counterexample.
'''


def prepare_task(qualification, out, yosys, smtbmc):
    qualification, out = Path(qualification), Path(out)
    original = json.loads((qualification / 'result.json').read_text())
    if (original['status'] != 'SAFE' or sha(qualification / 'source.v') != original['source_sha256']
            or sha(qualification / 'model.json') != original['hashes']['model.json']):
        raise ValueError('qualified original proof and source/model hashes required')
    out.mkdir(parents=True, exist_ok=False)
    concrete, metadata = normalize(qualification / 'model.json', original['top'], out / 'normalized', yosys)
    metadata.update(depth=original['depth'], original_source_sha256=original['source_sha256'],
                    original_parameters=original['parameters'], original_defines=original['defines'])
    save(out / 'normalized/contract.json', metadata)
    save(out / 'qualification.json', original)
    source = out / 'normalized/design.v'
    target = out / 'baseline.v'
    target.write_text(property_source(source, concrete, metadata, 'concrete_design'))
    result = prove(target, 'native_property', out / 'baseline', yosys, smtbmc,
                   depth=metadata['depth'], timeout=60)
    if result['status'] != 'SAFE':
        raise ValueError('normalized original did not complete proof: ' + result['status'])
    bundle = out / 'bundle'
    bundle.mkdir()
    shutil.copyfile(source, bundle / 'concrete.v')
    shutil.copyfile(qualification / 'source.v', bundle / 'original.v')
    save(bundle / 'contract.json', {**metadata,
         'ports': {n: {'direction': p['direction'], 'width': len(p['bits'])}
                   for n, p in concrete['ports'].items()}, 'normalized_baseline_seconds': result['seconds']})
    save(bundle / 'signal_manifest.json', {n: {'width': len(p['bits'])}
         for n, p in concrete['netnames'].items() if n != metadata['clock']})
    save(bundle / 'eligible_cutpoints.json', cut_candidates(concrete))
    (bundle / 'syntax.md').write_text(SYNTAX)
    save(out / 'bundle-manifest.json', llm_pilot.file_hashes(bundle))
    print(json.dumps({'task': out.name, 'normalized_baseline': result['seconds'],
                      'status': result['status'], 'rtl_bytes': source.stat().st_size}), flush=True)


def evaluate(snapshot, task, candidate, out, arm, yosys, smtbmc, budget=180):
    """Executed as a bounded subprocess from the frozen source snapshot."""
    task, candidate, out = map(Path, (task, candidate, out))
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    deadline = started + budget
    result = {'status': 'ERROR', 'arm': arm}
    try:
        concrete = json.loads((task / 'normalized/design.json').read_text())['modules']['concrete_design']
        metadata = json.loads((task / 'normalized/contract.json').read_text())
        cert = json.loads((candidate / 'certificate.json').read_text())
        if arm in ('templates', 'neuroabs-inspired'):
            if set(cert) != {'cuts'}:
                raise ValueError('cut selection requires exactly cuts')
            abstract = cut_model(concrete, cert['cuts'])
            source = export_json(abstract, 'abstract_design', out / 'abstract', yosys, deadline)
            result['correctness'] = {'status': 'ACCEPTED_BY_CONSTRUCTION',
                                     'cuts': cert['cuts'], 'transformer_sha256': sha(snapshot / 'scripts/native_abstraction.py')}
            product = None
        else:
            source = candidate / 'abstract.v'
            abstract = prepare_candidate(source, out / 'abstract-prep', yosys, deadline)
            result['abstract_signals'] = {n: len(v['bits']) for n, v in abstract['netnames'].items()}
            product = witnessed_product(concrete, abstract, metadata, cert, out / 'product', yosys, deadline)
        result['preparation_seconds'] = time.monotonic() - started
        target = out / 'property.v'
        target.write_text(property_source(source, abstract, metadata, 'abstract_design'))
        depth = metadata['depth']
        prop = prove(target, 'native_property', out / 'property', yosys, smtbmc, depth=depth,
                     timeout=min(60, deadline - time.monotonic()))
        result['property'] = prop
        if prop['status'] == 'SAFE':
            if product:
                gate = prove(product, 'native_product', out / 'gate', yosys, smtbmc, depth=depth,
                             timeout=min(60, deadline - time.monotonic()))
                result['correctness'] = gate
                result['status'] = 'SUCCESS' if gate['status'] == 'SAFE' else 'CERTIFICATE_' + gate['status']
            else:
                result['status'] = 'SUCCESS' if cert['cuts'] else 'UNCHANGED'
        else:
            result['status'] = 'ABSTRACT_CEX' if prop['status'] == 'CEX' else prop['status']
        # Preserve complete logs on disk; feedback contains bounded excerpts only.
        for kind in ('property', 'gate'):
            for trace in (out / kind).glob('*.vcd'):
                result.setdefault('counterexamples', {})[kind + '/' + trace.name] = trace.read_text()[:20000]
    except TimeoutError as error:
        result.update(status='UNKNOWN', reason=str(error))
    except Exception as error:
        result.update(status='ERROR', reason=f'{type(error).__name__}: {error}')
    result['seconds'] = time.monotonic() - started
    save(out / 'evaluation.json', result)
    return result


def worker(snapshot, task, candidate, out, arm, yosys, smtbmc, budget):
    budget = min(180, budget)
    if budget <= 0:
        return {'status': 'UNKNOWN', 'reason': 'evaluation budget exhausted'}, 0
    out.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(snapshot / 'scripts/search_abstractions.py'), 'evaluate',
               '--snapshot', str(snapshot), '--task', str(task), '--candidate', str(candidate),
               '--out', str(out), '--arm', arm, '--yosys', yosys, '--smtbmc', smtbmc,
               '--budget', str(budget)]
    # Inner tool groups must reach their own deadlines and clean up before the
    # supervisor dies; killing only this Python process would orphan a solver.
    row, _ = _run(command, out.parent, out.name + '-process', time.monotonic() + budget + 5)
    target = out / 'evaluation.json'
    result = json.loads(target.read_text()) if target.exists() and row['returncode'] == 0 and not row['timeout'] else {
        'status': 'UNKNOWN' if row['timeout'] else 'ERROR', 'reason': 'evaluation worker did not finish'}
    return result, row['seconds']


def run(snapshot, task, out, arm, yosys, smtbmc):
    if arm == 'templates':
        out.mkdir(parents=True, exist_ok=False)
        options = json.loads((task / 'bundle/eligible_cutpoints.json').read_text())
        selected = sorted(options, key=lambda n: (-options[n]['width'], n))[:4]
        save(out / 'plan.json', {'template': 'single vector havoc', 'ordered_cuts': selected,
                                  'budget_seconds': 900, 'selection_before_results': True})
        rows = []
        deadline = time.monotonic() + 900
        for i, name in enumerate(selected):
            candidate = out / f'attempt-{i+1:02d}' / 'candidate'
            candidate.mkdir(parents=True)
            save(candidate / 'certificate.json', {'cuts': [name]})
            result, seconds = worker(snapshot, task, candidate, candidate.parent / 'verification', arm,
                                      yosys, smtbmc, deadline - time.monotonic())
            rows.append({'cut': name, 'seconds': seconds, 'result': result})
            save(out / 'results.json', rows)
            print(json.dumps({'arm': arm, 'attempt': i+1, 'status': result['status'], 'seconds': seconds}), flush=True)
        return
    ledger = llm_pilot.initialize(out, task / 'bundle', [snapshot, task / 'normalized'],
                                  'rewrite' if arm == 'ai' else 'certificate')
    ledger['arm'] = arm
    llm_pilot.save(out, ledger)
    prompt = FULL_PROMPT if arm == 'ai' else CUT_PROMPT
    for i in range(4):
        _, ledger = llm_pilot.load(out)
        if ledger['charged_seconds'] >= ledger['budget_seconds']:
            break
        generated = llm_pilot.generate(out, prompt)
        attempt = out / f'attempt-{i+1:02d}'
        _, ledger = llm_pilot.load(out)
        remaining = ledger['budget_seconds'] - ledger['charged_seconds']
        if generated['status'] == 'GENERATED' and remaining > 0:
            result, seconds = worker(snapshot, task, attempt / 'candidate', attempt / 'verification',
                                      arm, yosys, smtbmc, remaining)
        elif generated['status'] == 'GENERATED':
            result, seconds = {'status': 'UNKNOWN', 'reason': 'shared search budget exhausted before verification'}, 0
        else:
            result, seconds = {'status': generated['status'], 'reason': generated.get('error', 'no candidate')}, 0
        llm_pilot.record_verification(out, result, seconds)
        print(json.dumps({'arm': arm, 'attempt': i+1, 'status': result['status'],
                          'generation_seconds': generated['generation_seconds'], 'verification_seconds': seconds}), flush=True)
        feedback = {k: v for k, v in result.items() if k not in ('property', 'correctness')}
        for name in ('property', 'correctness'):
            if name in result:
                feedback[name] = {k: result[name].get(k) for k in ('status', 'seconds', 'reason')}
        previous = {p.name: p.read_text() for p in (attempt / 'candidate').iterdir() if p.is_file()}
        prompt = (FULL_PROMPT if arm == 'ai' else CUT_PROMPT) + '\nPrevious raw candidate:\n' + json.dumps(previous)
        prompt += '\nActual feedback:\n' + json.dumps(feedback)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'evaluate', 'run'))
    for name in ('task', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--snapshot', type=Path, default=ROOT)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--arm', choices=('templates', 'neuroabs-inspired', 'ai'))
    parser.add_argument('--yosys', required=True)
    parser.add_argument('--smtbmc', required=True)
    parser.add_argument('--budget', type=float, default=180, help='evaluation subprocess budget in seconds')
    args = parser.parse_args()
    if not math.isfinite(args.budget) or not 0 < args.budget <= 180:
        parser.error('--budget must be finite and in (0, 180]')
    args.snapshot, args.task, args.out = [p.resolve() for p in (args.snapshot, args.task, args.out)]
    if args.action == 'prepare':
        prepare_task(args.task, args.out, args.yosys, args.smtbmc)
    elif args.action == 'evaluate':
        if args.candidate is None:
            parser.error('--candidate required for evaluation')
        if args.arm is None:
            parser.error('--arm required for evaluation')
        evaluate(args.snapshot, args.task, args.candidate.resolve(), args.out, args.arm,
                 args.yosys, args.smtbmc, args.budget)
    else:
        if args.arm is None:
            parser.error('--arm required for search')
        run(args.snapshot, args.task, args.out, args.arm, args.yosys, args.smtbmc)


if __name__ == '__main__':
    main()
