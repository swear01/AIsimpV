# Muse and DeepSeek direct-API RTL pilots, 2026-09-24

The local gateway now completes real `deepseek-flash` generation for AIsimpV.
Both DeepSeek V4.1 Flash and Muse Spark 1.3 Contributor generated certificates
for a fixed skid8 concrete/abstract pair. Both also generated a new 10-bit
abstract RTL design that passed the independent certificate gate and the frozen
safety property with its nondeterministic input free. These are successful
feasibility examples, not evidence of faster end-to-end verification or a new
abstraction method.

## Frozen task and outcome

The original 16,384-token runs gave both models byte-identical task bundles,
prompts and trusted verifier snapshots. The later DeepSeek snapshot changed
only its output cap. The fixed-pair task supplied both RTL designs and asked for an
`h/J/w` certificate. The joint task supplied only the 18-bit concrete RTL,
contract and syntax, and required a smaller abstract RTL plus certificate.
Each run allowed at most four attempts and 900 charged seconds, including
generation and verification. The model had no tools or gold certificate; the
parent exported the returned RTL and checked the saved candidate independently.
All runs used `reasoning_effort=high`. Muse used its direct API. DeepSeek used
`127.0.0.1:35001` with `deepseek-flash`; successful responses named
`opencode-go-1` as the gateway endpoint and `deepseek-flash` as the returned
model. Gateway metadata identifies routing, not the model weights independently.

| Run | Output cap | Attempts | Charged time | Result |
| --- | ---: | ---: | ---: | --- |
| DeepSeek fixed pair | 16,384 tokens | 1 | 62.213 s | Certificate ACCEPTED; property SAFE |
| Muse fixed pair | 16,384 tokens | 1 | 88.070 s | Certificate ACCEPTED; property SAFE |
| DeepSeek joint, original protocol | 16,384 tokens | 4 | 305.337 s | All four responses stopped at `length`; no candidate text |
| Muse joint, original protocol | 16,384 tokens | 3 | 304.273 s | Attempt 1 truncated; attempt 2 had a stale abstract hash; attempt 3: 10 bits, ACCEPTED, SAFE |
| DeepSeek joint, larger cap, initial run | 65,536 tokens | 1 | 115.075 s | Gateway HTTP 503; no candidate |
| DeepSeek joint, exact retry | 65,536 tokens | 2 | 150.586 s | Attempt 1 had a stale abstract hash; attempt 2: 10 bits, ACCEPTED, SAFE |

The larger-cap DeepSeek run is a **separate protocol amendment**, not a fifth
attempt added to the original four. Its first HTTP 503 and exact retry cost
265.661 seconds together. Including the original four truncated attempts,
DeepSeek spent 570.998 charged seconds on joint discovery. These values are
single search chains under different output caps, not comparable success rates
or repeat timing statistics. [DeepSeek's Chat Completions documentation](https://api-docs.deepseek.com/api/create-chat-completion/)
specifies a 64K thinking-mode default, and [Meta's reasoning documentation](https://dev.meta.ai/docs/reasoning)
explains why hidden reasoning consumes the output budget. `cost_usd` is
unavailable and was not estimated.
The gateway's historical Cloudflare 403 did not occur in the successful calls;
this does not establish that its separate 403 failover defect was repaired.

Both saved joint candidates have 10 exported state bits, down from the
concrete design's 18. They retain the visible data register and replace a
hidden data path with the free 8-bit input `z`. Muse also stores the inverse
of the original ready/valid control bit. Both certificates use `J=true` and
were accepted without changing the contract. This is the familiar data
cutpoint strategy already seen in the archived Codex pilot; it does not show
that either model found a new class of state representation. The earlier
[eight-repeat skid8 study](verification_timing.md) measured a 0.578-second median direct property proof;
the hundreds of seconds spent on these new search chains give no end-to-end
speedup on this task.

## Evidence and checks

Raw prompt, request, response, model/usage metadata, candidates, verifier
queries and ledgers are under the local project directory
`artifacts/local-gateway-20260924/`. The `rtl-pilots` directory holds original
DeepSeek runs; `rtl-pilots-meta` holds Muse runs; `rtl-pilots-deepseek-64k`
holds the HTTP 503; `rtl-pilots-deepseek-64k-retry` holds the successful exact
retry. Its `protocol-amendment.json` records the sole setting change.
`recheck-muse` and `recheck-deepseek-64k` reran the two saved joint candidates
in fresh output directories; each again returned 10 bits, ACCEPTED and SAFE.
The separate JSON transport smoke passed through the gateway with HTTP 200.

The evidence proves these two bounded tasks on one skidbuffer family. It does
not test larger designs, cross-family transfer, stronger non-LLM search, or
whether the generated RTL is suitable as a hardware replacement. The
formal property and certificate checks are the basis for the safety claim;
the model's own verdict was never trusted.
