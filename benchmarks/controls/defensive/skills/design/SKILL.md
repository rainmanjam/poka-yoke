---
name: design
description: >-
  Designing a new interface, module, schema or type together with its validation and failure
  behaviour: what each input accepts, what happens when it does not, and what the caller gets
  back when something goes wrong.
---

# Design: Decide the Failure Behaviour Now

A new interface is a chance to decide what happens when things go wrong *before* anything
depends on the answer. Retrofitting validation onto an interface that has callers means
choosing between breaking them and leaving the gap open.

So design the failure paths at the same time as the happy path. For every parameter, decide
what it accepts and what it does with everything else. For every operation that can fail,
decide what the caller receives.

## Specify the accepted domain of every parameter

A type is a start, not a specification. `amount: float` still permits negatives, infinity, NaN
and values with more precision than money has. Write down what is actually allowed:

```python
def charge(amount, currency, customer_id):
    """
    amount:      positive, at most 2 decimal places, below the 10_000 per-txn ceiling
    currency:    3-letter ISO code, one of the supported set
    customer_id: non-empty, exists, account not closed
    """
```

Then enforce it at the top of the function, because a docstring is not a check:

```python
    if not isinstance(amount, (int, float)) or amount <= 0:
        raise ValueError(f"amount must be positive, got {amount!r}")
    if round(amount, 2) != amount:
        raise ValueError(f"amount has sub-cent precision: {amount!r}")
    if currency not in SUPPORTED_CURRENCIES:
        raise ValueError(f"unsupported currency {currency!r}")
```

Three checks, each naming the value that failed. A caller reading the error knows what to fix
without opening the source.

## Decide the failure contract before implementing

For each way the operation can fail, choose one and be consistent:

**Raise.** The caller cannot sensibly continue and should not have to check. Right for
programmer error and for corrupt state.

**Return an outcome.** The failure is expected and the caller has a decision to make. Right for
"not found", "already exists", "insufficient funds".

**Return a default.** The value is optional and a sensible substitute exists. Right for display
paths and configuration, wrong for anything that moves money or deletes data.

Mixing all three inside one module means every caller has to remember which convention this
function follows, so the convention itself becomes a source of mistakes.

## Validate at the boundary, and again at depth

The entry point should reject bad input early, with a message aimed at whoever sent it. Inner
functions should check again, because a future caller may reach them by another path.

This duplication is deliberate. A single check is a single point of failure, and the inner
check is what protects you when someone adds a second entry point next year and forgets.

Keep the two different in emphasis: the outer check produces a user-facing error, the inner
check produces a programmer-facing one.

## Schemas and stored shapes

**Make required fields non-nullable and say so.** A column that permits null will eventually
contain null, and every reader must handle it.

**Constrain at the storage layer too.** Check constraints, foreign keys and unique indexes hold
when application code is bypassed by a migration, a script or a console session.

**Decide what a missing optional means.** Absent and empty are different, and if the difference
matters, the schema should distinguish them rather than leaving each consumer to guess.

**Plan for the malformed row.** Data that predates the current validation exists in every
system with history. Decide whether readers skip it, repair it, or fail on it.

## Timeouts, limits and resource ceilings

Anything that talks to something else needs a bound, decided at design time:

- **Timeout on every network call.** A call without one waits forever, and the failure surfaces as a hang rather than an error.
- **Size ceiling on every input you accept.** Uploads, request bodies, list parameters and pagination limits all need a maximum, or a caller can exhaust memory.
- **Retry policy, with a cap.** Decide how many, how spaced, and which errors are worth retrying. Retrying a validation failure just fails more slowly.
- **A ceiling on anything recursive or iterative** driven by input, so a malformed structure cannot loop indefinitely.

Name the unit in the parameter: `timeout_seconds`, `max_rows`, `retry_limit`.

## What the caller receives when it fails

An error is an interface too, and it deserves the same care as the success path.

- **Say what was wrong, specifically.** "Invalid request" tells the caller nothing; "currency 'XYZ' is not supported" tells them exactly what to change.
- **Include the offending value**, truncated if it might be large, and never if it might be a secret.
- **Distinguish caller error from system failure.** The first is theirs to fix, the second is yours, and conflating them wastes everyone's time.
- **Keep the error stable.** Callers will parse it, whatever you intended.

## What good output looks like

- **Show the signature with its accepted domain**, not just its types.
- **Show the guards.** The checks are the design, so put them on the page.
- **State the failure contract explicitly**: what raises, what returns an outcome, what defaults.
- **Cover the dependency being unavailable**, not only the inputs being wrong.

## What to avoid

**Types treated as validation.** `amount: float` does not exclude negative, infinite or
sub-cent values. The annotation documents intent; the check enforces it.

**Errors that lose the cause.** Catching and re-raising a generic exception discards the
information the caller needed.

**Validation that cannot be reached.** A check after the value has already been used is
decoration.

**Unbounded anything.** No timeout, no size limit, no retry cap. Each is a defect waiting for
an unusual day.
