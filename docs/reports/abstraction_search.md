# Bounded native-memory abstraction search

This is the first experiment under the [frozen protocol](../abstraction_search_protocol.md).
The three selected tasks are configurations of one public FIFO family, not
three independent controller/protocol families. Selection used original proof
runtime before seeing any abstraction result; no human-authored useful
abstraction was required.

## Measured result

No large end-to-end acceleration emerged. The AI generated a verified control-state
summary with relational helpers, but its certificate remained expensive. The fastest
candidates mostly made the abstract assertions tautological and moved the original
proof into the certificate. These are not evidence of a new fast abstraction method.

Original-source proof medians were **24.399, 52.830 and 35.371 seconds**, each
confirmed three times before abstraction. The common normalization itself improves
those timings, so speedup ratios below use the matched normalized original. All
numbers are seconds; medians of three fresh serial runs. Task dimensions are
**FIFO depth × data width**. Total includes candidate preparation, abstract property,
correctness proof and supervisor overhead; it excludes candidate discovery.

| Task / candidate | Matched C | A property | Certificate | Total validation | C / total |
|---|---:|---:|---:|---:|---:|
| 256×256 / stateless | 19.575 | 0.300 | 17.114 | 17.986 | 1.09× |
| 64×512 / stateless | 28.808 | 0.299 | 22.896 | 23.736 | 1.21× |
| 64×512 / stateful | 28.808 | 0.305 | 36.004 | 36.880 | 0.78× |
| 256×512 / stateless | 31.677 | 0.301 | 33.638 | 34.591 | 0.92× |

A ratio below 1 is slower. The approximately 1.1–1.2× gains in the first two
stateless cases occur while re-proving the original theorem in a different encoding;
they do not demonstrate the intended relational abstraction speedup. All 21 paired
measurements completed their required proofs; full samples/ranges are in the
[machine-readable results](data/abstraction_search_results.json).

The 64×512 fourth AI attempt is the most structurally distinct result: native
register-plus-memory storage falls from **34,911 bits to 21 bits**, with free output
data witnessed from C. After the preceding control-state candidate failed induction,
the model supplied eight helper relations, including `C.f_fill = A.fill` and guarded
history equalities. The parent made no candidate edits. The corrected verifier and
three fresh repeats accept it, but data-related safety work remains in the product
certificate. The relations reuse facts and signals present in the original RTL and
assertions; this is not a claim of a novel abstraction theorem.

## Controls and complete search costs

The frozen four-template baseline produced 12 spurious counterexamples. The
NeuroAbs-inspired arm returned the unchanged model in all 12 attempts. A post-hoc
exhaustive single-cut control then checked all eleven eligible vectors per task:
**33/33 produced counterexamples**. No combinations were executed. Because adding
independent havoc cuts only adds traces, a permitted superset cannot remove the
existing single-cut counterexample. This is an inference about this eleven-vector
havoc space, not a limitation of other predicates, relational abstractions or NeuroAbs.

rIC3 1.5.2 single-thread IC3 timed out on all three original selected FIFO tasks at
the 60-second shared deadline. AVR supplied benchmark source cases during screening;
the AVR solver itself was not run. The full screening record has 29 executions:
21 SAFE, one BOUNDED, five UNKNOWN and two CEX; no failed screening case is suppressed.

| Task | Fixed four templates | AI cutpoint search | Full AI search |
|---|---:|---:|---:|
| 256×256 | 4.287 | 402.970 | 573.023 |
| 64×512 | 12.019 | 382.452 | 854.851 |
| 256×512 | 9.137 | 418.554 | 900.962 |

The table reports full search-process wall time, including initialization and parent
bookkeeping; charged generation/verification totals are also recorded in JSON.
Each AI arm used four calls. Full AI discovery recorded eight provisional proof
successes, one failed induction, two certificate timeouts and one generation timeout.
All eight successes passed the corrected verifier; exact duplicates reuse the same
proof, so five distinct candidates required **155.954 seconds** of additional
revalidation. The last search charged 900.038 seconds to generation/verification,
including cleanup at its 900-second deadline; its full process took 900.962 seconds.
Its incomplete call has no final token-usage record. Dollar cost
is unknown. Screening, tool builds, verifier qualification and repeated timing are
retained separately and are not hidden inside a claimed discovery speedup.

Every model output, including empty files from the timeout, is retained byte-for-byte
in the [raw candidate bundle](data/abstraction_search_candidates.json). Generation
snapshot v1 and its ledgers remain unchanged. A negative boundary test exposed an
input-`init` attribute that could restrict the original environment and make an unsafe
product appear proved; final snapshot v4 rejects this and inconsistent initializers.
It also fixes nested deadline propagation. All reported final results use v4; the
old false-acceptance probe and unused intermediate snapshots remain in the raw evidence.

