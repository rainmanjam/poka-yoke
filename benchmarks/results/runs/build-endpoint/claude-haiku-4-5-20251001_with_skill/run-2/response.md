The background design review confirms the approach. Here are the **key mistake-proofing moves** embedded in the code:

| Hazard | Device | Rung |
|--------|--------|------|
| **Adjacent IDs swapped** (orderId ↔ accountId) | Distinct parameter names + typed validation | Control |
| **Duplicate charges** (retry or UI double-click) | Idempotency key + unique constraint | Control |
| **Money as float** (0.1 + 0.2 ≠ 0.3) | Integer cents only (no float arithmetic) | Control |
| **Invalid states** (failed + succeeded) | Enum status with transaction boundary | Control |
| **Check-then-act race** (concurrent refunds exceed order) | Transaction guarantees atomicity | Control |
| **Tenant leak** (refunding another org's order) | Scoped query `where: {tenantId}` | Control |
| **Non-exhaustive branching** (adding status forgets handler) | TypeScript enum exhaustiveness | Warning |
| **Stripe + DB split-brain** (call succeeds, DB fails) | Transaction rolls back both or commits both | Control |
| **Over-refund** (refund > order total) | Validation gate before Stripe call | Warning |
| **Partial failure invisibility** | Status tracking (pending→succeeded/failed) | Detection |

The remaining hazards are intentionally explicit: Stripe key validation should happen at server startup (add to your config loader); replay logic for duplicate detection uses 60s window (adjust per your SLA); and the `charge_id` reference assumes order has Stripe metadata (add that to your Order schema based on payment flow).