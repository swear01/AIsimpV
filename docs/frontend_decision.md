# RTL frontend decision and observed evidence

The feasibility implementation uses **Yosys → BTOR2 → typed model → Z3**. The JSON netlist is used only to validate clock/cell semantics and obtain signedness, not as a second transition-model frontend. No RTL text parser or manually substituted transition relation is used.

## Installed tool (2026-09-20)

Project-local executable: `.tools/yosys-venv/bin/yowasp-yosys`. `scripts/bootstrap_yosys.sh` pins its package and runtime dependencies; no system packages or global configuration were changed.

- `yowasp-yosys==0.69.0.0.post1233`
- `yowasp-runtime==1.96`, `wasmtime==47.0.1`, `click==8.5.0`, `platformdirs==4.11.11`
- Actual backend: `Yosys 0.69 (git sha1 9f75ca1f9, Release, Clang /workspace/YoWASP/yosys/wasi-sdk-33.0-x86_64-linux/share/cmake/../..//bin/clang++ 22.1.0)`
- `yosys.wasm` SHA-256: `77fe957bef892d75f74a0ce2165d7b328b6cda462a0e0051509df0c5a55ece49`

YoWASP is an unofficial WebAssembly packaging of the actual Yosys backend. Native Yosys is also accepted by supplying the executable explicitly; every run records the actual version and executable hash. The verified feasibility results use the pinned YoWASP above.

## Fixed invocation

```text
read_verilog -sv source.v
hierarchy -check -top TOP
proc
opt_clean
check -assert
write_json netlist.json
write_btor -i model.info model.btor2
write_verilog -noattr normalized.v
```

Each output directory retains the exact RTL copy, script, Yosys stdout/stderr, netlist, BTOR2, clock info, typed model, version and hashes, command, status, and frontend wall time. The model's source fingerprint binds the copied RTL, top, clock, registered nondeterministic ports, script, and actual Yosys version. The model hash then binds the entire typed transition relation.

`export_rtl(source, top, out_dir, *, nondet=(), clock="clk", executable=None, timeout=60)` returns the typed model. `Unsupported` is a `ValueError`; failure does not return an accepted model. Inputs named in `nondet` become fresh unconstrained inputs in the model; witness expressions never enter this frontend. The clock is removed only after checking that all state elements use the same positive edge and the clock does not appear in data logic.

## Supported boundary

This is a deliberately bounded frontend for the P1/P5 fixtures and the selected public pilot: one flat module, one positive-edge input clock, two-state BV data (1–256 bits), explicit fully defined constant initialization, deterministic functional next state, and explicit output observations. BV1 remains distinct from Bool in the typed model. Comparisons and reduction-or are converted from BTOR2 BV1 into typed predicates and back explicitly. Yosys output registers sometimes have anonymous BTOR2 state IDs; their origin is recovered only from a direct output-to-state graph alias.

Unsupported operators, arrays/memory, assumptions/constraints, embedded assertions outside the exact profile below, liveness, latches, asynchronous reset, negative/multiple/gated clocks, clock-as-data, undefined bits, missing init/next, and unresolved nondeterministic port names fail closed. Constant-initial-state support is narrower than the checker IR's general initial predicate. RTL includes/hierarchy and arbitrary SystemVerilog are outside this export interface. Native signed operations not in the implemented operator subset are rejected rather than reinterpreted.

The parser alone does not establish RTL clock correctness. Callers processing RTL must use `export_rtl`, which validates Yosys netlist and clock metadata before returning a model. The returned model retains `clock: {name: ACTUAL_CLOCK, edge: "positive"}` after removing the clock from data symbols. The checker must compare this metadata against the frozen contract; an alternative clock port cannot silently inherit the contract clock name.

## Public pilot interface

