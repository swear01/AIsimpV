#!/usr/bin/env python3
"""Paired timings of the frozen manual rewrites and saved joint LLM candidate."""
import argparse
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rtl_relate import wednesday as w
from rtl_relate.formal import _run, prove_rtl
from rtl_relate.frontend import export_rtl
from rtl_relate.ir import digest, load_json

TASKS = (*w.TASKS, 'J1-skid8')
WARMUPS, REPEATS, BUDGET = 2, 8, 900


def save(path, value):
    path.write_text(json.dumps(value, indent=2, default=str) + '\n')


def prepare(task, out):
    if task != 'J1-skid8':
        case = w.prepare(task, 'good', out)
        for role in ('concrete', 'abstract'):
            case[role + '_source'] = out / role / 'normalized.v'
            case[role + '_parameters'] = {}
        w.validate_case(task, case, out)
        frozen = next(row for row in load_json(ROOT / 'docs/reports/data/manual-summary.json')['rows']
                      if row['task_id'] == task and row['variant'] == 'good')
        for name in ('concrete', 'abstract', 'contract', 'certificate'):
            if digest(case[name]) != frozen[name + '_sha256']:
                raise ValueError(f'frozen {task} {name} changed')
        return case
    candidate = ROOT / 'fixtures/public/llm_skid8'
    provenance = load_json(candidate / 'provenance.json')
    saved = load_json(ROOT / 'docs/reports/data/llm-reproduction.json')['checks'][1]
    for name, expected in saved['candidate_sha256'].items():
        if w.sha(candidate / name) != expected or provenance['source_hashes'][name] != expected:
            raise ValueError(f'saved joint candidate changed: {name}')
    entry = next(row for row in load_json(ROOT / 'fixtures/public/sources.json')['tasks']
                 if row['id'] == 'R2-skid8')
    contract = load_json(ROOT / entry['contract']['path'])
    if digest(contract) != entry['contract']['sha256'] or w.sha(ROOT / entry['concrete']['path']) != entry['concrete']['sha256']:
        raise ValueError('joint baseline or contract changed')
    concrete = export_rtl(ROOT / entry['concrete']['path'], entry['top'], out / 'concrete',
                          clock='i_clk', parameters=entry['parameters'])
    abstract = export_rtl(candidate / 'abstract.v', 'abstract_design', out / 'abstract',
                          clock='i_clk', nondet=('z',))
    return dict(concrete=concrete, abstract=abstract, contract=contract,
                certificate=load_json(candidate / 'certificate.json'),
                concrete_source=out / 'concrete/normalized.v',
                abstract_source=out / 'abstract/normalized.v',
                concrete_top=entry['top'], abstract_top='abstract_design', nondet=['z'])


def stats(values):
    return dict(values=values, median=statistics.median(values),
                minimum=min(values), maximum=max(values))


def summarize(rows):
    results = {}
    for task in TASKS:
        measured = [row for row in rows if row['task'] == task and not row['warmup']]
        result = {'count': len(measured), 'status': 'INCOMPLETE'}
        if len(measured) == REPEATS and all(row['status'] == 'PASS' for row in measured):
            result.update(status='COMPLETE', metrics={name: stats([row[name] for row in measured]) for name in (
                'concrete_property', 'abstract_property', 'concrete_solver_processes',
                'abstract_solver_processes', 'frontend', 'certificate', 'validation_path')})
            result['comparisons'] = {}
            for name, baseline, alternative in (
                    ('property', 'concrete_property', 'abstract_property'),
                    ('solver_processes', 'concrete_solver_processes', 'abstract_solver_processes'),
                    ('known_candidate_validation', 'concrete_property', 'validation_path')):
                result['comparisons'][name] = {
                    'paired_speedup_C_over_A': stats([row[baseline] / row[alternative] for row in measured]),
                    'paired_seconds_saved': stats([row[baseline] - row[alternative] for row in measured]),
                    'alternative_faster_pairs': sum(row[alternative] < row[baseline] for row in measured)}
        results[task] = result
    return results


