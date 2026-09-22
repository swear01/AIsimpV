# Bounded direct-API pilots

The current runner calls provider Chat Completions APIs directly using Python's
standard library. It never starts Codex CLI or loads its configuration, system
prompt, rules, skills, tools or conversation history. Each request contains one
`user` message: the explicit task prompt, output JSON schema, canonical input
hashes and the complete audited bundle. Repair attempts add only this run's raw
candidate and actual independent verification feedback. Provider-side behavior
is outside this runner; removing the CLI does not imply access to a raw model.

## Models and credentials

[`scripts/llm_models.toml`](../scripts/llm_models.toml) freezes both profiles:

| CLI provider | Model | Endpoint | Credential environment variable |
| --- | --- | --- | --- |
| `meta` (default) | `muse-spark-1.3-contributor` | `https://api.meta.ai/v1/chat/completions` | `META_API_KEY` |
| `deepseek` | `deepseek-flash` (V4.1 Flash) | `https://api.deepseek.com/chat/completions` | `DEEPSEEK_API_KEY` |

Both use `reasoning_effort=high`, JSON-object output and a 16,384-token completion
cap; DeepSeek explicitly enables thinking. Temperature/top-p remain provider
defaults. The exact provider-specific request parameters are saved per attempt.
These settings do not imply equal reasoning effort across providers.

Keys must already exist in the launching process's environment. They are sent
only as authorization headers, never copied into the project, prompts, commands
or ledgers. HTTP redirects are refused. Missing keys fail explicitly; API failures
are recorded and stop the orchestration. There is no automatic provider fallback
or hidden retry. Use a separate run/workspace for each provider. The default is
Meta because it passed the live qualification below; DeepSeek is an explicit
selection until its account has usable credit.

