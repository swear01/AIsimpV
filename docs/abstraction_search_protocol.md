# AI abstraction search pilot

Status: screening protocol frozen before running new candidates, 2026-09-21.
Base: `8314459e35013456e26b231119f712d4e420a05e`.

The first-stage target is approximately three RTL/property tasks whose direct
complete proof takes 20–60 seconds (prefer approximately 30 seconds). A timeout
on every strong engine is not required. No manually successful abstraction is
required before AI search. A failed search is not evidence that no useful
abstraction exists.

## Selection

Start with pinned public AVR benchmarks already available locally, then the
NeuroAbs artifact and published parameterized designs with native assertions.
Preserve source bytes, native assertion set, assumptions and initialization;
record any public parameter configuration before timing it. Do not increase
unrolling depth merely to inflate runtime or disable normal preprocessing.
Screen with a 60-second per-task deadline. Record ERROR, UNSUPPORTED, CEX,
BOUNDED and timeout as well as SAFE. Freeze the first approximately three
eligible tasks before attempting abstraction; prefer distinct designs/families.
Repeat qualifying measurements three times serially with fresh tool processes.
No build or competing formal task runs during qualification timings.

Use a fixed primary engine/configuration for comparisons. A second engine is
a cross-check, not an additional admission requirement. Record versions, source
and model hashes, machine, commands, assertions/assumptions and all logs.
If no tasks qualify in the first batch, publish that batch and explicitly record
the next screening batch before running it; do not silently select successes.

## Comparisons

1. Direct original RTL proof after ordinary preprocessing.
2. Non-LLM search over explicitly documented fixed abstraction templates.
3. NeuroAbs original artifact where available; otherwise identify precisely the
   reimplemented subset and deviations, without calling it the original tool.
4. AI abstraction/representation search with actual correctness, counterexample
   and runtime feedback. It may propose new mappings and relations but need not
   use a particular abstraction form or reduce state bits.

Freeze selected models/contracts and independent verifier before generation.
Both AI arms use the same model, reasoning setting and bounded search resources.
Initial cap: four generation attempts and 900 seconds of charged generation plus
verification per task and AI arm. Any resource amendment must be recorded before
additional calls. All failed attempts and interventions remain in the ledger.
Run experiments using the existing authenticated CLI; do not purchase services.

## Acceptance and cost

Accept only sound overapproximations covering the original legal executions and
a complete proof of the frozen property. No unproved relation may be introduced
as an environmental assumption. Preserve native formal monitors. Spurious
counterexamples and proof/certificate timeout are distinct from design bugs.

Report separately: original/abstract property wall time with identical timing
boundaries; accepted-candidate validation including abstraction correctness;
and complete discovery cost including every failed attempt. 30/0.3 is 100× for
that measured phase, not automatically an end-to-end 100× result. Keep 100× as
a target, not an acceptance rule that suppresses smaller or negative results.
Remeasure fixed successful candidates; report variability and all selected tasks.

Keep original artifacts immutable. New runs use new output directories. Reports
must distinguish executed results, implementation limitations and proposed work.

## Screening batch 1 (before execution)

Primary engine: existing SMTBMC/Z3 with native assertions; catalog depths remain
20 for AVR and 4 for upstream FIFO. Secondary engine: rIC3 1.5.2, single-thread
IC3, once its build is qualified. This does not require every engine to be slow.
Ordered catalog: `fixtures/public/abstraction_search_candidates.json`, nine public
AVR controller/datapath tasks followed by three public FIFO configurations.
FIFO configurations are 64×64, 64×128 and 256×64, using existing upstream
parameters. They count as one family. Run all twelve at a 60-second deadline,
without inspecting abstraction success when selecting.

NeuroAbs artifact investigation: DOI 10.6084/m9.figshare.30633074 version 2
contains only `detail result.xlsx` (14,103 bytes); the author publication page
also has no implementation link. An implementation comparison is therefore not
yet available. Preserve the downloaded metadata/table and document any later
reimplementation explicitly.

## Screening batch 2 (before execution)

