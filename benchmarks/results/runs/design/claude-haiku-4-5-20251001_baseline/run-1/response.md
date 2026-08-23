Use **discriminated unions** — each subscription state gets its own type with a `status` field that narrows the rest of the shape:

```typescript
type Subscription = 
  | { status: 'trialing'; trialEndDate: Date }
  | { status: 'active'; renewalDate: Date }
  | { status: 'past_due'; retryCount: number; gracePeriodEnd: Date }
  | { status: 'canceled'; cancelReason: string; wasVoluntary: boolean }
```

This gives you **exhaustiveness checking** — TypeScript won't let you forget a case in a switch, and only lets you access fields that actually exist on that variant.

If you're validating with Zod, the pattern mirrors perfectly:

```typescript
const subscriptionSchema = z.discriminatedUnion('status', [
  z.object({
    status: z.literal('trialing'),
    trialEndDate: z.date(),
  }),
  z.object({
    status: z.literal('active'),
    renewalDate: z.date(),
  }),
  z.object({
    status: z.literal('past_due'),
    retryCount: z.number().int().min(0),
    gracePeriodEnd: z.date(),
  }),
  z.object({
    status: z.literal('canceled'),
    cancelReason: z.string(),
    wasVoluntary: z.boolean(),
  }),
])

type Subscription = z.infer<typeof subscriptionSchema>
```

**Why this works:** The status field acts as a discriminator, so TypeScript can narrow the type automatically in conditionals and switches. No overlapping optional fields, no "is this field valid in this state?" questions. The schema and type stay in sync naturally.