Official references: [DeepSeek V4.1 Flash model ID](https://api-docs.deepseek.com/zh-cn/news/news260910/),
[Meta Chat Completions](https://dev.meta.ai/docs/protocols/chat-completions).

## Experiment boundary and evidence

The certificate pilot receives C, fixed A, their manifests, the frozen contract
and certificate syntax. The rewrite pilot receives C, its manifest, the contract
and permitted syntax. The coordinator audits bundle **contents**: never include
gold certificates, relationship hints, unrelated conversations or agent rules.
Generated text has no tool access. The parent materializes exact JSON string
values into `certificate.json` and, in rewrite mode, `abstract.v`; it rejects
extra paths, symlinks, hardlinks and strings larger than 65,536 bytes. Only the
independent verifier can produce an accepted result. Untrusted RTL is checked
for forbidden external file reads before Yosys receives it.

Each run retains four attempts and 900 seconds shared by generation and
verification. A separate HTTP worker is killed at the remaining wall-time limit,
including a stalled response body. Initialization freezes the model configuration,
runner and trusted inputs by hash. The parent rechecks them after generation and
before recording verification. Failed setup reserves and charges an attempt;
existing candidate files are never overwritten by a repeated setup. Interrupted
`RUNNING` records require investigation. One coordinator owns each run directory.

Retain `prompt.txt`, `output-schema.json`, `inline-inputs.json`, `request.json`,
`response.json` (when received), `command.json`, `stderr.txt`, `final.txt` (when
available), raw candidates and their hashes. The ledger records requested and
returned model IDs, request/response hashes, finish reason, token usage, generation
time and exact verifier feedback/time. Truncated, refused, tool-call or malformed
responses cannot become valid candidates. Token usage includes provider-reported
reasoning/cache details when available; `cost_usd` remains null rather than guessed.
No test fixture or transport smoke result counts as a research result.

```sh
python scripts/llm_pilot.py init --run results/llm-certificate \
  --bundle /absolute/path/to/audited-certificate-input \
  --trusted rtl_relate --trusted /absolute/path/to/frozen-contract-and-harness \
  --mode certificate --provider meta
python scripts/llm_pilot.py generate --run results/llm-certificate \
  --prompt /absolute/path/to/parent-written-prompt.txt
# Parent runs the real frontend/checker/property/replay and measures all stages.
python scripts/llm_pilot.py record-check --run results/llm-certificate \
  --feedback /absolute/path/to/real-feedback.json --seconds 12.34
```

`12.34` is a placeholder, not a measurement. The Python entry point is
`initialize(run, bundle, trusted_paths, mode, provider='meta')`; the other entry
points remain `generate(run, prompt_text)` and
`record_verification(run, feedback_object, seconds)`. Both task drivers expose
`--provider meta|deepseek`. For native RTL searches, use
`search_abstractions.py run ... --arm ai --provider meta`; `templates` uses no LLM.

Protocol version 2 refuses legacy Codex ledgers. Reproduce historical runs with
their frozen snapshots, and start new directories for API runs. Do not replace
old model labels or measurements. Human formula/RTL repairs require an assisted
label; record protocol amendments separately from candidate assistance.

Boundary checks need no API credentials or external model calls:

```sh
python -m unittest discover -s tests -p test_llm_pilot_boundary.py -v
```

They include a real local HTTP worker exchange, credential exclusion, frozen
inputs, candidate tampering, truncated output, redirects, shared budget and hard
timeout handling. Paths and ancestors must be physical, without symlinks.

## Live transport qualification (2026-09-22)

A separate trivial JSON task, containing no RTL or relationship hints, tested
both configured APIs. Muse Spark returned `muse-spark-1.3-contributor`, passed
verbatim materialization in 10.389 seconds, and reported 174 prompt tokens plus
657 completion tokens (635 reasoning; 831 total). DeepSeek's authenticated model
listing included `deepseek-flash`, but generation returned HTTP 402 in 0.578 seconds
([insufficient balance](https://api-docs.deepseek.com/quick_start/error_codes/));
DeepSeek generation is **not qualified** yet. Its failed attempt is retained.

Private raw evidence is under
`/home/swear01/AIsimpV/artifacts/direct-api-models-20260922/`: immutable transport
snapshot, prompt/request/response, candidates and both ledgers. This is API
qualification only; it supplies no new RTL correctness or speedup measurement.

## Task-specific orchestration

The task-specific orchestration is `scripts/run_llm_experiments.py`. `prepare`
checks the accepted qualification's canonical C/A/contract hashes and the
normalized RTL hashes, then copies only trusted core modules, C/A/contract,
the two harness scripts, `llm_models.toml` and the audited input whitelist into a read-only snapshot.
A certificate bundle contains C, A, contract and generic syntax; a rewrite bundle
contains C, contract and the same syntax. Initial prompts are kept separately
with audit hashes. The concrete task is skid8 and the rewrite pilot explicitly
requires fewer than 18 exported state bits; results do not generalize to arbitrary
rewrites or task families.

The trusted coordinator audits these exact inputs before changing `audit.json`
to `APPROVED_BY_ROOT`. This is an experiment-integrity check inside the already
authorized work, not another user approval request. Run the immutable copy:

```sh
python scripts/run_llm_experiments.py prepare --source-root /path/to/qualified/repo \
  --qualification /path/to/qualified/results --workspace /path/to/new/pilot-workspace
# After coordinator audit; preserve the original audit and record its approval.
RTL_RELATE_YOSYS=/path/to/yowasp-yosys \
  python /path/to/new/pilot-workspace/snapshot/scripts/run_llm_experiments.py run \
  --workspace /path/to/new/pilot-workspace --mode certificate --provider meta
RTL_RELATE_YOSYS=/path/to/yowasp-yosys \
  python /path/to/new/pilot-workspace/snapshot/scripts/run_llm_experiments.py run \
  --workspace /path/to/new/pilot-workspace --mode rewrite --provider meta
```

Both pilots stop at their first qualifying success or their fixed budget. Each
frontend/check/property phase runs in a separate process under a hard remaining
wall-time cap. The gate must accept before property checking. Every new A is
exported, and its full resulting manifest/hash is returned as real feedback;
the parent never changes certificate bindings on the model's behalf. Raw outputs,
failed exports, SMT queries and formal logs remain in the run. No checkout changes
can alter the running verifier because its imports come from the frozen snapshot.

On an abstract counterexample, the evaluator decodes the actual SMTBMC witness,
requires a feasible abstract prefix violating the frozen property, and replays
the resulting public trace on C within a separate 30-second remaining-budget
cap. Only a feasible concrete violating trace becomes BUG; an infeasible trace
is SPURIOUS_TRACE, while failed extraction/replay remains unresolved. The real
public trace and formal feedback are provided to the next generation attempt.

Saved raw candidates can be checked without any model request:

```sh
RTL_RELATE_YOSYS=/path/to/yowasp-yosys python - <<'PYTHON'
import sys
from pathlib import Path
sys.path.insert(0, 'scripts')
from run_llm_experiments import evaluate
snapshot = Path('/absolute/path/to/preserved/snapshot-v3')
print(evaluate(snapshot, 'rewrite',
               Path('/absolute/path/to/run-rewrite/attempt-02/candidate'),
               Path('/absolute/path/to/new-empty-recheck-directory'), 300)['status'])
PYTHON
```

`evaluate` imports the preserved verifier snapshot. The development implementation
normalizes all three paths to absolute paths; the historical v3 copy requires
absolute arguments. Its phase workers retain hard time caps and complete logs.
The current parent materialization additionally uses directory descriptors,
`O_NOFOLLOW` and single-link regular-file validation. This hardening postdates
the measured v3 run; its old source and raw candidates remain unchanged.

## Historical Codex experiments

All September 21 results below used the archived Codex runner, not the current
direct API implementation. Their snapshots, ledgers and measured costs are unchanged.

For the recorded September 21 execution, fixed-pair attempts 1–2 used the original
file-tool transport and attempts 3–4 used its unsuccessful Code Mode workaround.
All four failed at infrastructure access before a meaningful certificate was
produced; the fourth was automatically queued before the coordinator paused the
loop. That pilot remains `INFRASTRUCTURE_BLOCKED`, with zero meaningful discovery
attempts and all four costs retained. It was not restarted under a fresh budget.
The separately budgeted joint pilot used the approved inline transport from its
first attempt. Its first candidate had a stale abstract hash; actual export
feedback allowed the model to correct the certificate on attempt two while
retaining the exact same RTL. The gate then accepted and the free-choice property
was proved. `protocol-amendment.json` records transport changes and the absence
of human candidate formula edits, tied to both immutable raw ledger hashes.

## Separately registered fixed-pair follow-up

The complete Wednesday-delivery goal authorized a new fixed-pair experiment after
the original infrastructure failure. Its [preregistration](llm_certificate_followup.md)
was also [published on issue #9](https://github.com/swear01/AIsimpV/issues/9#issuecomment-5754280390)
before candidate generation. It adds at most four submissions and 900 charged
seconds beyond the original two pilots' allocation. Keep the original ledgers,
attempt counts and costs; report this run separately and include it in cumulative
costs. It is not a resume or reset of the infrastructure-blocked run.

The fixed C/A/contract bytes are unchanged. That historical run used the inline
Codex transport already used by the joint pilot. Before research generation, a separate
trivial structured-output model call qualifies that actual transport; its prompt
contains no RTL or relationship hints. Save its cost and any diagnosis separately
from research attempts. A subsequent clean-source verification of saved candidates
is also a separate verification cost, not another generation attempt.