Batch 1 has no qualifying 20–60 second complete proof. Its three FIFO instances
prove in approximately 8–11 seconds; tree arbiter at approximately 36 seconds is
only BOUNDED, and buffer allocator/am2901 time out. Preserve all twelve results.
Next screen existing FIFO parameter settings, in order `(BW, LGFLEN)`:
`(128,8), (128,10), (256,8), (256,10), (64,12)`. These are native parameter
settings without RTL or property edits, all depth 4 and deadline 60 seconds.
They remain a single design family; any resulting three-instance pilot must be
reported as such. Continue examining distinct controller families with rIC3
when its pinned build is available, without requiring them all to time out.

## rIC3 controller screening (before execution)

Use rIC3 1.5.2 `-e ic3` on the original native assertions of tree_arbiter,
buffer_alloc_h, am2901, rcu, buffer_alloc, usb_phy, sdlx, heap, am2910, in that
order, with normal preprocessing and one combined bad output. Preserve
assumptions; cover cells are irrelevant to this safety run and are removed only
from the BTOR export. The deadline is 60 seconds including preparation.
Controller cases qualifying on this engine may join the pilot with rIC3 as
their fixed comparison engine; never compare times across different engines.
This is recorded before seeing their rIC3 timings. rIC3 was built from locked
crates.io 1.5.2 with nightly-2025-11-15 after diagnosing incompatible newer Rust.

## Screening batch 3 (before execution)

Batch 2 produced one provisional qualifying SAFE result: FIFO 256×256 at
23.746 seconds. Other widths/capacities took 17–18 seconds; the nonmonotonic
runtime is retained, so capacity is not treated as a reliable complexity proxy.
Screen three further native FIFO configurations: BW=512, LGFLEN=6/8/10, with
the same flags, depth 4, engine and 60-second deadline. These are still one
family, not additional independent controller designs. Any qualifying task
requires three serial confirmation runs before being frozen for abstraction.

## Provisional selection and native adapter

Before any abstraction generation, select the first three eligible screening
results in catalog order: FIFO 256×256 (23.746 s), 64×512 (52.560 s), 256×512
(34.426 s). FIFO 1024×512 (39.030 s) is retained as an unselected result, not
substituted based on later abstraction outcomes. Confirm the selected three
serially three times. This pilot currently covers three configurations of one
public family; it cannot support a cross-family generalization claim.

The original finite-BV h/J/w checker cannot import native memories and partial
initialization. Add an explicit native-memory adapter rather than silently
zero-initializing or deleting assertions. It exposes each native assertion's
exact A/EN bits as observations, preserves the original state/initialization and
turns original anyconst cells into shared constant-choice input ports. The final
property harness recreates those constant choices and asserts every original
enabled predicate, with any new abstract input independently free each step.

The native certificate supplies witnesses naming current concrete signals for
all extra abstract inputs and optional typed helper relations. An independent
synchronous product proves equality of original public outputs and enabled
assertion violations, plus every helper relation. Helpers are asserted, never
assumed. For every original execution, the witnesses choose a legal abstract
input sequence, so a complete product proof is sufficient for inclusion. All
abstract initial states are universally checked; no existential initial-state
mapping is assumed. This can reject valid abstractions but cannot waive a failed
mapping. The adapter rejects original assumptions, candidate formal constructs,
multiple/negative clocks, asynchronous writes and unsupported cells. Compiler
normalization and the model checker remain in the trusted base.

Report this product certificate separately from the existing five-obligation
h/J/w checker. Its cost must be charged, including failed induction or timeout.
Recheck the normalized original with the same regenerated property harness used
for A, and use that matched boundary in the final speedup comparison.

## Frozen search arms (before generation)

All nine qualification runs completed SAFE. Original-source medians are
24.399, 52.830 and 35.371 seconds in the selected order. The matched normalized
originals initially took 19.336, 28.406 and 31.480 seconds; this normalization
effect is not AI speedup. Use fresh repeated matched timings for final ratios.

The fixed template is single-vector havoc. Eligible cuts are distinct visible
internal vectors of at least two bits, excluding primary ports, constants,
aliases with identical bit vectors and overlapping cuts. Try the four widest
eligible vectors, breaking ties lexically, before inspecting any cut result.
The transformer disconnects their drivers and introduces free per-cycle inputs;
it retains all assertion monitors and uncut initialization. Original values
witness inclusion by construction, with no separate theorem-search charge.

The NeuroAbs-inspired arm uses the same transformer, lets the model select
multiple eligible nonoverlapping cuts, and returns actual CEXs for refinement.
It does not implement NeuroAbs's AST-local expression rewriting or published
counterexample-reduction algorithm. This is a partial comparison of LLM-guided
cutpoint selection, not the original NeuroAbs or a full reproduction. Original
implementation comparison remains unavailable with the retrieved artifact.

