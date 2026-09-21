# Paired verification timing follow-up

Registered before collecting new timings, on source base `0d2a98a`.
The question is whether the existing rewrites reduce actual property-proof
time, and whether any saving covers certificate/translation costs.

- Fixed pairs: the four existing good manual pairs and the unchanged successful
  joint LLM skid8 candidate. The latter shares R2's concrete design/contract;
  this is five candidate pairs, not five independent benchmark families.
- Same frozen contracts, pinned YoWASP Yosys/Z3, existing `prove_rtl`, depth 20,
  base plus induction, and 120-second per-proof limit. No new assumptions,
  witnesses or certificate invariants enter the property harness.
- Two recorded warm-up pairs per candidate, then eight measured pairs. Alternate
  C/A execution order, balanced four each; rotate candidate order across rounds.
  All tool runs are serial; no agent launches competing formal jobs.
- Fresh tool processes and fresh output directories each time. OS/filesystem
  caches are not flushed. This is repeated warm-system latency, not cold boot
  or a claim of exclusive hardware ownership. Retain load/CPU metadata.
- Re-export both models and recheck the certificate for every pair. Bind all
  repeats to identical model/contract/certificate and property-source hashes.
  Preserve every warm-up, failure, timeout, raw command and output.
- Report (1) SMTBMC + Z3 base/induction process wall time, including their
  startup; (2) full property-driver wall time, including ordinary preparation,
  version checks and evidence I/O; (3) known-candidate validation cost:
  C/A translation + certificate + abstract property + orchestration, measured
  as pair wall time minus the actual concrete property call. The three-stage
  subtotal and remaining orchestration are also retained. Per-record reporting
  I/O is captured in suite wall time. The baseline starts from
  frozen normalized C and runs its ordinary property preparation. Both C and A
  use their export's normalized RTL, including FSM and pipeline; the older
  pilot used some raw sources, so these are new controlled measurements rather
  than replacements for its timings. Translation cost is explicit, never hidden in a claim
  about pure solver time. The third metric excludes finding the candidate and
  research-only cover/strictness/reverse checks, so it is not total research cost.
- Summaries show all eight values, median, range, paired ratios and wins. A
  missing/failed proof prevents a complete-pair speed comparison; failures are
  not filtered into a success-only median. No optional stopping or changing
  depth/engine to favor A after viewing timings. One run-wide 900-second budget.
- Existing LLM generation/failure costs remain separate (joint 86.784 seconds,
  fixed-pair follow-up 38.610 seconds, original infrastructure failures 309.740
  seconds). This experiment calls no model and cannot establish amortization
  across properties, general speedup, or benefits of feedback.

Outcome is initially NOT_RUN. Publish a linked report and raw manifest after
the fixed run; original Wednesday data and release assets remain unchanged.
