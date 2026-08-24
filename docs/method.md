# The Method

A short guide for humans. The plugin's skills teach this to a model; this page is for you.

**Where the plugin's own two halves sit on the ladder below.** The hazard detector is a
device: it runs in pre-commit and CI, is never in a model's context, and behaves the same on
hour six of a session as on minute one. The skills are instructions. They are better
instructions than a line in a rules file, because they carry reasoning rather than a
prohibition, but they are still competing for attention with everything else in the window and
should be expected to fade as it fills. That is this method applied to itself, and it is why
the honest advice is to invoke a mode early and fresh, and to install the device.

## Where it comes from

Shigeo Shingo (1909–1990) was a Japanese industrial engineer who taught at Toyota as an
outside consultant from 1955, and who formalised poka-yoke and gave it its name. The Toyota
Production System itself was developed inside Toyota by Taiichi Ohno and Eiji Toyoda; Shingo's
own contributions were SMED and the quality method below, and his books, translated into
English years before Ohno's own account, helped carry the method outside Japan.

His contribution to quality was a reframing that sounds obvious and almost never gets
applied:

> A **mistake** is a human action. A **defect** is a mistake that reached the customer.
> Mistakes are inevitable. Defects are not.

Everyone accepts the first half. Almost no organization acts on the second, because the
instinctive response to a mistake is to ask people to be more careful, more training, more
documentation, another reviewer, a checklist. Shingo's answer was that inspecting for defects
never removes their cause. Carefulness is not a durable property of a system.

What works is a *device*: a jig that only accepts a part one way round, a counter that will not
release until all six screws are fitted, a sensor that confirms step 3 happened before step 4.
The Japanese term is **poka-yoke** (ポカヨケ), "mistake-proofing". Shingo first called it
*baka-yoke*, "fool-proofing", and tells of renaming it after a worker was upset by what the
name implied: the point was never that people are fools.

## The one test

> If your proposed fix relies on someone remembering something, it is not a poka-yoke.

Documentation, comments, wiki pages, review checklists, training sessions, Slack reminders,
and lines in an agent instruction file are all rung zero on the ladder below. They are worth
writing. They are not devices, and counting them as fixes is how the same incident happens
twice.

## Axis 1: what happens when the mistake occurs

| Rung | What it does | Software |
|---|---|---|
| **1** | **Control**: impossible | types · DB constraints · required arguments · deny rules · branch protection |
| **2** | **Warning**: announced as it happens | lint errors · CI gates · assertions · confirmations that name the object |
| **3** | **Detection**: found afterward | tests · monitoring · reconciliation |
| **0** | *not a poka-yoke* | docs · comments · training |

Always reach for the highest rung you can afford, and when you settle for a lower one, say
out loud *why*. "Runtime assertion, because Control would need a newtype touching 40 call
sites" is a decision someone can evaluate. "Added validation" is not.

## Axis 2: how the device notices

Shingo's three detection methods, which become your inspection lenses. Run all three over any
interface.

**Contact, can the wrong thing fit?**
On the factory floor, a part that won't seat unless correctly shaped. In code, the type is the
shape. Two adjacent `string` parameters can be swapped silently; two distinct types cannot.

**Fixed-value, can an incomplete or wrong-sized set pass?**
A counter confirming all six screws. In code: exhaustive matching, required fields, row-count
guards on bulk writes, config validated as a whole at startup.

**Motion-step, can the steps happen in the wrong order?**
A sensor confirming step 3 before step 4. In code: typestate, builders, state machines,
idempotency keys, scope-bound resources.

## Axis 3: where to put the device

1. **Source inspection**: check the *conditions* that produce the error, before the operation
   proceeds. Designed in where you can, enforced at runtime where you cannot. Best.
2. **Self-check**: the work checks itself. Runtime. Fail fast.
3. **Successive check**: the next station checks. Review, CI.

A CI gate that catches a bad migration is good. A schema that makes it unwritable is better,
and costs less forever.

## How to write a finding

Four fields, always. An unclassified finding is an opinion.

- **Mistake**: the wrong action, stated as an action. *"Call `transfer(dst, src)` reversed."*
- **Consequence**: what happens, and whether it is **silent**. Silence is the aggravator.
- **Current rung**: Control / Warning / Detection / None.
- **Device + rung**: the specific change, and where it lands.

And write about the code's affordances, never about the person. Not as a courtesy: "the
developer should have been more careful" has no implementation, so it cannot be a fix.

## Where the strongest devices go

Mistake-proofing has a cost, and past a point it stops paying. Five wrapper types for one
function, a builder for a two-field struct, a confirmation dialog on a reversible action. These add friction without preventing anything, and they train people to route around gates.

Aim the strong devices at high **blast radius** and low **reversibility**: money, auth,
deletion, migrations, publishing, secrets. Leave low-stakes code readable and low-stakes
actions fast. [The counter-argument to the maximalist version](https://www.seangoedecke.com/invalid-states/)
is worth reading.

## Source material and further reading

- [`references/hazard-catalog.md`](../plugins/poka-yoke/references/hazard-catalog.md), ~30 recurring hazard shapes, organized by lens, each with its device
- [`references/ux-patterns.md`](../plugins/poka-yoke/references/ux-patterns.md), interface devices sized by consequence
- Language references for
  [TypeScript](../plugins/poka-yoke/references/lang-typescript.md),
  [Python](../plugins/poka-yoke/references/lang-python.md), and
  [Rust and Go](../plugins/poka-yoke/references/lang-rust-go.md)
- Shigeo Shingo, *Zero Quality Control: Source Inspection and the Poka-Yoke System* (1986)
- Don Norman, *The Design of Everyday Things*, forcing functions
