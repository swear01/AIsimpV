#!/usr/bin/env python3
"""Frontend check for the frozen upstream axilxbar formal problem."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / 'experiments/upstream_axilxbar/upstream'
RTL = UPSTREAM / 'rtl'
FORMAL = UPSTREAM / 'bench/formal'


def wrapper(path):
    text = (RTL / 'axilxbar.v').read_text()
    ports = text.split(') (', 1)[1].split(');', 1)[0]
    names = re.findall(r'(?m)^\s*(?:input|output)\s+wire\s+(?:\[[^]]+\]\s+)?([A-Za-z_]\w+)', ports)
    if len(names) != 40:
        raise ValueError(f'expected 40 upstream AXI ports, found {len(names)}')
    connections = ',\n'.join(f'        .{name}({name})' for name in names)
    path.write_text('module axilxbar_formal_top #(\n'
                    '    parameter integer C_AXI_DATA_WIDTH=32, C_AXI_ADDR_WIDTH=16,\n'
                    '    parameter NM=4, NS=8\n'
                    ') (\n' + ports + ');\n'
                    '    axilxbar #(.NM(NM), .NS(NS),\n'
                    '        .C_AXI_ADDR_WIDTH(C_AXI_ADDR_WIDTH),\n'
                    '        .C_AXI_DATA_WIDTH(C_AXI_DATA_WIDTH), .OPT_LOWPOWER(1)) dut (\n'
                    + connections + '\n    );\nendmodule\n')


def check(label, design, out, yosys, upstream_params=False):
    text = design.read_text()
    forbidden = r'(?m)^\s*`(?:include|line)\b|\$(?:readmem[bh]|fopen|system|exec)\s*\('
    if re.search(forbidden, text):
        raise ValueError(f'{label}: external file or command directive in RTL')
    directory = out / label
    directory.mkdir()
    sources = [RTL / 'addrdecode.v', RTL / 'skidbuffer.v', design,
               FORMAL / 'faxil_slave.v', FORMAL / 'faxil_master.v']
    top = 'axilxbar'
    if upstream_params:
        wrapper_path = directory / 'wrapper.v'
        wrapper(wrapper_path)
        sources.append(wrapper_path)
        top = 'axilxbar_formal_top'
    script = ('read_verilog -formal -sv -defer ' + ' '.join(map(str, sources))
              + f'; hierarchy -check -top {top}; proc; check; select -count t:$check')
    (directory / 'command.txt').write_text(f'{yosys} -Q -T -p {script!r}\n')
    try:
        result = subprocess.run([yosys, '-Q', '-T', '-p', script], text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
        log = result.stdout
        status = 'PASS' if result.returncode == 0 else 'FAIL'
        exit_code = result.returncode
    except subprocess.TimeoutExpired as error:
        log = (error.stdout or b'').decode(errors='replace')
        status, exit_code = 'TIMEOUT', None
    (directory / 'yosys.log').write_text(log)
    counts = re.findall(r'(?m)^(\d+) objects\.$', log)
    checks = int(counts[-1]) if counts else None
    if status == 'PASS' and checks == 0:
        status = 'NO_FORMAL_CHECKS'
    return {'status': status, 'exit_code': exit_code, 'check_cells': checks,
            'design_sha256': hashlib.sha256(design.read_bytes()).hexdigest(),
            'log': str(directory / 'yosys.log')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--upstream-params', action='store_true',
                        help='check upstream SBY 4x8, AW16, LOWPOWER1 parameters via port wrapper')
    args = parser.parse_args()
    if args.out.exists():
        parser.error('output directory already exists')
    yosys = shutil.which('yosys')
    if yosys is None:
        parser.error('yosys is unavailable')
    args.out.mkdir(parents=True)
    results = {'original': check('original', RTL / 'axilxbar.v', args.out, yosys,
                                 args.upstream_params)}
    if args.candidate:
        results['candidate'] = check('candidate', args.candidate / 'axilxbar.v', args.out,
                                     yosys, args.upstream_params)
        if not args.upstream_params:
            (args.candidate / 'frontend.txt').write_text(json.dumps(results, indent=2) + '\n')
    (args.out / 'summary.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))
    if any(result['status'] != 'PASS' for result in results.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
