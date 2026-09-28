# Upstream axilxbar formal rewrite pilot

This case tests one actual [ZipCPU/wb2axip](https://github.com/ZipCPU/wb2axip) formal obligation: read-grant consistency in `CHECK_MASTER_GRANTS` of `rtl/axilxbar.v` (source commit `2e8d3bc2d26ddc33d1881022a2a2b9d3f0c16b9b`). The `upstream/` tree is a byte-for-byte snapshot of the three RTL files, two formal helper modules, and `bench/formal/axilxbar.sby`; Apache-2.0 notices remain in the source. The full suite is available as context. The target is one obligation, not a claim that every upstream assertion was rewritten or proved.

The upstream `prf4x8_lp` task uses 4 masters, 8 slaves, 16-bit addresses, and `OPT_LOWPOWER=1`. This local pilot uses the source defaults (4, 8, 32-bit addresses, `OPT_LOWPOWER=1`) because installed Yosys 0.69 crashes internally with `hierarchy -chparam` on this design. This difference is recorded in `task.json`; do not report the local run as an execution of the exact upstream SBY task.

After the generation input was frozen, a port-preserving wrapper was found to elaborate the upstream 4×8, 16-bit-address parameters without `hierarchy -chparam`. Run `python3 scripts/check_upstream_axilxbar.py --upstream-params --candidate <candidate-dir> --out <new-output-dir>` for this additional frontend check. Original and all three candidates passed it. It still does not execute the upstream SBY proof engine.

From the repository root, check the original formal design with:

```sh
python3 scripts/check_upstream_axilxbar.py --out results/upstream-axilxbar/original
```

Generate one isolated candidate, then run the same frontend check and blind analysis:

```sh
python3 scripts/freestyle_pilot.py rewrite --case experiments/upstream_axilxbar --out results/upstream-axilxbar/rewrite-01 --provider deepseek
python3 scripts/check_upstream_axilxbar.py --candidate results/upstream-axilxbar/rewrite-01/candidate --out results/upstream-axilxbar/frontend-01
python3 scripts/freestyle_pilot.py analyze --case experiments/upstream_axilxbar --candidate results/upstream-axilxbar/rewrite-01/candidate --out results/upstream-axilxbar/analysis-01 --provider deepseek
```

The check uses `read_verilog -formal`, which activates upstream `FORMAL` code, followed by hierarchy, process conversion, and structural checking. It is neither an SBY proof nor a soundness check. The candidate analysis does not receive the generator's explanation. Keep original and candidate artifacts separate from the earlier derived-property pilot.
