# rtl-relate

Independent research prototype for checking finite bit-vector RTL abstraction certificates. It does not import NeuroAbs. The current experiments use authored P1/P5 abstractions and certificates; no LLM discovery or verification speedup is claimed.

## Reproduce

Requires Python 3.10+ (tested with 3.14.6), the Z3 CLI on PATH (tested with 4.15.4), and `uv` for the isolated frontend installation. No Python runtime dependency is required by the checker.

```bash
sh scripts/bootstrap_yosys.sh
python3 -m unittest discover -s tests -v
python3 -m rtl_relate demo --out results/my-first-run
```

Use a new output directory for each run. The demo preserves all queries, solver outputs, models, contracts, certificates, RTL copies, Yosys exports and metadata, traces, and timing. It exits nonzero if any expected result is missing or wrong. `summary.json` and `results.csv` contain the result matrix. The installer pins YoWASP Yosys and its dependencies under `.tools/`; it does not modify system packages.

| Case | Certificate | Property / replay |
| --- | --- | --- |
| P1 counter → done | ACCEPTED | SAFE; extra early-done trace is infeasible in C |
| P5 retain stall/hold | ACCEPTED | SAFE; at least one added abstract trace is infeasible in C |
| P5 unrestricted data | ACCEPTED | Abstract CEX; SPURIOUS_TRACE after exact concrete replay |
| P5 concrete missing hold guard | ACCEPTED | BUG only after legal concrete violation evidence |

The P5 bug experiment may first encounter a spurious abstract trace. In the current run it finds a **different** concrete violation via direct concrete search and replays that trace. The record explicitly identifies this provenance and includes the search cost; it does not claim the first abstract trace was concretized.

Check saved data files independently:

```bash
python3 -m rtl_relate check \
  results/my-first-run/rtl/p1/certificate/concrete.json \
  results/my-first-run/rtl/p1/certificate/abstract.json \
  fixtures/contracts/p1.json \
  results/my-first-run/rtl/p1/certificate/certificate.json \
  --out results/rechecked-p1
```

The supplied contract is the trusted input. A new contract is a different theorem, even if a new certificate passes. Candidate generation is not implemented; a future generator must have read-only access to the checker, concrete model, contract, tests, and acceptance records.

See [semantics](docs/semantics_v0.md), [frontend scope](docs/frontend_decision.md), [environment](docs/environment.md), and [actual sprint results](SPRINT_REPORT.md).

## Scope

One positive-edge clock, same-step finite state transitions, explicit initialization, E=true, data-only typed certificates, and safety. The certificate gate supports Mealy observations with one shared witness; property/replay currently support Moore observations and one-step safety predicates only. Unsupported memory, reset, clock, assumption, and operator semantics fail closed. SAFE comes from an all-state step proof or exhaustive reachable closure; reaching an exploration limit returns UNKNOWN.

The trusted computing base includes Yosys, the adapter, typed IR, checker, finite explorer, and Z3. There is no independent solver proof-kernel checking. The tiny cases are correctness and feasibility evidence, not competitive performance benchmarks.