The full AI arm generates arbitrary design-only synchronous RTL and a native
witness certificate. It receives the exact original/normalized RTL, port and
signal manifests, contract, syntax, actual errors/CEXs and measured proof costs.
No manually useful candidate is supplied. Both AI arms use the existing Codex
configuration (gpt-5.6-sol, high reasoning), four attempts and 900 seconds per
task including all generation and verification. Each task/arm starts fresh.
The verifier, model bundle and normalization contract are frozen and hashed;
candidate bytes are never repaired by the parent.

## Recorded controls and verifier correction during the pilot

After two cutpoint arms returned unchanged candidates, add an explicitly
post-hoc control that enumerates all eleven eligible single cuts per task,
lexically, with a 900-second cap. It supplements the original four-template
comparison and does not replace it. Also run rIC3 on the same three original
FIFO configurations with 60-second deadlines; keep selection and primary
SMTBMC comparisons unchanged.

A negative boundary probe found that Yosys honors an `init` attribute on an
input: the original first-cycle assertion had a CEX, while the v1 product gate
incorrectly returned SAFE after restricting that input. Fix the adapter to
allow nontrivial initializers only on stored state, reject conflicting state
and memory-read initializers, and reject asynchronous memory read resets.
The regression reproduces the unsafe original and requires candidate rejection.

Keep the generation snapshot and every v1 ledger immutable. Revalidate all
provisionally accepted full-AI candidates with a separately frozen corrected
snapshot; charge that additional validation separately. No generated RTL or
certificate is repaired. Select each task's candidate by the lowest original
total validation time among those accepted by the corrected verifier, then
repeat that fixed candidate and matched original three times serially. Pilot
development timings are exploratory; final timings have no competing local
formal, build or test processes. The AI generation budget remains unchanged.

The final verifier snapshot also propagates the shared evaluation deadline into
every nested frontend/solver call, giving those process groups time to clean up
before their Python supervisor exits. A live sleeping-descendant test checks
that a timed-out evaluation leaves no solver running. Cleanup overhead is
charged. Source snapshots v2/v3 are retained unused intermediates; v4 is the
final corrected-verifier snapshot used for revalidation and repeated timings.
Exact duplicate candidate bytes within the same frozen task reuse their v4
proof, with zero *additional* revalidation cost and an explicit evidence link;
their original generation and verification costs are still fully charged.

After the 64×512 fourth full-AI attempt supplied eight helper relations and
passed the previously failed induction check, additionally repeat any distinct
accepted stateful candidate three times even if a stateless proof-transfer
candidate had lower total validation time. This preserves the structurally
different result without replacing the original winner-selection rule.

Post-measurement review cleanup does not replace either frozen snapshot or
change selection. Check byte identity of all five distinct accepted candidates'
prepared models and proof inputs, and all 33 single-cut models, against v4;
retain the comparison in `post-review-proof-inputs.json`. The conservative
raw-byte preflight also rejects forbidden tokens inside comments.


## Prospective model/transport amendment — 2026-09-22

Future AI runs use direct Chat Completions APIs, not Codex CLI. The default is
`muse-spark-1.3-contributor` (`META_API_KEY`); explicit `--provider deepseek` selects
`deepseek-flash`, the V4.1 Flash ID (`DEEPSEEK_API_KEY`). Project settings,
reasoning effort, token caps, explicit prompts and exact request/response bytes
are recorded as described in the [current runner protocol](llm_protocol.md).
Both profiles use high reasoning; provider defaults otherwise remain recorded
by the request rather than inferred to be equivalent.

Each attempt sends one user message, no system/developer message or tool schema.
No Codex configuration, agent rules or inherited session is loaded. Native
assertions, reset/init, assumptions, independent correctness/property checks,
selection criteria, four attempts and the shared 900-second budget are unchanged.
New runs have separate ledgers; there is no cross-provider fallback or pooling.
The template arm remains deterministic and independent of model configuration.

Meta passed a separate transport-only smoke. DeepSeek generation returned HTTP
402 and is not qualified until account credit is available. These checks contain
no candidate relationship hints and are outside research budgets. This amendment
does not relabel the completed Codex experiment or alter its frozen evidence.
