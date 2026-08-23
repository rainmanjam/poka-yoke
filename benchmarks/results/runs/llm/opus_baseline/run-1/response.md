Yes — quite a lot else. The two prompt lines you added are what this framework calls **rung zero**: requests to a component with a non-zero error rate. They're worth keeping, but neither one can fail loudly, so neither is a device. Ranked by what's actually biting you:

**1. The model should never produce the amount at all.** This is the big one. You're asking it to *generate* a number from prose. Instead, fetch the order's refundable line items server-side and have the model *select* an ID from that list. Amount comes from your database, not from the chat message. Open-ended generation becomes a closed set a `Literal`/enum enforces — "refunds a weird amount" becomes unrepresentable rather than unlikely.

**2. Double refunds are a write-path bug, not a reasoning bug.** "Never refund the same order twice" can't hold under retries, duplicate webhooks, or two concurrent sessions. You need an **idempotency key** — deterministic, derived from the refund request (order ID + line item + a request UUID) — backed by a **unique constraint in the database**. Not a `SELECT` then `INSERT`: that's a TOCTOU race that fails exactly when traffic is high. Let the constraint reject the second write and return the first refund's result.

**3. Re-validate server-side regardless.** The refund endpoint must independently check the amount against the actual order total minus prior refunds, and reject anything over. The model is an untrusted client; its `amount` field is a proposal, not authorization.

**4. Structured output, not prose parsing.** If you're regexing or string-parsing the model's reply, switch to the provider's constrained-decoding mode with a schema, then validate the parsed object again in code. Decide the failure path explicitly — retry once with the error fed back, then hard-fail to a human. A silent default here is `except: pass` wired to your payment processor.

**5. Every production failure becomes an eval case.** You can't patch the model, so the regression test *is* the fix. Take the weird-amount transcripts and the double-refund transcripts, turn them into a held-out set with assertions on the structured fields, and run it in CI on every prompt or model change. Also pin the model version — a provider updating it under you is an unannounced deploy of your least predictable component.

**6. Bounds and alerting.** Cap refunds per conversation and per hour; alert on refund volume anomalies. That's your detection rung for whatever the first five miss.

---

★ Insight ─────────────────────────────────────
Devices 1–3 are *Control* rung — they make the mistake impossible or reject it deterministically. Devices 4–6 are *Warning* — they catch it after. The reason your prompt edits felt unsatisfying is that prompt text can't reach either rung; it has no failure mode that stops the action.
─────────────────────────────────────────────────

**One decision is genuinely yours, and it shapes the rest:** what refund can this bot execute with no human in the loop? Options — a hard dollar ceiling; only full refunds of single line items; only orders under N days old; or confirmation for every refund. That threshold determines whether device 1 needs the full line-item selector or something simpler.

Tell me that policy plus your stack and I'll write the endpoint, schema, and constraint.