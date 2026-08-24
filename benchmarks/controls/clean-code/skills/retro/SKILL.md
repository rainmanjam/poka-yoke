---
name: retro
description: >-
  Something broke. Deciding what to change in the code so the class of problem is less likely,
  and writing it up so the next person understands the reasoning rather than just the outcome.
---

# Retro: Structural Lessons From an Incident

An incident is expensive information. Most of the value is lost because the write-up records
what happened and the fix records what changed, and neither records *why the code allowed it*.

The structural question is not "what went wrong" but "what about the shape of this code made
that failure available, and is that shape used elsewhere".

## Separate the timeline from the analysis

The timeline is what happened, in order, with times. It is a record, and it should be boring:
who noticed, when, what they did, what the system did back. Write it first and do not
interpret it while writing it.

The analysis is what you concluded. Keep it separate, because a timeline with interpretation
woven through it cannot be re-read later by someone who disagrees with the interpretation.

## Find the structural cause, not the last change

The last change before the incident is rarely the interesting one. Ask instead:

**What made this failure expressible?** A function that accepted an argument it could not
validate, a module that could observe state it had no business observing, a default that
silently applied.

**Why did the code look correct?** If the failing code passed review, understand what it
looked like to the reviewer. That perception is the thing to change, and it is usually a
naming or a structure problem rather than a knowledge problem.

**How far can this shape travel?** The same shape almost certainly exists elsewhere. Finding
the second and third instance is the difference between a fix and a lesson.

## The write-up

Aim it at someone six months from now who was not there.

- **Lead with the structural finding**, not the chronology. "A helper returned `None` for both 'absent' and 'failed', and three callers could not distinguish them" is the sentence worth remembering.
- **Say what was ruled out**, and why. A retro that lists only the cause reads as though it was obvious, which teaches the reader nothing about how to look.
- **Name the changes and their limits.** A fix that closes one path should say which paths it does not close.
- **Record disagreements.** If two people read the cause differently and one view won, the other view is evidence about how the code reads.

## What to change

**Prefer changes to shape over changes to process.** "Be careful with this function" degrades.
Splitting the function so the careless call is not available does not.

**Fix the class, not the case.** Patching the one call site that failed leaves the other twelve.
If the class is too large to fix at once, say so and list them.

**Reduce the distance between cause and symptom.** Much of an incident's cost is the time
between the wrong thing happening and anyone noticing. Structure that shortens that distance,
a narrower type, a failure that propagates rather than being absorbed, is worth as much as
preventing the failure.

**Change something.** A retro that concludes "we should be more careful" has concluded nothing.
If genuinely no code change is warranted, say what evidence would change that.

## What good output looks like

- **One structural finding, stated in a sentence**, before any detail.
- **The class sweep**, or an explicit statement that it was not done and why.
- **Changes tied to the finding.** A change that does not trace back to the structural cause is a separate piece of work and should be labelled as one.
- **What is still possible afterwards.** The residual risk is the part readers most need and most often do not get.

## What to avoid

**Blame framing.** Not primarily for kindness: naming a person ends the investigation, because
"they made a mistake" is a complete-sounding explanation that predicts nothing and prevents
nothing.

**Action items nobody owns.** An unowned item is a record of intent, and the next retro will
list it again.

**Over-fitting to the incident.** Building elaborate machinery to prevent one specific failure
adds complexity that must itself be maintained and understood. Ask whether the shape is
common enough to justify the structure.

**Treating monitoring as the fix.** Detection reduces the cost of a failure and does not reduce
its likelihood. Both are worth having; conflating them means the likelihood never gets
addressed.
