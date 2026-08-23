I've read through the `poka-yoke` router, which correctly identified this as a **Design** task (since we are creating the types before the code exists). I also reviewed the hazard catalog and TypeScript-specific guidelines to ensure we apply the highest possible "Control" rungs for mistake-proofing.

I've generated a detailed technical plan in the artifact for your review. Here's a brief summary of the design choices made to protect against common hazards:

1. **Discriminated Union over Bag-of-Optionals (Hazard C8)**: Instead of a single `Subscription` struct with all fields made optional, we define four distinct interfaces (`Trialing`, `Active`, `PastDue`, `Canceled`) tied together by a `status` discriminator. This makes invalid states (like an active subscription with a cancel reason) **unrepresentable**.
2. **Branded Types (Hazard C1)**: For IDs (`SubscriptionId`, `UserId`, `PlanId`), we use branded types so that you cannot accidentally pass a `UserId` into a function that expects a `SubscriptionId`.
3. **Exhaustive Matching (Hazard F1)**: I've included an `assertNever` helper. If you add a `paused` state next year, the TypeScript compiler will break the build at every `switch` statement that forgot to handle it.

Please review the proposed plan in the artifact, and let me know if those types align with your data model or if you'd like to adjust anything (such as using a specific DateTime library for the dates). Once you approve, we can proceed!