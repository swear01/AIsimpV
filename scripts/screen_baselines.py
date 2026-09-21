#!/usr/bin/env python3
"""Screen pinned public RTL using its original assertions, without certificate changes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import statistics
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rtl_relate.formal import _metrics, _run


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def prove(source, top, out, yosys, smtbmc, *, depth=20, timeout=45, parameters=None, defines=()):
    out.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    row = dict(status='ERROR', depth=depth, timeout=timeout, stages={},
               source_sha256=sha(source), load_start=os.getloadavg(), top=top,
               parameters=parameters or {}, defines=list(defines))
    try:
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', top):
            raise ValueError('invalid top identifier')
        for name in (*row['parameters'], *defines):
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
                raise ValueError('invalid parameter or define identifier')
        if any(type(value) is not int or value < 0 for value in row['parameters'].values()):
            raise ValueError('parameters must be nonnegative integers')
        shutil.copyfile(source, out / 'source.v')
        flags = ''.join(' -D ' + name for name in defines)
        params = ''.join(f' -chparam {name} {value}' for name, value in row['parameters'].items())
        script = (f'read_verilog -formal -sv{flags} source.v\nhierarchy -check -top {top}{params}\n'
                  f'prep -top {top} -flatten\nasync2sync\nchformal -lower\ndffunmap\nopt_clean\n'
                  'check -assert\nwrite_json model.json\nwrite_smt2 -wires model.smt2\n')
        (out / 'prepare.ys').write_text(script)
        deadline = start + timeout
        prep, _ = _run([yosys, '-Q', '-T', '-s', 'prepare.ys'], out, 'prepare', deadline)
        row['stages']['prepare'] = prep
        if prep['timeout']:
            raise TimeoutError('preparation exceeded shared budget')
        if prep['returncode'] != 0:
            raise ValueError('native RTL preparation failed; see logs')
        module = json.loads((out / 'model.json').read_text())['modules'][top]
        row['preprocessed'] = _metrics(module)
        cells = module['cells']
        assertions = [c for c in cells.values() if c['type'] == '$assert']
        if not assertions:
            raise ValueError('no assertion survived preparation')
        row['assertions'] = len(assertions)
        row['assumptions'] = sum(c['type'] == '$assume' for c in cells.values())
        row['constant_assertions'] = sum(all(isinstance(b, str) for b in c['connections']['A'])
                                         for c in assertions)
        row['memory_cells'] = sum(c['type'].startswith('$mem') for c in cells.values())
        row['model_sha256'] = sha(out / 'model.smt2')
        row['model_bytes'] = (out / 'model.smt2').stat().st_size
        for stage in ('base', 'induction'):
            command = [smtbmc, '-s', 'z3', '-t', str(depth), '--presat', '--noprogress',
                       '--dump-vcd', stage + '.vcd', '--dump-yw', stage + '.yw',
                       '--dump-smt2', stage + '.smt2']
            if stage == 'induction':
                command.append('-i')
            process, stdout = _run([*command, 'model.smt2'], out, stage, deadline)
            row['stages'][stage] = process
            statuses = re.findall(r'Status: (\w+)', stdout)
            status = statuses[-1] if statuses else None
            if process['timeout']:
                raise TimeoutError(stage + ' exceeded shared budget')
            if status == 'FAILED' and process['returncode'] == 1:
                row.update(status='CEX' if stage == 'base' else 'BOUNDED', reason=stage + ' failed')
                break
            if status != 'PASSED' or process['returncode'] != 0:
                row.update(status='UNKNOWN' if status in ('UNKNOWN', 'PREUNSAT') else 'ERROR',
                           reason=f'{stage} returned {status}')
                break
        else:
            row['status'] = 'SAFE'
    except TimeoutError as error:
        row.update(status='UNKNOWN', reason=str(error))
    except Exception as error:
        row.update(status='ERROR', reason=f'{type(error).__name__}: {error}')
    row.update(seconds=time.monotonic() - start, load_end=os.getloadavg())
    row['solver_seconds'] = sum(row['stages'][s]['seconds'] for s in ('base', 'induction')
                                if s in row['stages'])
    row['hashes'] = {p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file()}
    save(out / 'result.json', row)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, default=ROOT / 'fixtures/public/baseline_candidates.json')
    parser.add_argument('--tasks', nargs='+')
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--depth', type=int, help='override the catalog depth (AVR 20; FIFO 4)')
    parser.add_argument('--timeout', type=int, default=45)
    args = parser.parse_args()
    if args.repeats < 1 or (args.depth is not None and args.depth < 2) or args.timeout < 1:
        parser.error('positive repeats/timeout and depth >= 2 required')
    catalog = json.loads(args.catalog.read_text())
    selected = args.tasks or list(catalog['tasks'])
    if not set(selected) <= set(catalog['tasks']) or len(selected) != len(set(selected)):
        parser.error('unknown or duplicate task')
    yosys = os.environ.get('RTL_RELATE_YOSYS', str(ROOT / '.tools/yosys-venv/bin/yowasp-yosys'))
    smtbmc = str(Path(yosys).with_name('yowasp-yosys-smtbmc'))
    if not Path(yosys).is_file() or not Path(smtbmc).is_file() or not shutil.which('z3'):
        parser.error('pinned YoWASP and Z3 must already be installed')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    sources = out / 'sources'
    sources.mkdir()
    for task in selected:
        entry = catalog['tasks'][task]
        data = urllib.request.urlopen(entry['url'], timeout=30).read()
        path = sources / (task + '.v')
        path.write_bytes(data)
        if sha(path) != entry['sha256']:
            raise ValueError('upstream source hash mismatch: ' + task)
    save(out / 'catalog.json', catalog)
    metadata = dict(platform=platform.platform(), python=sys.version, cpu_affinity=sorted(os.sched_getaffinity(0)),
                    script_sha256=sha(__file__), catalog_sha256=sha(args.catalog), tasks=selected,
                    depth=args.depth, timeout=args.timeout, repeats=args.repeats, tools={})
    for label, executable, flags in [('yosys', yosys, ['-V']), ('z3', shutil.which('z3'), ['-version'])]:
        process, stdout = _run([executable, *flags], out, 'version_' + label, time.monotonic() + 15)
        if process['returncode'] != 0 or process['timeout']:
            raise ValueError(label + ' identity failed')
        metadata['tools'][label] = dict(path=executable, sha256=sha(executable), version=stdout.strip())
    metadata['tools']['smtbmc'] = dict(path=smtbmc, sha256=sha(smtbmc))
    package = Path(yosys).parent.parent
    metadata['tools']['distribution_files'] = {str(p.relative_to(package)): sha(p)
        for pattern in ('lib/python*/site-packages/yowasp_yosys/yosys.wasm',
                        'lib/python*/site-packages/yowasp_yosys/smtbmc.py',
                        'lib/python*/site-packages/yowasp_yosys/share/python3/smtio.py',
                        'lib/python*/site-packages/yowasp_yosys/share/python3/ywio.py')
        for p in package.glob(pattern)}
    save(out / 'metadata.json', metadata)
    rows = []
    for repeat in range(args.repeats):
        for task in selected[repeat % len(selected):] + selected[:repeat % len(selected)]:
            row = prove(sources / (task + '.v'), catalog['tasks'][task]['top'],
                        out / f'repeat-{repeat:02d}' / task, yosys, smtbmc,
                        depth=args.depth or catalog['tasks'][task].get('recommended_depth', 20), timeout=args.timeout,
                        parameters=catalog['tasks'][task].get('parameters'),
                        defines=catalog['tasks'][task].get('defines', ()))
            row.update(task=task, repeat=repeat)
            rows.append(row)
            save(out / 'rows.json', rows)
            print(json.dumps({k: row[k] for k in ('task', 'repeat', 'status', 'seconds', 'solver_seconds')}
                             | {'reason': row.get('reason')}), flush=True)
    summary = {}
    for task in selected:
        group = [r for r in rows if r['task'] == task]
        summary[task] = dict(statuses=[r['status'] for r in group], seconds=[r['seconds'] for r in group])
        if all(r['status'] == 'SAFE' for r in group):
            summary[task]['safe_median_seconds'] = statistics.median(r['seconds'] for r in group)
    save(out / 'summary.json', dict(results=summary, suite_seconds=time.monotonic() - start))
    return int(any(r['status'] == 'ERROR' for r in rows))


if __name__ == '__main__':
    raise SystemExit(main())
