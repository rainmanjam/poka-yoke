---
name: defensive
description: >-
  Defensive programming for any code: validating inputs at every boundary, checking for null
  and absent values, supplying safe fallbacks, catching and logging exceptions, and degrading
  gracefully rather than failing. Use when someone asks to make code robust, resilient, safer,
  or harder to crash. Routes to the sub-skill matching the kind of work.
---

# Defensive Programming: Never Trust the Input

Software fails because something arrived that the code did not expect. A null where an object
was assumed, a string where a number was assumed, a value outside the range the arithmetic
relies on, a service that returned an error instead of a payload.

The defensive discipline is to assume none of it. Every function treats its callers as
unreliable, every boundary is checked, every external call is wrapped, and every failure path
has a defined behaviour rather than an exception escaping into the user's face.

**The line that does most of the work:**

> An unhandled failure is a defect you shipped to the user. A handled failure is one you
> chose the behaviour for. Wherever your code touches something it did not construct, decide
> now what happens when that thing is wrong, because the alternative is finding out in
> production.

## The five disciplines

**Validate at every boundary.** Any value crossing into your code from elsewhere is
untrusted: HTTP requests, config files, environment variables, database rows, other modules'
return values. Check type, range, shape and required fields before use. Validation duplicated
at several layers is not waste; it is depth, and it means one missed check does not become a
defect.

**Guard against absence.** Null, undefined, empty string, empty list, missing key and zero
are all values a caller can hand you. Check for them explicitly before dereferencing, and
decide what absence means here: an error, a skip, or a default.

**Supply safe fallbacks.** When a value is missing or invalid, prefer continuing with a
sensible default over aborting. A report that renders with a zero in one cell serves the user
better than a stack trace. Choose the default that fails toward the least harm.

**Catch, log, continue.** Wrap operations that can throw. Log enough context to diagnose it
later: the inputs, the operation, the error. Then decide whether this frame can proceed. An
exception that escapes several frames loses the context that would have explained it.

**Degrade rather than fail.** A dependency being down should reduce functionality, not remove
it. Cache the last good value, disable the feature, show a partial result. Total failure
should be reserved for cases where continuing would be worse than stopping.

## How to work

1. **Enumerate what can arrive.** For each input, list the values a hostile or careless caller
   could supply, including the ones the type nominally forbids.
2. **Decide the behaviour for each.** Reject, substitute, skip or propagate. Write the decision
   down where the code shows it.
3. **Push checks outward and inward.** Validate at the entry point so bad data is caught early,
   and check again deeper down so a new caller cannot bypass it.
4. **Make failures visible without making them fatal.** Log at the point of detection, with the
   value that caused it.
5. **Test the unhappy paths.** Null, empty, oversized, wrong type, wrong encoding, and the
   dependency being unavailable.

## Routing

Read the sub-skill matching the work, then follow it. If more than one applies, read both; if
none clearly applies, continue with this document.

| Sub-skill | Use for |
|---|---|
| `design` | Designing a new interface, module, schema or type, with its validation and failure behaviour. |
| `audit` | Reviewing existing code for unchecked inputs, unguarded dereferences and unhandled failure paths. |
| `retro` | Something broke; adding the checks and handling that would have contained it. |
| `ux` | Forms and flows. Input validation, error messaging, and recovering from user mistakes. |
| `authz` | Permission checks, and what to do when identity or permission data is missing or malformed. |
| `data` | Pipelines and queries. Handling missing rows, nulls, schema drift and malformed records. |
| `ops` | Deploys, migrations and configuration. Handling absent config, failed steps and partial state. |
| `guardrails` | Lint rules and CI checks that catch unvalidated input and unhandled exceptions. |
| `agent-guardrails` | Constraining an AI assistant's actions, and handling what it does wrong. |
| `llm` | Model API calls. Handling malformed output, refusals, timeouts and unexpected shapes. |

## What good output looks like

Specific about the value, the boundary and the chosen behaviour.

