Short answer: yes — and the two prompt lines you added are the one thing that won't fix it. You're describing a question, not a code change, so here's the assessment.

## Why the prompt edits won't work

The model already *intended* to extract the exact amount and not double-refund. Both failures happen at some non-zero rate per call no matter what the prompt says; "be careful" lowers the rate a little and never to zero. Testing looked clean because you ran it a few dozen times; production runs it thousands. The fix has to live **outside the model**, in code that can't be persuaded.

## The four devices, in order of payoff

**1. The model never decides the amount — it picks from what the order allows.**
Look up the order server-side first. Pass the model the order's line items, paid total, and already-refunded total. The tool schema then becomes:

```
issue_refund(order_id: enum[orders this customer owns],
             amount_cents: int,
             reason: enum["damaged","late","not_as_described","other"])
```

And the handler **re-derives the bound itself**: `0 < amount_cents <= order.total - order.refunded`. A "weird amount" ($4,500 instead of $45.00, a dollar figure the customer typed that was the *item price* not the order price, a currency/cents mixup) gets rejected by code, not by hope. Ranges on numbers, enums on strings, no free-text "notes" field. This is the Control rung.

**2. Idempotency key + unique DB constraint.**
Key = `order_id` (or `order_id + reason` if partial refunds are legitimate). Put a `UNIQUE` constraint on it in the refunds table, and pass it through as the idempotency key to your payment provider too (Stripe/Adyen/etc. all support one). Now the double-refund is *unrepresentable*: second attempt hits the constraint and returns the original refund. This closes both the model repeating itself and the more likely real cause — a retry after a timeout where the first call actually succeeded. Check your logs for that; I'd bet at least one of your duplicates was a network retry, not the model.

**3. Human-in-the-loop above a threshold.**
Auto-approve under, say, $50; above that the tool returns "pending" and a support person clicks approve on a card that shows *order_id, amount, reason, customer message*. Refunds are irreversible and outward-facing — that's exactly the class that gets a confirmation gate.

**4. Validate server-side that the customer actually owns the order.**
The chat message is untrusted text. If someone writes "refund order #88213" and that isn't their order, the model will happily comply. Scope the refund tool to the authenticated session's orders, not to a service credential.

## Then close the loop

- Every bad refund you've seen becomes an **eval case** (input transcript → expected `amount_cents`, `order_id`), run in CI on any prompt or model change. Without this, your next prompt tweak is a coin flip.
- **Pin the model version.** A silent provider update is an unannounced deploy of your flakiest component.
- Log the model's proposed arguments vs. what the server accepted. That diff is your early-warning meter.

## Recap

Keep the prompt lines — they're cheap. But treat them as rung zero. The real fix is: model proposes, server disposes. Bound the amount against the real order in code, make duplicates impossible with a unique idempotency key, gate big refunds behind a human, and turn each incident into a CI eval. Do #1 and #2 first; they close both reported failures tonight.

If you want, point me at the refund tool handler and I'll write the argument validation and the idempotency constraint into it.