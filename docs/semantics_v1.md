# Frozen public-task semantics v1

This profile extends [v0](semantics_v0.md) only to declare a synchronous reset
that is already an ordinary public input in the transition function. The four
new contracts are indexed, with exact source and canonical contract hashes, in
[sources.json](../fixtures/public/sources.json). This is a frozen task definition,
not a claim that the four experiments have completed. Existing `p1.json` and
`p5.json` retain their original bytes, hashes and v0 semantics.

## Reset and sampling

Contract JSON retains `version: 1` (the data format) and selects
`semantics: "single-clock-bv-v1"` (the semantic profile). `reset` is either `null`
or exactly:

```json
{"kind": "synchronous", "port": "i_reset", "active": 1, "assumption": "unconstrained"}
```

The port must be an existing public BV1 input distinct from the clock. `active`
is integer `1`, not Boolean `true`; extra fields, asynchronous reset, other
polarities and sequence assumptions are rejected. The only supported clock is
one named positive-edge clock. Environment remains literal `true`, and sampling
remains `before_update`. R1 uses `reset: null`; skidbuffer uses `i_reset`, and
pipeline uses `reset`.

At each step, all public inputs including reset are freely chosen. The checker
does not assert reset initially, suppress reset, clear state itself, or insert
an additional reset transition. `F(s,u)` contains the reset effect from the
actual RTL. The profile declaration documents that effect; it does not replace
the frontend's validation of the actual clocking and transition logic. Exact
model/contract hashes still bind each certificate.

An explicit source initial condition determines `s_0` independently of input
values. No omitted initialization becomes zero. All selected source registers
have explicit initial values; this does not add memory or symbolic-array
support. Observations at `t` precede the update to `t+1`. For a step property,
`o.*` means observations at `t`, `n.*` at `t+1`, and `u.*` public input at `t`.

## Four fixed tasks

| ID | Frozen contract | Inputs, observations and initialization |
| --- | --- | --- |
| R1-fsm | [r1_fsm.json](../fixtures/contracts/r1_fsm.json) | `advance: BV1`; `idle,busy,done: BV1`; three-bit concrete state starts at `001`, cycles through `010,100,001` on advance and otherwise holds. No reset. |
| R2-skid8 | [r2_skid8.json](../fixtures/contracts/r2_skid8.json) | `i_reset,i_valid,i_ready: BV1`, `i_data: BV8`; `o_ready,o_valid: BV1`, `o_data: BV8`; all four source registers initially zero. |
| R3-skid32 | [r3_skid32.json](../fixtures/contracts/r3_skid32.json) | Same ports and semantics as R2, with BV32 data. |
| R4-pipe32 | [r4_pipe32.json](../fixtures/contracts/r4_pipe32.json) | `dataIn,c1,c2: BV32`, `reset: BV1`; observations `dataOut,tmp_stageOne,tmp_stageTwo: BV32`; all five source registers initially zero. `c1` and `c2` are free inputs, not constants. |

R1 is an authored control, not a public benchmark. Its current-state property
requires exactly one of idle/busy/done to be one; all-zero and multiple-one
valuations violate it. Equality decoding of illegal encodings remains explicit.

R2/R3 use the unchanged ZipCPU source with `DW=8/32`, `OPT_OUTREG=1`,
`OPT_LOWPOWER=0`, `OPT_PASSTHROUGH=0`, `OPT_INITIAL=1`, and `FORMAL` undefined.
Both valid registers clear on reset. Data registers follow the original update
logic even during reset; they are not additionally cleared. The fixed property is:

```text
o_valid(t) && !i_ready(t) && !i_reset(t)
    => o_valid(t+1) && o_data(t+1) == o_data(t)
```

This is a derived port-level task on upstream RTL. It is not the complete
upstream formal suite: that suite has initial reset, input hold assumptions,
and a reset guard at both sampling times. Here the environment is unconstrained
and the hold implication uses only current reset. Direct and abstract proofs
must both use this same contract. Non-vacuity covers include accepted input,
buffer full, output stall, release of stall, and reset during stall.

R4 retains the original source predicate from line 38 and assertion at line 40:

```text
dataOut == tmp_stageTwo + tmp_stageOne || dataOut == 0
```

All arithmetic is BV32 modulo `2^32`. The frozen history monitor has
`tmp_stageOne' = stageOne` and `tmp_stageTwo' = stageTwo`, with both initial
values zero. Nonblocking updates mean that history and `dataOut` at `t+1`
refer to stage values at `t`. Reset only clears `dataOut`; stage and history
updates continue. A design-only export may remove the embedded assertion only
after verifying the original predicate and retaining it in a trusted external
harness. It must expose the two original history states, preserve their initial
values and updates, and record extraction/source/model hashes. The observations
cannot be replaced by an always-safe bad bit. Abstract stage views may change
only as part of the certified mapping of all states, including monitor states.

## Proof obligations and independent property proof

The v0 obligations are unchanged: nonempty concrete initial states, `INIT_J`,
`STEP_J`, `INIT_MAP`, `STEP_MAP`, and `OBS_MAP`. Reset is quantified alongside
the other public inputs, including in witness expressions. There is no added
reset assumption in the SMT queries. A missing abstract reset effect therefore
can produce a genuine `STEP_MAP` certificate counterexample.

The property backend takes the model and trusted contract without `h`, `J` or
`w`. Abstract nondeterministic inputs remain fresh and unrestricted. SAFE needs
a complete proof, and a failed certificate is never a design BUG. Unknown,
unsupported and error outcomes remain distinct. A replay must obey the same
initial conditions, public input/reset sequence and observations.

## Source provenance and redistribution

Vendored files retain exact upstream bytes; SHA-256 covers whitespace and
original notices. Any normalized design is a separate generated artifact with
its own hash. The source index records pinned revisions, parameters, raw source
hashes, initial states, original/derived property classification, and contract
hashes. Source/model/export/proof-tool hashes belong in each actual run record;
the source index does not pretend that a future model hash already exists.

The [ZipCPU source](https://github.com/ZipCPU/wb2axip/blob/2e8d3bc2d26ddc33d1881022a2a2b9d3f0c16b9b/rtl/skidbuffer.v)
has an explicit Apache-2.0 header, retained together with the license text.
The [AVR repository README](https://github.com/aman-goel/avr/blob/9a76dc632066c4416cebccda3a4974a4f8adede8/README.md)
directs AVR usage to its GPLv3 LICENSE. `pipeline.v` has no file-level license
header; its original companion README credits Aman Goel and identifies `vce11`.
Both that README and the repository LICENSE accompany the unchanged file. This
records the available repository-level licensing evidence and does not invent
a separate per-file notice or grant. These third-party notices do not assign a
new license to the independently implemented checker.