## Research decision

Keep these cases instead of hunting for longer timeouts. The useful next experiment
is AI synthesis of relations and abstraction predicates with a cheap local simulation
certificate, ranked by property **plus correctness** cost. The certificate should
establish a structural mapping without merely re-solving the original safety theorem.
The current interface only permits existing concrete wires as witnesses and checks a
whole synchronous product; these are significant expressiveness and cost limits.
This experiment supports pursuing that direction, but does not yet establish that
it beats conventional abstraction or that AI can find a 100× result. It does not
require a human to invent a successful summary first.

## Contract and comparison scope

The upstream source, all 28 native assertions, reset/init and assumptions remain
fixed. The selected configuration has zero assumptions. Five cover statements
are retained in source but are not safety obligations. Memory remains partly
uninitialized; unknown values are never replaced by zero.

The matched property harness exposes the original assertion A/EN signals and
checks every enabled predicate. Original anyconst values remain fixed arbitrary
values; all new abstract input ports are independently free each cycle.
The abstract RTL may implement these observation ports differently; the product
must prove equality of enabled violation bits on original executions. Thus the
original theorem stays fixed, but abstract monitor logic is not frozen verbatim.
This freedom admits the proof-transfer candidates documented above.
The full AI arm also needs a separate witnessed synchronous-product proof.
Its optional helper relations are proved, never assumed. This sufficient gate
checks every abstract initial state and every original public output; it can
reject valid abstractions that need an existential initial-state relation.
Initializers may constrain only actual stored state, never public inputs or
combinational wires; conflicting state/read-register initializers are rejected.
It is a distinct native-memory adapter, not the original finite-BV h/J/w checker.