`export_rtl` additionally accepts `parameters=None` and `profile=None`. Parameter keys must be simple Verilog names and values unsigned 32-bit integers. They are applied through `hierarchy -chparam`; their elaborated values are checked against the resulting module. The retained script and source fingerprint bind these choices. Both skidbuffer widths use unchanged upstream RTL with `DW=8/32`, `OPT_OUTREG=1`, `OPT_LOWPOWER=0`, `OPT_PASSTHROUGH=0`, and `OPT_INITIAL=1`. Synchronous reset remains an ordinary input to the extracted next-state relation; the frontend adds no reset assumptions.

The only assertion extraction profile is `profile="avr_pipeline32"`, with `top="main"`, `clock="clock"`, and exact upstream source SHA-256 `9a28c1109682583337c71df11383cd451dc941bf0724ca51c820c1e7bf8d2eaa`. Different bytes, parameters, or nondeterministic inputs are rejected. The source copy is unchanged. After `proc`, Yosys exposes `tmp_stageOne`, `tmp_stageTwo`, and `prop`, saves `original-netlist.json`, and removes the original assertion cell. The adapter requires exactly one original `$check`, with assertion flavor, constant enabled condition, no trigger, and its predicate connected directly to `prop`. All ordinary clock/cell/init checks still apply.

The predicate is extracted from the BTOR2 output into `assertion.json`, bound to the returned model hash, and removed from the observation interface. Observations are exactly `dataOut`, `tmp_stageOne`, and `tmp_stageTwo`. Both 32-bit history states remain present, for 160 total state bits. The frozen contract carries the original `dataOut == tmp_stageTwo + tmp_stageOne || dataOut == 0` formula. The extracted predicate is checked against that formula in a solver regression without init/invariant assumptions, including a satisfiable negation to prevent a constant-true extraction from passing. This is one pinned benchmark adapter, not a general SVA translator.

Every export also retains `normalized.v` emitted by Yosys from the same processed graph, with its hash in `frontend.json`. For the pipeline only, the temporary `prop` output flag is removed before writing this RTL; the three contract outputs remain. The formal backend can consume this exact file without importing another assertion or losing the history registers. Normalization changes neither the original zero initialization nor the fact that reset clears only `dataOut`.

## Executed validation

`python -m unittest discover -s tests -p test_frontend.py -v`

Five unittest groups cover real exports of P1 concrete/abstract and P5 concrete/hold/coarse/bug against independent arithmetic for **all 520 state/input valuations**, including initialization, every next-state field, and every observation. Negative tests cover missing initialization/transition, unregistered nondeterminism, constraints, arrays, unsupported operators, malformed state targets, unknown bits, and actual RTL with uninitialized state, negative edge, asynchronous reset, multiple clocks, or a clock used as data. A renamed-clock RTL export verifies that the actual clock identity remains in the returned model for contract comparison, and an incorrect requested clock is rejected.

This establishes a small real RTL integration with exhaustive differential checks. It does not establish a complete SystemVerilog semantics implementation or a formally verified Yosys/BTOR2 translator.

The expanded frontend suite has 10 test groups: the original 520 valuations, BV1 reduction/inequality truth tables, 4,096 skidbuffer boundary valuations across 8/32-bit payloads, and 400 deterministic boundary/random pipeline valuations across raw-source extraction and re-exported normalized RTL. Pipeline arithmetic wraps at 32 bits and history updates continue during reset. Negative tests reject a changed assertion, extraction without the pinned profile, invalid parameter names/types, and unknown parameters. The original unsupported-clock and missing-initialization checks remain enabled.

## Authoritative references consulted

- [Yosys write_btor documentation](https://yosyshq.readthedocs.io/projects/yosys/en/0.45/cmd/write_btor.html): backend interface and auxiliary metadata export. This is a documentation snapshot, not the installed version claim.
- [BTOR2 tools format](https://github.com/hwmcc/btor2tools/blob/master/README.md): typed node grammar, state/init/next, operators, and outputs.
- [YoWASP packaging source](https://github.com/YoWASP/yosys): distribution source; the actual local version and artifact hash above are retained separately.

Context7 lookup returned no Yosys documentation entry; the official documentation, BTOR2 grammar, and actual executable output were used instead.
