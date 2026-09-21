# Bounded Codex pilots

This runner implements issue #8. Boundary tests alone do not imply a discovery result.
The current transport supplies the audited bundle verbatim inside the prompt,
with canonical JSON hashes as metadata. Codex returns schema-constrained strings
for RTL/certificate text; the parent materializes them without editing formulas,
RTL or hashes. Model shell tools and Code Mode are disabled. Output filenames are
fixed, strings are bounded, and parent writes reject symlinks and hardlinks.
The parent verifier authorizes the frozen input bundle and starts the two pilots
only after the skid8 gold pair has passed its checks. Each pilot has its own
ledger, at most four submitted candidates, and 900 seconds for generation plus
frontend, certificate, property and replay work. Syntax/type failures count.

The certificate pilot receives C, the fixed A, their actual manifests, the frozen
contract, and certificate syntax. The rewrite pilot receives C, its manifest,
the contract, permitted RTL syntax and certificate syntax. Neither input bundle
contains a gold certificate, candidate formulas from the research plan, unrelated
conversations, Git metadata or agent instructions. The trusted parent must audit
bundle **contents**: a filesystem allowlist cannot detect a solution pasted into
an otherwise permitted text file.

Use the installed Codex CLI and the existing OpenAI model/reasoning configuration.
Initialization reads only the configured model and effort into the public run
configuration; the complete configuration is hashed, not copied. Each generation
is a fresh, ephemeral `codex exec`, ignoring user configuration and rules, with
project instruction loading, host skill discovery, hooks, plugins, apps, memories,
web search and subagents disabled. Authentication remains with the existing Codex
installation; the runner never copies credentials. The generation tools receive
a read allowlist for the bundle and minimum runtime, a single candidate directory
as their writable host scope, and no network access. The model service connection
is handled by Codex itself, outside the model's shell sandbox.

Before the first generation, an actual `codex sandbox` probe checks the underlying
local-command profile: bundle read,
bundle overwrite rejection, candidate writes, hidden-file and symlink read
rejection, preservation of parent files, and blocked tool networking.
Network denial requires `PermissionError` with `EPERM` or `EACCES`; timeout,
connection refusal, and an unreachable network fail the probe.
Some non-mounted parent paths may be writable inside an ephemeral namespace; the probe
also checks that these writes do not affect the host. Codex 0.154.0 cannot reliably
mount individual writable files, so the candidate directory is writable and the
parent rejects extra paths, symlinks and non-regular files afterwards. This is an
OS-enforced local-tool boundary, not a claim against defects in Codex or the OS.
If the probe fails, no model call occurs and the pilot remains blocked. This
probe does not qualify the entire `codex exec` tool stack: the original file-tool
transport passed it but subsequently failed in a nested bwrap loopback setup.
That failure is why the current transport needs no model filesystem commands.

Only `certificate.json` is accepted in certificate mode. Rewrite mode additionally
accepts `abstract.v`. A generated `SAFE` statement or verdict file has no authority.
C, contract, checker and harness files are outside the writable scope and are
hashed before and after each generation and before recording verification.
Parents verify **raw saved candidates**; candidate changes after capture are
rejected. Model output remains untrusted RTL: the parent must prohibit external
`include`/`readmem`/system-task reads or isolate Yosys before compiling it.

The runner is deliberately separate from verification:

```sh
python scripts/llm_pilot.py init --run results/llm-certificate \
  --bundle /absolute/path/to/audited-certificate-input \
  --trusted rtl_relate --trusted /absolute/path/to/frozen-contract-and-harness \
  --mode certificate
python scripts/llm_pilot.py generate --run results/llm-certificate \
  --prompt /absolute/path/to/parent-written-prompt.txt
# Parent runs the real frontend/checker/property/replay, timing all stages.
python scripts/llm_pilot.py record-check --run results/llm-certificate \
  --feedback /absolute/path/to/real-feedback.json --seconds 12.34
```

