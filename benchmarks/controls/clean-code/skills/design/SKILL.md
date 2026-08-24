---
name: design
description: >-
  Designing a new interface, module, schema or type. Naming, cohesion, parameter shape,
  dependency direction and testability, decided before the thing has callers.
---

# Design: Getting the Shape Right First

An interface is a promise about how something will be used. Once it has callers, changing it
costs a migration, so the cheapest time to get the shape right is now, before anything depends
on it.

The disciplines are the same as everywhere else. What changes is that you are choosing rather
than repairing, so there is no existing consistency to respect and no cost to doing it well.

## Start from the call site

Write the code that will *use* the thing before writing the thing. A signature that looks
reasonable in isolation often reads terribly at the point of use:

```python
report = build(data, True, False, None, 30)
```

Nothing at that call site says what any argument means. The design problem is visible from the
caller and invisible from the definition, which is why the caller is where to start.

The same call with the shape fixed:

```python
report = build(rows, include_inactive=True, timeout=Seconds(30))
```

Keyword arguments at the boundary, defaults for what is usually right, and a name on every
value whose meaning is not obvious from its type.

## Parameters

**Order by how often they vary.** What the caller always supplies goes first; what rarely
changes gets a default and goes last.

**Make booleans keyword-only.** A positional `True` at a call site is unreadable, and two
adjacent booleans are worse: nothing stops a caller transposing them, and nothing detects it
afterwards. If a function takes more than one flag, consider whether it is really two
functions.

**Watch adjacent parameters of the same type.** `def transfer(src: str, dst: str)` accepts its
arguments in the wrong order without complaint. Either make them keyword-only or give the two
concepts distinct types.

**Prefer few parameters to many.** More than about four suggests the function is doing several
things, or that some of the parameters travel together and want to be one object.

## Return shapes

**Return the thing, not a status.** A function that computes rows should return rows. A count,
a boolean or `None` forces the caller to ask a second question.

**Be consistent about absence.** Pick one convention per codebase: an empty collection, an
optional, or an exception. Mixing them means every caller has to remember which this one does.

**Do not return unions the caller must unpack by guessing.** If the result is either a value or
an error, say so in the type rather than returning a value that is sometimes an error string.

## Modules and dependency direction

**Depend inward, toward the stable things.** Business rules should not import the web
framework, the ORM, or the mailer. When they do, the rules cannot be tested or reused without
all of it, and every framework upgrade becomes a rules change.

**Pass dependencies in.** A module that constructs its own database connection has decided for
every caller. One that receives it can be used in a test, a script and a job.

**Keep the public surface small.** Everything exported is something you have promised not to
break. Export the entry points; keep the helpers private.

## Naming what you are creating

New names are free right now and expensive later, so spend the time.

- **Say what it is, not what it does internally.** `PriceCalculator` tells a reader what it is for; `PriceUtils` tells them nothing.
- **Avoid the generic suffixes.** `Manager`, `Handler`, `Processor`, `Helper` and `Util` are placeholders for a noun you have not chosen. If nothing better comes, the concept is probably not clear yet.
- **Name the unit in the name.** `timeout` is ambiguous; `timeout_seconds` cannot be misread.
- **Match the domain's vocabulary.** If the business says "invoice", the type is `Invoice`, not `BillingRecord`.

## Schemas and data shapes

**Required and optional should be visible.** A schema where everything is optional communicates
nothing and pushes the checking into every consumer.

**Group fields that travel together.** Five address fields at the top level of an order should
be one `Address`. The grouping is a fact about the domain and will be true everywhere.

**Avoid flags that encode state.** Three booleans describing one lifecycle allow combinations
that cannot happen, and every reader has to work out which are real. One field naming the state
is clearer.

**Name the version if it will change.** A schema without a version is one that cannot be
migrated without guessing which shape you are holding.

## Testability as a design signal

The easiest way to tell whether a design is any good is to write one test against it before
implementing.

- If the test needs a database, a network, or a clock to check pure logic, the logic is tangled with its dependencies.
- If setting up the test takes more code than the assertion, construction is too complicated.
- If you cannot test one behaviour without exercising four, the unit has too many responsibilities.

None of that requires you to practise test-first development; the test is a probe you can throw
away after it has told you what it was going to tell you.

## What good output looks like

- **Show the signature.** The design conversation is about the shape, so put the shape on the page.
- **Show one call site.** Whether the design is good is most visible from the outside.
- **Say what you rejected.** "I considered a single options object and did not, because two of the four fields are required" is the part a reader learns from.
- **Do not design for cases that do not exist.** Extension points for hypothetical futures are the most common source of structure nobody needs.

## What to avoid

**Premature generalisation.** An interface with one implementation is a hop with no benefit
until the second one exists. Write the concrete thing; extract the interface when there is a
second case.

**Configuration for things that never vary.** Every option is a branch that must be understood,
tested and kept working.

**Designing the whole system before writing any of it.** The parts you learn from building the
first piece will change the design of the rest.
