# Bounded Codex pilots

This runner prepares issue #8. No discovery result is implied by its boundary tests.
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

Before the first generation, an actual `codex sandbox` probe verifies bundle read,
bundle overwrite rejection, candidate writes, hidden-file and symlink read
rejection, preservation of parent files, and blocked tool networking. Some
non-mounted parent paths may be writable inside an ephemeral namespace; the probe
also checks that these writes do not affect the host. Codex 0.154.0 cannot reliably
mount individual writable files, so the candidate directory is writable and the
parent rejects extra paths, symlinks and non-regular files afterwards. This is an
OS-enforced local-tool boundary, not a claim against defects in Codex or the OS.
If the probe fails, no model call occurs and the pilot remains blocked.

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

A repair prompt includes the prior candidate, its real checker feedback and any
new manifest verbatim. These are parent-selected task inputs, not inherited chat
history. A changed A must be exported again; the old certificate hashes are not
silently accepted. No human supplies h/J/w repairs while calling the outcome
unassisted discovery. If intervention is necessary, record it in the ledger's
`human_intervention` list and label the result assisted.

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
The other checks cover symlink and path escape, contract tampering, unauthorized
candidate files, mutation after capture, shared budget and attempt enforcement.
No mock result from these tests counts as an LLM experiment.

Official references: [permission profiles](https://learn.chatgpt.com/docs/permissions)
and [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).
The installed CLI's `exec --help`, `sandbox --help` and feature list were also
checked; profiles are currently a beta interface and the live probe is required
again when changing the tool version.
