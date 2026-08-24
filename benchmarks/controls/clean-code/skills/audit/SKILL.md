---
name: audit
description: >-
  Reviewing code that already exists for structural problems: responsibilities that have drifted
  together, names that no longer describe what they name, dependencies pointing the wrong way,
  and duplication that has hardened into divergence.
---

# Audit: Reading Code That Already Works

Everything you are looking at ships and passes its tests. That is the constraint. You are not
hunting for bugs; you are finding the places where the structure will make the *next* change
expensive or risky, and saying which ones are worth paying to fix now.

That framing matters, because a review that lists everything imperfect is indistinguishable
from a review that found nothing important.

## Read in this order

**1. The public surface.** Exported functions, classes and endpoints. This is what other code
depends on, so problems here have the largest blast radius and the highest migration cost.

**2. The names.** Read them without reading the bodies. Any name that turns out to be wrong
once you read the implementation is a finding, because every future reader will make the same
mistake you just did.

**3. The imports.** They show the dependency direction at a glance. Business logic importing a
web framework, an ORM or a mail client is the single most reliable structural smell.

**4. The longest functions.** Not because length is the problem, but because that is where
several responsibilities usually ended up together.

**5. The tests.** Tests are a readout of the design. Heavy mocking means tangled dependencies.
Long setup means complicated construction. Absent tests for the core logic usually means the
core logic is hard to reach.

## What to look for

**Responsibilities that drifted together.** Describe the unit in one sentence. If you need
"and", note where the seam is: which parts change for different reasons, and on whose schedule.

**Names that have gone stale.** A function called `validate_user` that also creates a session.
A `TempFile` class that outlives the request. A `config` parameter that is actually a feature
flag. The code changed, the name did not, and the name is what the next reader trusts.

**Dependency direction.** Which module could not be tested, reused or moved without dragging
something heavy behind it? That is coupling with a cost you can name.

**Duplication that has diverged.** Two copies that started identical and have drifted are worse
than either one alone, because a fix applied to one leaves the other wrong. Note which is
correct.

**Ambient state.** Module-level singletons, globals, and implicit context. Each makes a unit's
behaviour depend on something not visible at its call site.

**Boolean parameters at call sites.** `render(rows, True, False)` cannot be read. Note it where
the call sites are numerous enough for the confusion to be real.

**Comments explaining what the code does.** Usually a sign the code does not say it. The
comment is not the finding; what forced it is.

## Ranking, which is most of the value

An unordered list of twenty observations moves nothing. Rank by expected cost of leaving it,
which is roughly *how often this code changes* multiplied by *how badly the structure hurts
when it does*.

- **High:** misleading names on widely-called functions; business logic that cannot be tested without infrastructure; diverged duplication where one copy is wrong.
- **Medium:** long multi-responsibility functions in code that changes regularly; ambient state; unclear module boundaries.
- **Low:** long functions in stable code nobody touches; naming that is imperfect but unambiguous; local inconsistency in a file that is otherwise clear.
- **Not a finding:** formatting, brace style, import order, and anything a tool should own. Raising these spends the reader's attention and teaches them to skim the rest.

## Say what you did not flag

A review that lists only problems reads as though everything unmentioned was examined and
approved. Name what you looked at and considered acceptable, and why:

> The `reports/` package has three near-identical builders. I left them: they render for
> different audiences and have changed independently twice, so the duplication is carrying real
> variation rather than hiding it.

That sentence is worth more than three more findings, because it tells the reader what your
threshold was.

## What good output looks like

- **Anchored to lines.** `orders.py:142, apply_discount` is reviewable; "the discount logic" is not.
- **Problem before fix.** State what the structure costs, then what you would do.
- **Ordered by cost**, with the ordering visible, so the reader can stop partway and still have covered the important ones.
- **Sized honestly.** If three findings matter, give three. Padding to a round number buries them.
- **With the shape shown.** A short before-and-after communicates faster than a paragraph.

## What to avoid

**Rewriting to taste.** Code that is consistent and clear but not your style is not a finding.
Local consistency beats individual improvement.

**Findings that are true everywhere.** "Consider adding tests" and "reduce coupling" apply to
every codebase and therefore inform nothing about this one.

**Reviewing the domain instead of the code.** Whether the discount rules are correct is a
question for whoever owns them; whether they are legible and changeable is yours.

**Proposing a rewrite.** A large restructuring cannot be reviewed, so it will be merged on
trust. Propose the smallest change that removes the problem you named.

**Counting lines as complexity.** A hundred-line function doing one thing in sequence is easier
to follow than five short ones threading state between them.
