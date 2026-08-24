---
name: audit
description: >-
  Reviewing existing code for unchecked inputs, unguarded dereferences, unhandled failure paths,
  swallowed exceptions, missing timeouts and absent limits: the places where an unexpected value
  becomes an unhandled failure.
---

# Audit: Finding the Unhandled Paths

The code in front of you works on the inputs it has seen. The audit question is what happens on
the inputs it has not: the null, the empty list, the oversized upload, the dependency that
times out, the row that predates the current schema.

Work outside in. Start where untrusted data enters and follow it, noting every point where the
code assumes something it has not checked.

## Trace every input to its use

For each entry point, list what arrives and follow it:

**Request data.** Path parameters, query strings, bodies, headers, cookies. Every one is
attacker-controlled. Check type, presence, range and size before use.

**Configuration and environment.** Absent variables, empty strings, values of the wrong type,
and files that failed to parse into an empty dict rather than an error.

**Database rows.** Nullable columns, rows written before a constraint existed, and joins that
return nothing.

**Other services.** Non-200 responses, valid HTTP with an error body, malformed JSON, empty
payloads, and calls that never return.

**Other modules.** A function that returns `None` on failure will hand you `None`, and the type
annotation may not say so.

## What to look for

**Unguarded dereference.** `data["key"]`, `obj.attr`, `items[0]` where nothing established that
the key, attribute or element exists. Note the exception it would raise and how far from the
cause it would surface.

**Unchecked arithmetic.** Division without a zero check. Multiplication of values that could be
`None`. Currency in floats. Indexes computed from input.

**Swallowed exceptions.** `except: pass`, `except Exception: pass`, and empty catch blocks. The
failure happened and nobody will ever know.

**Over-broad catches.** A single handler around a long block. You cannot tell which operation
failed, and the recovery cannot be specific to it.

**Missing timeouts.** Any network call, subprocess or lock acquisition without a bound. This is
the most common cause of a hang that looks like a deadlock.

**Absent limits.** Unbounded uploads, unpaginated queries, list parameters with no maximum,
retries with no cap, recursion driven by input.

**Fallbacks that hide.** A default that fires silently and often. Note whether anything would
reveal it firing.

**Success reported without verification.** `return True` after an operation whose failure was
never checked.

**Partial writes.** A sequence of mutations with no transaction, where failing halfway leaves
inconsistent state.

## Ranking by blast radius

Order by what the failure reaches, not by how easy it is to fix.

- **High:** unchecked input reaching a write, a delete, a payment or an auth decision; missing timeouts on calls in a request path; swallowed exceptions around anything that mutates state; partial writes without a transaction.
- **Medium:** unguarded dereferences on a read path; missing limits on inputs that are large but bounded in practice; broad catches around mixed operations.
- **Low:** unchecked values that can only produce a clean crash on a page nobody depends on; defensive checks missing where the type genuinely excludes the case.
- **Not a finding:** guarding against conditions the language already prevents, or re-validating a value three frames after it was validated at the boundary. Both add lines the reader must evaluate and dismiss.

## For each finding, say what should happen

An audit that only says "unchecked" leaves the hard part undone. The decision is the deliverable:

> `orders.py:88` reads `customer["email"]` with no check. Imported customers can lack one.
> Skip the send, log at warning with the customer id, and return `False` so the caller can
> record it as unsent rather than believing it went out.

Reject, substitute, skip or propagate, and say what it costs when it fires.

## What good output looks like

- **Name the value, the line and the arriving case.** "`amount` may be a string when the form posts an empty field" beats "validate inputs".
- **Say how far the failure travels.** An exception three frames from its cause is a different problem from one caught locally.
- **State the chosen behaviour**, not just that one is needed.
- **Cover the dependency being unavailable**, not only the value being wrong.
- **Order by what the failure reaches.**

## What to avoid

**Blanket advice.** "Add error handling" is not a finding. Which value, which line, which
behaviour.

**Wrapping everything.** A try block around each statement is unreadable and makes real
handling harder to see.

**Validation without a decision.** Adding a check that logs and then proceeds with the bad
value is worse than no check, because it implies coverage that does not exist.

**Ignoring the happy-path cost.** Every guard is a line to read. Guards that cannot fire are
noise, and noise is what makes real guards get skimmed.
