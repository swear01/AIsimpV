# AIsimpV

Independent research prototype for checking finite bit-vector RTL abstraction certificates. It does not import NeuroAbs. The public RTL pilot now checks FSM re-encoding, 8/32-bit skidbuffers, and a 32-bit pipeline with independent certificates and safety proofs. All 12 authored positive/negative controls meet their expected outcomes. These small cases establish feasibility, not verification speedup.

## Current research plan

The [September 23 pilot plan](docs/wednesday_plan.md) covers four new tasks: FSM re-encoding, public skidbuffer instances at 8/32 bits, and a public 32-bit pipeline. It also includes two bounded LLM pilots: certificate discovery for a fixed pair, then joint RTL/certificate generation. The four manual tasks are complete; see the [measured report and slides](docs/reports/wednesday_report.md). The joint Codex pilot produced a different 18→10-bit skid8 abstraction: attempt one failed its model hash binding, and attempt two passed the certificate gate and free-choice safety proof without human candidate edits. The original fixed-pair pilot exhausted four infrastructure-failed attempts before meaningful discovery. A [separately preregistered follow-up](docs/llm_certificate_followup.md) then generated a passing certificate on its first candidate for the unchanged human-prepared C/A pair, taking 38.610 seconds for generation and verification; an independent clean-source recheck also passed. All failed attempts and transport qualification costs remain recorded separately. This is one successful pair, without evidence of feedback benefit or verification speedup.

The additional [finite FIFO 4×8 assessment](docs/reports/fifo_followup.md) remains `UNSUPPORTED` at undefined-value branches and anonymous BTOR inputs. It preserves arbitrary initial memory values, adds no FIFO property proof, and is outside the four-task matrix.

An [eight-repeat paired timing study](docs/reports/verification_timing.md) now separates property proof, SMTBMC/Z3 process time, and certificate/translation costs for the four manual rewrites and saved LLM candidate. It finds no reliable speedup: pipeline property time rises from a median 0.618 s to 1.070 s, and every known-candidate validation path costs more than direct concrete proof. State reduction alone is not the performance objective.

The [native-memory abstraction search](docs/reports/abstraction_search.md) selects three FIFO configurations with original proof medians of 24.4, 52.8 and 35.4 seconds, before inspecting abstraction outcomes. It compares fixed havoc templates, a clearly limited NeuroAbs-inspired cutpoint search, and full AI RTL generation under a [frozen protocol](docs/abstraction_search_protocol.md), without a manually successful abstraction prerequisite. These are three instances of one family. A separate synchronous-product adapter preserves all native assertions and partial memory initialization; it does not change the older finite-BV frontend's support boundary.

Three-repeat comparisons show no large total acceleration: the selected stateless candidates take 18.0/23.7/34.6 seconds including their certificates, versus matched originals at 19.6/28.8/31.7 seconds. Their approximately 0.3-second abstract property checks transfer the original theorem into the certificate. AI also generated a 21-bit control-state summary with eight helper relations, but its total validation takes 36.9 seconds. All 24 model attempts and the complete 33-case single-cut control are retained.

See the [benchmark source survey](docs/benchmark_shortlist.md), [measured manual results](docs/reports/data/manual-results.csv), and [GitHub issues](https://github.com/swear01/AIsimpV/issues) for dependencies, file ownership, and acceptance evidence. The two skidbuffer widths count as one design family. The skidbuffer task uses a documented derived contract; it is not a reproduction of the full upstream formal suite.

## Reproduce

Requires Python 3.11+ (tested with 3.14.6), the Z3 CLI on PATH (tested with 4.15.4), and `uv` for the isolated frontend installation. No Python runtime dependency is required by the checker.

```bash
sh scripts/bootstrap_yosys.sh
python3 -m unittest discover -s tests -v
python3 -m rtl_relate demo --out results/my-first-run
python3 -m rtl_relate.wednesday --out results/my-wednesday-run
```

Use a new output directory for each run. The demo preserves all queries, solver outputs, models, contracts, certificates, RTL copies, Yosys exports and metadata, traces, and timing. It exits nonzero if any expected result is missing or wrong. `summary.json` and `results.csv` contain the result matrix. The installer pins YoWASP Yosys and its dependencies under `.tools/`; it does not modify system packages.

Historical pilot artifacts and installed tools are local and excluded from Git. Run the commands above to generate your own evidence. The verification workflow runs the tests, tiny demo and four-task public rewrite matrix, retaining raw proof evidence as a GitHub Actions artifact. The [report](docs/reports/wednesday_report.md) links the frozen pilot evidence and saved LLM candidates.

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

The supplied contract is the trusted input. A new contract is a different theorem, even if a new certificate passes. The [bounded Codex runner](docs/llm_protocol.md) isolates generation from the trusted checker, concrete model, contract and acceptance records. A generated verdict has no authority; the parent independently exports and verifies saved candidates.

See [public-task semantics](docs/semantics_v1.md), [original tiny-task semantics](docs/semantics_v0.md), [frontend scope](docs/frontend_decision.md), [environment](docs/environment.md), and [actual sprint results](SPRINT_REPORT.md).

## Scope

The original finite-BV certificate profile supports one positive-edge clock, same-step finite state transitions, explicit initialization, E=true, data-only typed certificates, and safety. The certificate gate supports Mealy observations with one shared witness; property/replay currently support Moore observations and one-step safety predicates only. The v1 profile supports an explicitly declared synchronous reset as an unconstrained public input. Unsupported memory, reset, clock, assumption, and operator semantics fail closed. The public RTL property backend returns SAFE only after successful bounded base checks and k-induction with yosys-smtbmc/Z3; finite-depth checking alone is BOUNDED. The original tiny backend uses an all-state step proof or exhaustive reachable closure; reaching its exploration limit returns UNKNOWN.

The trusted computing base includes Yosys, the adapter, typed IR, checker, finite explorer, and Z3. There is no independent solver proof-kernel checking. The public set has two upstream design families, three parameter instances and one authored FSM control. It is a pilot, not a broad benchmark suite or an end-to-end acceleration result.

## Working on an issue

Start with an unblocked issue and state which issue you are handling before changing shared files. Each issue lists dependencies, owned paths, and completion evidence. Changes to the common checker/schema/runner need coordination with dependent case work. Keep original RTL, contracts, gold certificates, and checker code outside a generation agent's writable candidate workspace.

An issue is complete only when its acceptance checks have actually run and its evidence links are recorded. Preserve failed attempts and distinguish `NOT_RUN`, `UNSUPPORTED`, `UNKNOWN`, certificate rejection, abstract counterexamples, and replay-confirmed concrete bugs. Timing comparisons use the same frozen contract and normal preprocessing on both sides.

Baseline qualification follow-up: [two public FIFO instances with repeated 5.77 / 7.31 second direct proofs](docs/reports/baseline_screen.md). Certificate integration and abstraction speedup for these instances remain untested.
