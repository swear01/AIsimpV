# Skidbuffer occupancy rewrites

These are authored gold fixtures for frozen tasks R2-skid8 and R3-skid32.
They are not evidence of autonomous LLM discovery. The concrete RTL is the
pinned, unmodified `../upstream/skidbuffer.v`; its revision, license, and
parameters are recorded in the public source manifest.

`skid_abstract.v` preserves output data and replaces both valid bits with a
2-bit occupancy state. `COARSE=0` forgets only buffered data, using free `z`
when buffered data reaches the output. `COARSE=1` takes free `z` every cycle,
so it deliberately loses the stall/hold relation. Initial occupancy and output
data are zero. Synchronous reset clears occupancy; it does not directly reset
output data. The unused occupancy encoding 3 has an explicit next state 0.

```python
from rtl_relate.skid_cases import prepare_case
case = prepare_case(8, "good", "results/skid8/frontend")
# Also supported: width 32 and variants "coarse", "bad_certificate".
```

The returned dictionary contains actual exported models, the frozen contract,
a hash-bound authored certificate, source/top/parameter descriptions for the
formal proof driver, actual frontend costs, and three hand-authored trace
probes. Calling this function does not claim any proof result. The main
experiment runner must retain the gate, property proof, and trace checks.
Returned proof sources are the frontend's elaborated `normalized.v` files;
their parameters have already been applied. The original parameter values
and source hashes remain in each retained `frontend.json`.

The negative certificate uses the identical good model and mapping/invariant,
changing only its witness to zero. Certificate construction binds exact typed
manifest origins, not fuzzy name matches. The coarse certificate instead uses
the concrete output-data next-state function as its witness.

The probes exercise accepted input, full buffering, stall, release, and reset
while stalled; establish an extra legal abstract trace; and demonstrate a
coarse property counterexample. Each trace requires abstract-prefix SAT and
exact concrete replay before being reported as evidence. The strict trace
preserves the hold property but changes the released buffered value. The
coarse counterexample changes output data during a stall.

Run the actual RTL/SMT regression checks with:

```sh
python -m unittest discover -s tests -p test_skidbuffer_rewrite.py -v
```

The task's property is the derived port-level hold contract. It is not the
upstream complete FORMAL suite. `z` stays free for abstract property checking;
the witness belongs exclusively to the certificate harness.
