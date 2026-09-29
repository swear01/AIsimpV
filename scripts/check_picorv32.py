#!/usr/bin/env python3
"""Elaborate the frozen upstream PicoRV32 ADD task with the original checker."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / 'experiments/picorv32/upstream'


def inline_file(sby, name):
    marker = f'[file {name}]\n'
    if sby.count(marker) != 1:
        raise ValueError(f'missing or repeated {name} in SBY')
    return sby.split(marker, 1)[1].split('\n[file ', 1)[0]


def check(label, design, out, yosys):
    directory = out / label
    directory.mkdir()
    text = design.read_text()
    if re.search(r'(?m)^\s*`(?:include|line)\b|\$(?:readmem[bh]|fopen|system|exec)\s*\(', text):
        raise ValueError(f'{label}: external file or command directive in RTL')
    sby = (UPSTREAM / 'insn_add_ch0.sby').read_text()
    for name in ('defines.sv', 'insn_add_ch0.sv'):
        (directory / name).write_text(inline_file(sby, name))
    script = (f'read_verilog -formal -sv -I{UPSTREAM} '
              f'{directory / "insn_add_ch0.sv"} {UPSTREAM / "wrapper.sv"} {design}; '
              'hierarchy -check -top rvfi_testbench; proc; check; '
              'select -count t:$check')
    (directory / 'command.txt').write_text(f'{yosys} -Q -T -p {script!r}\n')
    try:
        result = subprocess.run([yosys, '-Q', '-T', '-p', script], text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
        status = 'PASS' if result.returncode == 0 else 'FAIL'
        log = result.stdout
        exit_code = result.returncode
    except subprocess.TimeoutExpired as error:
        status, exit_code = 'TIMEOUT', None
        log = (error.stdout or b'').decode(errors='replace')
    (directory / 'yosys.log').write_text(log)
    counts = re.findall(r'(?m)^(\d+) objects\.$', log)
    checks = int(counts[-1]) if counts else None
    if status == 'PASS' and not checks:
        status = 'NO_FORMAL_CHECKS'
    modules = re.findall(r'(?m)^\s*module\s+(\w+)', text)
    original_modules = re.findall(r'(?m)^\s*module\s+(\w+)', (UPSTREAM / 'picorv32.v').read_text())
    return {'status': status, 'exit_code': exit_code, 'formal_check_cells': checks,
            'missing_modules': sorted(set(original_modules) - set(modules)),
            'design_sha256': hashlib.sha256(design.read_bytes()).hexdigest(),
            'log': str(directory / 'yosys.log')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('output directory already exists')
    yosys = shutil.which('yosys')
    if yosys is None:
        parser.error('yosys is unavailable')
    args.out.mkdir(parents=True)
    results = {'original': check('original', UPSTREAM / 'picorv32.v', args.out, yosys)}
    if args.candidate:
        results['candidate'] = check('candidate', args.candidate / 'picorv32.v', args.out, yosys)
        (args.candidate / 'frontend.txt').write_text(json.dumps(results, indent=2) + '\n')
    (args.out / 'summary.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))
    if any(item['status'] != 'PASS' for item in results.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
