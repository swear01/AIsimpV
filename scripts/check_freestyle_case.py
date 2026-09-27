#!/usr/bin/env python3
"""Frontend-only elaboration of the frozen axilxbar/property binding."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / 'experiments/freestyle_axilxbar/original'
BINDING = '''
    axilxbar_read_hold_property f_hold (
        .clk(S_AXI_ACLK), .resetn(S_AXI_ARESETN),
        .rvalid(S_AXI_RVALID[0]), .rready(S_AXI_RREADY[0]),
        .rdata(S_AXI_RDATA[0+:32]), .rresp(S_AXI_RRESP[0+:2])
    );
'''


def check(label, design, prop, out, yosys):
    text = design.read_text()
    # ponytail: lexical guard may reject commented directives; use an isolated frontend for broader RTL syntax.
    forbidden = r'(?m)^\s*`(?:include|line)\b|\$(?:readmem[bh]|fopen|system|exec)\s*\('
    if re.search(forbidden, text) or re.search(forbidden, prop.read_text()):
        raise ValueError(f'{label}: external file or command directive in candidate')
    if text.count('\nendmodule') != 1:
        raise ValueError(f'{label}: expected exactly one top module')
    case = out / label
    case.mkdir()
    bound = case / 'bound_design.v'
    bound.write_text(text.replace('\nendmodule', BINDING + '\nendmodule'))
    script = (f'read_verilog -sv -defer {ORIGINAL / "addrdecode.v"} {ORIGINAL / "skidbuffer.v"} {bound}; '
              f'read_verilog -formal -sv -defer {prop}; '
              'hierarchy -check -top axilxbar; proc; check; '
              'select -assert-any axilxbar_read_hold_property/t:$check')
    (case / 'command.txt').write_text(f'{yosys} -Q -T -p {script!r}\n')
    try:
        result = subprocess.run([yosys, '-Q', '-T', '-p', script], text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
        (case / 'yosys.log').write_text(result.stdout)
        return {'status': 'PASS' if result.returncode == 0 else 'FAIL',
                'exit_code': result.returncode, 'log': str(case / 'yosys.log')}
    except subprocess.TimeoutExpired as error:
        (case / 'yosys.log').write_text((error.stdout or b'').decode(errors='replace'))
        return {'status': 'TIMEOUT', 'exit_code': None, 'log': str(case / 'yosys.log')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('output directory already exists')
    yosys = shutil.which('yosys')
    if not yosys:
        parser.error('yosys is unavailable')
    args.out.mkdir(parents=True)
    results = {
        'original': check('original', ORIGINAL / 'axilxbar.v', ORIGINAL / 'property.v', args.out, yosys),
        'candidate': check('candidate', args.candidate / 'axilxbar.v',
                           args.candidate / 'property.v', args.out, yosys),
    }
    (args.out / 'summary.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))
    if any(result['status'] != 'PASS' for result in results.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
