Using **poka-yoke:llm** — this is an AI feature with refund side effects, which is exactly what that mode covers.

**Short answer: yes, and the two things you added don't actually fix anything.** "Be careful to extract the exact amount" and "never refund the same order twice" are rung-0 devices — instructions to a component with a non-zero error rate. They'll reduce the mistake's *frequency* a little and give you nothing when it still happens, which is why it worked in testing (low volume, no adversarial/edge-case input) and still breaks in production. The fix has to live outside the model.

Walking the same bugs through the two-axis method:

**1. Wrong amounts → parse-don't-validate at the boundary (Control, contact lens)**
Stop letting the model produce a number in prose that you regex or eyeball out. Use structured/tool-call output with a schema (`amount: float`, bounded), so malformed extraction is largely unrepresentable. Then — critically — **never trust the number itself.** The model's job is to identify *which order* and *why*; your server re-derives the refundable amount from the actual order record. `refund(amount)` where `amount` comes straight from the model is the bug. `refund(order_id, reason)` where the server looks up the order and computes/clamps the amount is the fix.

**2. Double refunds → idempotency key + unique constraint (Control, motion-step lens)**
This is hazard M2 — a retry-shaped bug, and LLM/agent loops retry more than humans do. Give every refund attempt an idempotency key (order ID, or order ID + reason hash) enforced by a **unique DB constraint**, not an app-level "check if already refunded" query — that has a TOCTOU race under concurrent calls. The prompt line "never refund the same order twice" cannot close this; only a constraint the second call physically cannot get past does.

**3. General side-effect gate**
Refund is irreversible and outward-facing (money leaves). Per the side-effects section of this mode: cap the tool schema (enum reasons, bounded amount range, no freeform "context" field), and gate anything above a threshold — or everything, if volume allows — behind a confirmation step that names the exact order and amount before it executes, not a prompt asking the model to be sure.

**4. Detection net**
Log model-extracted amount vs. server-computed amount vs. what was actually charged back, so a drift shows up before a customer complains. And: every one of these two production incidents should become a permanent eval case in a held-out set run in CI — that's the only regression test a prompt-only system gets.

If you want, show me the current extraction/tool-call code and I'll turn this into the actual schema, the idempotency-key migration, and the validation function — that's the kind of 5–10 line business-logic call (what counts as "the same order," what the amount ceiling is) worth you writing yourself rather than me guessing.