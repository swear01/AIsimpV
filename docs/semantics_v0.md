# Frozen semantics v0

The two trusted contracts are `fixtures/contracts/p1.json` and `p5.json`. Their hashes are included in every certificate and experiment result. The runner verifies that the authored fixture contract equals the checked-in contract before running a candidate. Source/model/contract changes invalidate old certificate bindings; acceptance is valid only for the recorded exact hashes.

## Models and sampling

A model is a total deterministic next-state function of its current state and registered inputs. Concrete C has only public inputs u. Abstract A may additionally have a fresh freely chosen z at each step. Logical state s_0 satisfies I_C; s_(t+1)=F_C(s_t,u_t). Observations are sampled from the current state/input at t, before that update. No stuttering, latency changes, multi-clock scheduling, liveness, fairness, X/Z, blackboxes, or symbolic arrays are supported.

The validated frontend clock name and positive edge remain in each model and must equal the frozen contract. Reset is absent in these fixtures; reset protocols and nontrivial environment assumptions return UNSUPPORTED. The RTL adapter requires fully defined constant initial states. The manual IR supports arbitrary state-only initial predicates, including unconstrained bits, but never fills omitted values with zero. Empty concrete initial sets are rejected before proving any implication.

Symbols have design-bound IDs, state/input/nondet kind, Bool or exact unsigned-BV representation width, signedness provenance, and exact origin. Signed operations are explicit (currently sign extension only); no Python integer promotion is used. Public input origins are exact port identities, not guessed similar names. The model digest binds the manifest, initial predicate, every next-state expression, and observations together. Every abstract state and registered z must appear exactly once in h and w.

## Certificate and obligations

h and J may reference only current concrete states (`c.<id>`). w may also reference current public inputs (`u.<port>`). Abstract/next/future-input references, missing bindings, wrong widths, duplicate JSON keys, and executable certificate text are rejected. Certificates are typed JSON expression trees, never Python eval or caller-provided SMT commands.

After a nonempty initial-domain SAT check, the gate sends the negation of each implication to Z3:

```text
INIT_J:   I_C(s)                  => J(s)
STEP_J:   J(s)                    => J(F_C(s,u))
INIT_MAP: I_C(s)                  => I_A(h(s))
STEP_MAP: J(s)                    => F_A(h(s),u,w(s,u)) = h(F_C(s,u))
OBS_MAP:  J(s)                    => O_A(h(s),u,w(s,u)) = O_C(s,u)
```

E=true is fixed. Free SMT state/input constants make any violating assignment discoverable; only all five UNSAT results yield ACCEPTED. The same w is substituted in next and observation. Abstract admissibility constraints and new assumptions are not expressible in this model schema. Unknown/timeout is never accepted; parser, binding, and process failures are separate errors. A SAT obligation refutes this certificate and is not a design bug verdict.

These conditions establish a sufficient forward simulation and transfer safety over the frozen observations. They are not a complete decision procedure for arbitrary refinement. See [Abadi/Lamport](https://www.microsoft.com/en-us/research/publication/the-existence-of-refinement-mappings/) for the underlying refinement-mapping concept. Fixed-width arithmetic follows [SMT-LIB bit-vector semantics](https://smt-lib.org/theories-FixedSizeBitVectors.shtml).

## Property and replay

The property entry point accepts only a model and trusted contract: there is no certificate, concrete state, h, J, or w parameter. All abstract z remain unconstrained and fresh. The v0 property is a Bool predicate over current/next observations and current public inputs. Observations in this layer must be Moore; Mealy property/replay returns UNSUPPORTED even though the certificate gate can check Mealy correspondence.

An UNSAT all-state one-step violation query proves every transition preserves the predicate, hence every reachable trace does. If that query is SAT, a complete finite reachable-state exploration establishes reachability or finds an actual abstract trace. Limits are 65,536 state/input/nondet valuations, 100,000 visited transitions, and the query time budget for exploration. Hitting a limit returns UNKNOWN; no bounded absence is reported as SAFE.

Replay fixes the public input sequence and complete observation prefix on C, then asks for a legal sequence from its initial state. It does not copy z from A. FEASIBLE means that exact prefix exists; INFEASIBLE means that exact prefix does not. BUG additionally requires an observed violation of the frozen property. A different concrete trace found by concrete search is identified as such and charged separately.

## Evidence and trust

Queries, raw solver output, exit code, tool/source hashes, counterexample SMT assignments, symbol bindings, and wall times are retained. Z3 returns exit code 1 for the expected `get-model` diagnostic after UNSAT/UNKNOWN; only that exact output shape is permitted. Other nonzero exits or mixed/malformed output return ERROR. Tests exercise both real solver results and injected process failures.

This is an independent checker relative to a future generation agent, not a formally verified checker. Frontend, translation, exploration, and solver remain trusted. Current fixtures contain only authored gold candidates and intentional mutants; filesystem sandboxing for a future generator is not yet implemented.