def measure(task, index, root, deadline, bindings):
    started = time.monotonic()
    out = root / f'round-{index:02d}' / task
    out.mkdir(parents=True)
    order = ['concrete', 'abstract'] if (index + TASKS.index(task)) % 2 == 0 else ['abstract', 'concrete']
    row = dict(task=task, round=index, warmup=index < WARMUPS, order=order,
               status='ERROR', stages={}, load_start=os.getloadavg())
    try:
        if time.monotonic() >= deadline:
            raise TimeoutError('run-wide budget exhausted')
        frontend = out / 'frontend'
        frontend.mkdir()
        process, _ = _run([sys.executable, str(Path(__file__).resolve()), '--prepare', task,
                           '--out', str(frontend)], out, 'export', min(deadline, time.monotonic() + 120))
        row['stages']['frontend'] = process
        row['frontend'] = process['seconds']
        if process['timeout'] or process['returncode'] != 0:
            raise ValueError('frontend failed; see raw export logs')
        case = load_json(frontend / 'case.json')
        binding = {name + '_sha256': digest(case[name]) for name in ('concrete', 'abstract', 'contract', 'certificate')}
        binding.update({role + '_source_sha256': w.sha(case[role + '_source']) for role in ('concrete', 'abstract')})
        row['binding'] = binding
        if task in bindings and bindings[task] != binding:
            raise ValueError('a frozen pair changed between repetitions')
        bindings[task] = binding
        before = time.monotonic()
        gate = w.bounded('certificate', [case[name] for name in ('concrete', 'abstract', 'contract', 'certificate')]
                         + [out / 'certificate'], {'timeout_ms': 10000}, out / 'gate-process',
                         min(deadline, before + 120))
        row['certificate'] = time.monotonic() - before
        row['certificate_status'] = gate['status']
        if gate['status'] != 'ACCEPTED':
            raise ValueError('certificate did not pass')
        for role in order:
            remaining = min(120, deadline - time.monotonic())
            if remaining <= 0:
                raise TimeoutError('run-wide budget exhausted')
            before = time.monotonic()
            proof = prove_rtl(case[role + '_source'], case[role + '_top'], case['contract'], out / role,
                              parameters=case.get(role + '_parameters'),
                              nondet=case.get('nondet', ()) if role == 'abstract' else (),
                              timeout_seconds=remaining, depth=20)
            row[role + '_property'] = time.monotonic() - before
            row['stages'][role] = proof
            w.validate_proof(proof, binding, role, case)
            if proof['status'] != 'SAFE':
                raise ValueError(f'{role} proof is {proof["status"]}')
            row[role + '_solver_processes'] = sum(proof['stages'][name]['seconds'] for name in ('base', 'induction'))
        c, a = (row['stages'][role] for role in ('concrete', 'abstract'))
        if c['tools'] != a['tools'] or bindings.setdefault('_tools', c['tools']) != c['tools']:
            raise ValueError('proof tools differ within or between pairs')
        row['validation_stage_subtotal'] = row['frontend'] + row['certificate'] + row['abstract_property']
        row['status'] = 'PASS'
    except Exception as error:
        row['error'] = f'{type(error).__name__}: {error}'
    finally:
        row.update(wall_seconds=time.monotonic() - started, load_end=os.getloadavg())
        if row['status'] == 'PASS':
            row['validation_path'] = row['wall_seconds'] - row['concrete_property']
            row['validation_orchestration'] = row['validation_path'] - row['validation_stage_subtotal']
        save(out / 'result.json', row)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--prepare', choices=TASKS, help=argparse.SUPPRESS)
    args = parser.parse_args()
    out = args.out.resolve()
    if args.prepare:
        save(out / 'case.json', prepare(args.prepare, out))
        return 0
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    source_hashes = {str(p.relative_to(ROOT)): w.sha(p) for p in [Path(__file__).resolve(),
                     ROOT / 'docs/timing_protocol.md', *sorted((ROOT / 'rtl_relate').glob('*.py'))]}
    metadata = dict(protocol_sha256=w.sha(ROOT / 'docs/timing_protocol.md'), source_sha256=source_hashes,
                    platform=platform.platform(), python=sys.version, processor=platform.processor(),
                    cpu_affinity=sorted(os.sched_getaffinity(0)), warmups=WARMUPS, repeats=REPEATS,
                    budget_seconds=BUDGET, depth=20, new_model_calls=0,
                    source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip())
    save(out / 'metadata.json', metadata)
    rows, bindings = [], {}
    for index in range(WARMUPS + REPEATS):
        offset = index % len(TASKS)
        for task in TASKS[offset:] + TASKS[:offset]:
            row = measure(task, index, out, started + BUDGET, bindings)
            rows.append(row)
            save(out / 'rows.json', rows)
            print(json.dumps({k: row[k] for k in ('task', 'round', 'warmup', 'status', 'wall_seconds')}
                             | ({'error': row['error']} if 'error' in row else {})), flush=True)
    unchanged = all(w.sha(ROOT / path) == expected for path, expected in source_hashes.items())
    summary = dict(results=summarize(rows), wall_seconds=time.monotonic() - started,
                   source_unchanged=unchanged, all_records_passed=all(r['status'] == 'PASS' for r in rows),
                   warmup_wall_seconds=sum(r['wall_seconds'] for r in rows if r['warmup']),
                   measured_wall_seconds=sum(r['wall_seconds'] for r in rows if not r['warmup']),
                   bindings=bindings)
    save(out / 'summary.json', summary)
    return 0 if unchanged and summary['all_records_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
