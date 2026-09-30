#!/usr/bin/env python3
"""Compare one nonzero dependent ADD trace across the frozen designs."""
import json
from pathlib import Path
import subprocess
import tempfile


CASE = Path(__file__).resolve().parents[1]
TESTBENCH = Path(__file__).resolve().with_name('add_sequence_tb.sv')
SIGNALS = ('clk', 'resetn', 'rvfi_valid', 'rvfi_insn', 'rvfi_pc_rdata',
           'rvfi_rs1_rdata', 'rvfi_rs2_rdata', 'rvfi_rd_addr', 'rvfi_rd_wdata')


def trace(vcd):
    symbols, values, events = {}, {}, []
    time = None
    for line in vcd.read_text().splitlines():
        if line.startswith('$var '):
            fields = line.split()
            if fields[4] in SIGNALS and fields[4] not in symbols.values():
                symbols[fields[3]] = fields[4]
        elif line.startswith('#'):
            if time is not None and all(values.get(key) == '1' for key in ('clk', 'resetn', 'rvfi_valid')):
                event = {'time': time}
                for name in SIGNALS[3:]:
                    bits = values.get(name, 'x')
                    event[name] = hex(int(bits, 2)) if set(bits) <= {'0', '1'} else bits
                events.append(event)
            time = int(line[1:])
        elif line.startswith('b'):
            bits, symbol = line[1:].split()
            if symbol in symbols:
                values[symbols[symbol]] = bits
        elif line and line[0] in '01xXzZ' and line[1:] in symbols:
            values[symbols[line[1:]]] = line[0].lower()
    return events


def main():
    designs = {
        'original': CASE / 'upstream/picorv32.v',
        'candidate': CASE / 'candidate-sonnet-5-5/picorv32.v',
        'deepseek-02': CASE / 'candidate-02/picorv32.v',
    }
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        traces = {}
        for label, design in designs.items():
            vcd = directory / f'{label}.vcd'
            script = directory / f'{label}.ys'
            script.write_text(f'read_verilog -sv -D RISCV_FORMAL {design} {TESTBENCH}; '
                              f'hierarchy -check -top tb; proc; flatten; opt; memory; opt; '
                              f'sim -clock clk -resetn resetn -n 80 -vcd {vcd}\n')
            subprocess.run(['yosys', '-Q', '-T', '-s', str(script)], check=True,
                           stdout=subprocess.DEVNULL)
            traces[label] = trace(vcd)
    expected = {'rvfi_insn': '0x2081b3', 'rvfi_pc_rdata': '0x8',
                'rvfi_rs1_rdata': '0x5', 'rvfi_rs2_rdata': '0x7',
                'rvfi_rd_addr': '0x3', 'rvfi_rd_wdata': '0xc'}
    if traces['candidate'] != traces['original']:
        raise SystemExit('candidate trace differs from original')
    if not any(all(event.get(key) == value for key, value in expected.items())
               for event in traces['candidate']):
        raise SystemExit('expected nonzero ADD event not found')
    if traces['deepseek-02']:
        raise SystemExit('DeepSeek 02 unexpectedly retired an instruction')
    print(json.dumps(traces, indent=2))


if __name__ == '__main__':
    main()
