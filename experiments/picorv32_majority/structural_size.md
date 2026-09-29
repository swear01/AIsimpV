# Structural size of both candidates

This is a **size comparison**, not an assertion check. Both designs use Yosys 0.69+post, standalone `picorv32` as top, and the upstream wrapper parameters `COMPRESSED_ISA=1`, `ENABLE_FAST_MUL=1`, `ENABLE_DIV=1`, `BARREL_SHIFTER=1`. `synth -flatten; stat` reports generic cells without technology mapping. The assertion harness is not synthesized.

| Measure | Original | Candidate 01: omit M | Candidate 02: abstract register reads |
|---|---:|---:|---:|
| Complete source file lines | 3,049 | 2,103 | 2,516 |
| `picorv32` module lines | 2,106 | 2,019 | 2,106 |
| Generic cells, upstream RVFI/ALTOPS defines | 12,412 | 11,460 (−7.7%) | **7,221 (−41.8%)** |

The last row is a structural proxy for this research task. Upstream `checks.cfg` defines `RISCV_FORMAL`, `DEBUGNETS`, and `RISCV_FORMAL_ALTOPS`; here `RISCV_FORMAL` is only a source preprocessor define that exposes RVFI signals. ALTOPS replaces M instruction results with simpler operations. Deleting M therefore has much less impact on this configuration than on an ordinary hardware build. In a separate ordinary build without those defines, candidate 01 reduced generic cells from 18,823 to 9,864 (47.6%), but that figure does not represent the upstream assertion configuration. Candidate 02 selects the upstream register-read abstraction; Yosys reports two `$anyseq` cells and no register-file memory in the resulting model. Generic cell counts are not solver runtime, gate area, or evidence of preserved behavior.

To reproduce the generic cell counts, replace `SOURCE` with `upstream/picorv32.v`, `candidate-01/picorv32.v`, or `candidate-02/picorv32.v` from this directory:

```sh
yosys -Q -T -p 'read_verilog -sv -D RISCV_FORMAL -D DEBUGNETS -D RISCV_FORMAL_ALTOPS SOURCE; hierarchy -top picorv32 -chparam COMPRESSED_ISA 1 -chparam ENABLE_FAST_MUL 1 -chparam ENABLE_DIV 1 -chparam BARREL_SHIFTER 1; synth -top picorv32 -flatten; stat'
```

For the ordinary-build row, omit the three `-D` defines from `read_verilog`. No Formal command was run.