The non-LLM baseline tries four deterministic single-vector havoc cuts, ordered
by decreasing width then name. The NeuroAbs-inspired arm uses the same sound
transformer with model-selected multiple cuts and actual counterexample feedback.
This is a partial netlist-cutting comparison: it does **not** implement NeuroAbs's
AST-local expression rewrites or published CEX-reduction algorithm. The retrieved
[NeuroAbs artifact](https://doi.org/10.6084/m9.figshare.30633074), version 2,
contains only a result spreadsheet; its original implementation was unavailable.
A win against this comparator would not establish a win against NeuroAbs or a
strong conventional word-level abstraction engine.

The full AI arm may generate a different RTL representation and witnesses.
Each AI task/arm has four attempts and 900 seconds for generation plus all
verification, including failures. Both arms use gpt-5.6-sol with high reasoning.
The parent never edits candidate RTL or certificates. A fresh source snapshot,
input bundle, hashes, logs, actual CEXs and rejected candidates are retained.

Property-only speedup, accepted-candidate validation, and total discovery cost
must be read separately. A constant property with a correctness gate that proves
the original theorem merely transfers the proof cost. It is not end-to-end
acceleration. Failure within this bounded search does not establish that no
useful abstraction exists.

`SUCCESS` in a raw search ledger means the property and correctness checks
passed; it is not a speedup verdict. In the observed degenerate candidates,
some candidates set `A_abstract = A_choice | EN_choice` and
`EN_abstract = EN_choice`. Consequently `EN_abstract & ~A_abstract` is identically
zero; others assign all A bits to one. In the OR variant, the certificate supplies
the original A/EN as witnesses. In both variants, bad-output equality reduces to
the original safety theorem. Reusing that
certificate is essentially reusing the original proof, not discovering a
property-independent FIFO summary.

## Reproduction and evidence

Sources are pinned in the [selected catalog](../../fixtures/public/abstraction_search_selected.json).
The [initial catalog](../../fixtures/public/abstraction_search_candidates.json)
and protocol document the screening order and subsequent batches. Install the
pinned frontend using `sh scripts/bootstrap_yosys.sh`; Z3 must be on PATH.
All output directories must be new. Keep experiment outputs outside the trusted
source snapshot. Freeze only `scripts/` and `rtl_relate/` (without bytecode caches)
in that snapshot before generation. The following example reproduces the saved
21-bit candidate without a model call. Run it from the repository root.

```bash
export ASEARCH_RUN="$(mktemp -d)"
export ASEARCH_SNAPSHOT="$ASEARCH_RUN/snapshot"
export ASEARCH_TASK=sfifo_sync512_d64
export RTL_RELATE_YOSYS="$(pwd)/.tools/yosys-venv/bin/yowasp-yosys"
export ASEARCH_SMTBMC="${RTL_RELATE_YOSYS}-smtbmc"
python3 - <<'PY'
import os, shutil
from pathlib import Path
snapshot = Path(os.environ['ASEARCH_SNAPSHOT'])
snapshot.mkdir()
for name in ('scripts', 'rtl_relate'):
    shutil.copytree(name, snapshot / name,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
PY
python3 scripts/screen_baselines.py --catalog fixtures/public/abstraction_search_selected.json \
  --out "$ASEARCH_RUN/baselines" --repeats 3 --timeout 60
python3 "$ASEARCH_SNAPSHOT/scripts/search_abstractions.py" prepare \
  --task "$ASEARCH_RUN/baselines/repeat-01/$ASEARCH_TASK" \
  --out "$ASEARCH_RUN/tasks/$ASEARCH_TASK" \
  --yosys "$RTL_RELATE_YOSYS" --smtbmc "$ASEARCH_SMTBMC"
python3 - <<'PY'
import hashlib, json, os
from pathlib import Path
bundle = json.loads(Path('docs/reports/data/abstraction_search_candidates.json').read_text())
entry = bundle['tasks'][os.environ['ASEARCH_TASK']]['ai'][3]
candidate = Path(os.environ['ASEARCH_RUN']) / 'saved-candidate'
candidate.mkdir()
for name, text in entry['files'].items():
    raw = text.encode()
    assert hashlib.sha256(raw).hexdigest() == entry['sha256'][name]
    (candidate / name).write_bytes(raw)
PY
python3 "$ASEARCH_SNAPSHOT/scripts/search_abstractions.py" evaluate \
  --snapshot "$ASEARCH_SNAPSHOT" --task "$ASEARCH_RUN/tasks/$ASEARCH_TASK" \
  --candidate "$ASEARCH_RUN/saved-candidate" --out "$ASEARCH_RUN/replayed" \
  --arm ai --yosys "$RTL_RELATE_YOSYS" --smtbmc "$ASEARCH_SMTBMC"
```

To run a new bounded search, replace the last command's `evaluate` with `run`,
omit `--candidate`, and choose a fresh `--out` directory. Repeat prepare/run for
the other catalog entries and arms `templates` and `neuroabs-inspired`.
Keep proofs serial. A new model search is stochastic; replaying the saved bytes
is the way to reproduce the reported candidates exactly.
The reported generation used the archived Codex CLI runner; all numbers in this
report retain that provenance. Since September 22, new searches use the
[direct-API runner](../llm_protocol.md), defaulting to Muse Spark 1.3 Contributor;
add `--provider deepseek` for V4.1 Flash through the existing local gateway.
The earlier official-account balance diagnosis was for the wrong route; consult
the current runner protocol for actual gateway qualification.
The runner saves exact prompts, requests, responses and token usage without any
Codex system prompt. New API results must be reported separately. No hidden gold
candidate or verifier outputs are part of the initial model bundle.

The optional secondary engine accepts `--ric3 /absolute/path/to/rIC3`; this
experiment pins version 1.5.2 and its single-thread `-e ic3` interface. Build with
locked dependencies and nightly-2025-11-15; the current stable/latest nightly
build attempts failed and their logs are retained. The secondary results do not
change the task selection or mix engines in speedup ratios.

Research motivation follows the professor's
[Project 6: Abstraction and Refinement of RTL Designs](https://ric2k1.notion.site/2026-Summer-Plan-AI-for-EDA-Frontend-3a20e6ef6182806eb0adc0451236fa2d)
and [NeuroAbs](https://arxiv.org/html/2608.17304v1). All measured claims here
come from this experiment, not from those papers.

Local raw evidence: `/home/swear01/AIsimpV/artifacts/abstraction-search-20260921`.
It includes every screening model, raw generation log, candidate, CEX, snapshot,
qualification result, validation result and timing command. Local verification
passed all **177 unit tests**, the complete feasibility demo, the frozen public
rewrite matrix, and the existing finite-FIFO boundary assessment. The latter
still reports the older frontend's expected unsupported case; it is not a new
native-memory performance result.

Post-measurement review removed unused arguments/imports, validated witness
types before set construction, accepted CRLF rIC3 verdicts, and made the Linux
solver-cleanup regression use the active Python interpreter with an explicit
child-start check. The raw-byte candidate preflight remains conservative:
forbidden tasks and backticks in comments are also rejected. The v1 generation
and v4 measurement snapshots remain unchanged. The final implementation
regenerates byte-identical prepared models, property proofs and product proofs
for all five distinct accepted candidates, and identical models for all 33
single-cut controls (`post-review-proof-inputs.json` in the raw evidence).