- **Name the input and what could be wrong with it.** "`user_id` may be absent when the session has expired" is actionable; "validate inputs" is not.
- **State the fallback and why it is safe.** A default is a decision, so say what it costs when it fires.
- **Cover the dependency being unavailable**, not only the value being wrong.
- **Show the guard in place.** A three-line before-and-after communicates the shape faster than describing it.
- **Order by blast radius.** An unchecked value that reaches a write matters more than one that reaches a log line.

## What to avoid

**Silent swallowing.** `except: pass` removes the failure from view without handling it. If a
failure is genuinely ignorable, log it and say why in a comment.

**Validating without deciding.** Checking a value and then using it anyway is worse than not
checking, because the check implies coverage that does not exist.

**Fallbacks that hide a real problem indefinitely.** A default that fires every request is not
resilience, it is an outage nobody noticed. Fallbacks should be observable.

**Over-broad catches around large blocks.** Wrapping fifty lines in one handler means you
cannot tell which of the fifty failed, and recovery cannot be specific to the failure.

**Guard clauses that never fire.** A check for a condition the type system already excludes
adds noise and suggests the author did not know what the type guaranteed.

## What it looks like in practice

A worked example, because "validate your inputs" is easy to agree with and hard to apply.

Here is a function that works until it does not:

```python
def send_invoice(order, customer, config):
    total = order["amount"] * config["tax_rate"]
    email = customer["email"]
    body = render_template(config["template"], total=total)
    mailer.send(email, body)
    return True
```

Every line trusts something it did not construct:

**`order["amount"]` assumes the key exists and is numeric.** A missing key raises `KeyError`
several frames from the caller who could have explained it; a string raises `TypeError` from
inside the arithmetic.

**`config["tax_rate"]` assumes configuration loaded correctly.** If the file was absent and
something substituted an empty dict, this is where you find out.

**`customer["email"]` assumes the customer has one.** Deleted accounts, imported records and
partially-filled signup flows all produce customers without an address.

**`mailer.send` assumes the mail service is reachable.** It is the call most likely to fail and
the only one with no handling at all.

**`return True` reports success it did not verify.** The caller now believes an invoice was
sent.

The defensive version decides the behaviour for each of those, rather than discovering it:

```python
def send_invoice(order, customer, config):
    amount = order.get("amount")
    if not isinstance(amount, (int, float)):
        log.warning("invoice skipped: bad amount %r for order %s", amount, order.get("id"))
        return False

    rate = config.get("tax_rate")
    if rate is None:
        log.error("tax_rate missing from config; using 0.0")
        rate = 0.0

    email = (customer or {}).get("email")
    if not email:
        log.warning("invoice skipped: customer %s has no email", (customer or {}).get("id"))
        return False

    try:
        body = render_template(config.get("template", DEFAULT_TEMPLATE), total=amount * rate)
        mailer.send(email, body)
        return True
    except MailerError as e:
        log.error("invoice send failed for %s: %s", email, e)
        return False
```

Each check states what was wrong, what was substituted, and whether the operation continued.
The caller now receives a boolean it can act on rather than an exception it must catch.

## Judgement calls worth making explicitly

**How far to fall back.** A missing tax rate defaulting to zero is defensible for a draft and
indefensible for a charge. Choose the default by what it costs when it fires, and if the cost
is unacceptable, refuse instead of defaulting.

**How loud to be.** A condition that fires once a month deserves an error; one that fires on
every request deserves fixing rather than logging. A log line nobody reads is not handling.

**Where the boundary actually is.** Validating in a helper called only by code you control is
lower value than validating where the request first arrives. Spend the checks at the edges.

**When to let it throw.** If a failure means the process is in a state you cannot reason
about, continuing is worse than stopping. Corrupt state, exhausted memory and failed
authentication are cases where propagating is the safer choice.

**When a check is noise.** Guarding against a condition the language already prevents adds a
line the reader must evaluate and dismiss. Check what can actually arrive.