The sample `12.34` is a command placeholder, not a measurement. The equivalent
Python interface is `initialize(run, bundle, trusted_paths, mode)`,
`generate(run, prompt_text)` and `record_verification(run, feedback_object, seconds)`.
The parent checks the ledger's remaining budget before running each verification
stage and sets stage timeouts accordingly. It charges frontend failures and all
formal/replay costs. Generation automatically uses the remaining total budget as
its timeout. Wall time is separately retained, including coordination idle time;
it is not silently substituted for charged tool time. No concurrent writer may
operate on one run directory. Each generation reserves an attempt before launch;
an interrupted `RUNNING` record needs explicit investigation and is not retried
under a fresh budget.

The development runner writes ledgers atomically and reserves the attempt before
candidate setup or the isolation probe. Setup failures retain their elapsed cost
and terminate as `ISOLATION_OR_RUNNER_ERROR`; resuming that terminal run returns
the same ledger without another attempt. Existing candidate directories are never
cleared. Every infrastructure-failed attempt permits only infrastructure-error
feedback, even if a candidate hash exists and modified trusted files are later
restored. Candidate hashes still must match. These post-pilot guards do not modify the archived runner
snapshots or retroactively change the original measurements.

A repair prompt includes the prior candidate, its real checker feedback and any
new manifest verbatim. These are parent-selected task inputs, not inherited chat
history. A changed A must be exported again; the old certificate hashes are not
silently accepted. No human supplies h/J/w repairs while calling the outcome
unassisted discovery. Record infrastructure/protocol amendments separately from
candidate formula assistance. Use the ledger's `human_intervention` list, or a
reviewed sidecar bound to the immutable raw ledger SHA256; do not interpret an
empty raw list as proof that no protocol amendment occurred. Human formula/RTL
repairs require an assisted-result label.

For every attempt retain `prompt.txt`, `events.jsonl`, `stderr.txt`, `final.txt`,
`command.json`, raw candidate files/hashes, generation status/time, exact formal
feedback, charged verification time, and any usage emitted by Codex. `usage` and
`cost_usd` remain null when unavailable. The CLI model option and CLI version are
recorded; the provider's internal model routing is not inferred. The ledger has
parent-only verification records and source hashes. Audit the run before public
publication: preserve the original private copy and redact machine-specific paths
from a separately marked public copy if necessary. Never publish auth/config
contents or unrelated session history.

Run the boundary checks without making model requests:

```sh
python -m unittest discover -s tests -p test_llm_pilot_boundary.py -v
```

The live OS probe requires Linux, `/usr/bin/python3`, and a current Codex CLI. CI
without Codex skips that one check; it does not claim isolation was tested there.
Pilot paths and their ancestors must be physical directories without symlinks;
symlinked roots are deliberately rejected rather than normalized across the boundary.
The other checks cover symlink and path escape, contract tampering, unauthorized
candidate files, mutation after capture, shared budget and attempt enforcement.
No mock result from these tests counts as an LLM experiment.

Official references: [permission profiles](https://learn.chatgpt.com/docs/permissions)
and [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).
The installed CLI's `exec --help`, `sandbox --help` and feature list were also
checked; profiles are currently a beta interface and the live probe is required
again when changing the tool version.

The task-specific orchestration is `scripts/run_llm_experiments.py`. `prepare`
checks the accepted qualification's canonical C/A/contract hashes and the
normalized RTL hashes, then copies only trusted core modules, C/A/contract,
the two harness scripts and the audited input whitelist into a read-only snapshot.
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
  --workspace /path/to/new/pilot-workspace --mode certificate
RTL_RELATE_YOSYS=/path/to/yowasp-yosys \
  python /path/to/new/pilot-workspace/snapshot/scripts/run_llm_experiments.py run \
  --workspace /path/to/new/pilot-workspace --mode rewrite
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
