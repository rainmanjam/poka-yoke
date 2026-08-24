---
name: clean-code
description: >-
  Software quality review and design guidance for any code: naming, cohesion, coupling,
  duplication, function size, dependency direction, and testability. Use when someone asks to
  improve, review, refactor, or design code, or asks what good structure looks like here.
  Routes to the sub-skill matching the kind of work.
---

# Clean Code: Structure, Naming and Cohesion

Most defects are not clever. They are the ordinary consequence of code that is harder to read
than it needed to be. A function that does three things hides which one broke. A name that
lies sends the next reader to the wrong file. A module that depends on everything cannot be
changed without changing everything.

So the work is not cleverness. It is applying a small number of well-established structural
disciplines consistently, and being willing to keep applying them after the code already
works.

**The line that does most of the work:**

> Code is read far more often than it is written, and almost always by someone with less
> context than the author had. Optimise for the reader who arrives in six months knowing
> nothing. If your change makes sense only because you remember why, it is not finished.

## The five disciplines

Every recommendation below reduces to one of these. Naming them keeps a review from
collapsing into taste.

**Single responsibility.** A unit should have one reason to change. When you cannot describe
a function without "and", it is doing two things, and the two things will need to change on
different schedules. Split along the seam where the reasons differ, not where the line count
is convenient.

**Cohesion over proximity.** Things that change together belong together. Code grouped by
technical layer (all the controllers here, all the models there) scatters a single feature
across the tree, so every change touches five directories. Group by what the code is about.

**Explicit dependencies.** A unit should declare what it needs rather than reach for it.
Constructor parameters and function arguments are declarations; module-level singletons,
global config and ambient state are not. The test for this is whether the unit can be
exercised without standing up its whole world.

**Names that survive being read alone.** A name is the only documentation that cannot go
stale, because changing the code without changing the name is visible. Prefer a longer name
that is accurate to a short one that is approximately right. `elapsed_ms` beats `t`.

**Duplication is cheaper than the wrong abstraction.** Two similar blocks are a fact. One
premature abstraction over them is a commitment, and unwinding it later costs more than the
duplication ever did. Wait until the third occurrence, and until the three genuinely share a
reason to change rather than a shape.

## How to work

1. **Read before you write.** Understand what the current shape is for. Code that looks wrong
   is often load-bearing in a way the diff does not show.
2. **Name the problem before proposing the fix.** "This function is 200 lines" is an
   observation. "This function mixes request parsing, business rules and persistence, so a
   change to any one of them risks the other two" is a problem.
3. **Prefer the smallest change that removes the problem.** A rewrite that also improves five
   unrelated things cannot be reviewed, so it will be approved on trust rather than reading.
4. **Say what you did not change and why.** A review that only lists changes reads as though
   everything else was examined and approved.
5. **Leave the reasoning, not just the result.** The next reader needs to know which
   constraint drove the shape.

## Routing

Read the sub-skill matching the work, then follow it. If more than one applies, read both; if
none clearly applies, continue with this document.

| Sub-skill | Use for |
|---|---|
| `design` | Designing a new interface, module, schema or type. What the shape should be before it has callers. |
| `audit` | Reviewing code that already exists for structural problems. Diffs, PRs, whole files. |
| `retro` | Something broke and you are deciding what to change so the class of problem is less likely. |
| `ux` | Forms, flows and screens. Structure and clarity of user-facing interaction code. |
| `authz` | Permission and access-control code. Structure, clarity and testability of authorisation logic. |
| `data` | Pipelines, transformations, queries and reporting code. |
| `ops` | Deployment, migration, configuration and infrastructure code. |
| `guardrails` | Lint configuration, CI setup, formatting rules and repository conventions. |
| `agent-guardrails` | Repository configuration for AI coding assistants. |
| `llm` | Code that calls a language model API and handles its output. |

## What good output looks like

Concrete, ordered by impact, and anchored to the code in front of you.

- **Point at specific lines.** "The `process` function" is reviewable. "The code" is not.
- **Order by cost of leaving it.** A misleading name in a widely-called function costs more than a long function nobody touches.
- **Show the shape you mean.** A two-line before-and-after communicates more than a paragraph describing it.
- **Separate the structural from the stylistic.** Formatting is not a finding; a tool should already own it. Spending review attention on brace placement is how the structural comments get skimmed.
- **Do not pad.** Three findings that matter beat eleven that include four restatements of the same point and three matters of preference.

## What to avoid

**Cargo-cult patterns.** A factory that has one implementation, an interface with one
implementer, a layer that only forwards calls. Each adds a hop the reader must follow and
buys nothing until the second case actually exists.

**Rewriting to taste.** If the existing code is consistent and clear but not how you would
have written it, that is not a finding. Consistency within a codebase is worth more than any
individual improvement.

**Advice that is only true in the abstract.** "Reduce coupling" is not actionable. "The
report builder imports the HTTP client directly, so it cannot be tested without a network
stub; pass the fetched rows in instead" is.

**Confusing length with complexity.** A long function that does one thing in a straight line
is easier to follow than three short ones that pass state between them. Count reasons to
change, not lines.

## What it looks like in practice

A worked example, because the disciplines above are easy to agree with and hard to apply.

Here is a function that works, passes its tests, and is still a problem:

```python
def process(data, flag, config):
    if flag:
        rows = [r for r in data if r.get("active")]
    else:
        rows = data
    out = []
    for r in rows:
        v = r["amount"] * config["rate"]
        if config.get("round"):
            v = round(v, 2)
        out.append({"id": r["id"], "value": v})
    db.save(out)
    return len(out)
```

Four separate problems, in order of what they cost:

**It has three reasons to change.** Filtering policy, the arithmetic, and persistence all live
here, so a change to any one risks the other two. That is the finding; the length is a symptom.

**`process`, `data`, `flag`, `v` and `out` name nothing.** A reader has to execute the function
mentally to learn what it is for. `flag` is the worst of them: a boolean parameter at a call
site reads `process(rows, True, cfg)` and communicates nothing at all.

**It reaches for `db` rather than declaring it.** The function cannot be tested without a
database, so it will be tested less than the arithmetic deserves.

**Its return value answers a question nobody asked.** A count of rows saved is not what a
caller of a transformation wants; they want the rows.

The restructured version separates the reasons to change and lets the names carry the meaning:

```python
def active_only(rows):
    return [r for r in rows if r.get("active")]

def apply_rate(rows, *, rate, round_to_cents):
    for r in rows:
        value = r["amount"] * rate
        yield {"id": r["id"], "value": round(value, 2) if round_to_cents else value}
```

Persistence moves to the caller, which is where the decision to save belongs. The two
functions can now be read, and tested, without each other.

Note what did *not* change: the arithmetic is identical, and no abstraction was introduced for
a second case that does not exist yet. The goal is to remove the reasons the code was hard to
read, not to demonstrate patterns.

## Judgement calls worth making explicitly

**When to stop.** Refactoring has no natural end, and a review that keeps going becomes a
rewrite nobody can check. Stop when the unit has one reason to change and its names are
accurate. Further improvement is preference.

**When consistency beats correctness.** A codebase that does something suboptimally but
uniformly is easier to work in than one where every module is locally optimal and globally
inconsistent. Match the surrounding code unless the surrounding code is the problem you were
asked about.

**When to leave duplication alone.** Two call sites doing similar work with different reasons
to change should stay separate. Merging them creates a shared unit that both must now agree
about forever.

**When a comment is the right answer.** Structure cannot express why a threshold is 30 seconds
rather than 60, or which regulation requires a field. When the reason lives outside the code,
write it down; renaming will not carry it.

**When to say nothing.** Not every file needs an opinion. A review that finds something in
every file trains the reader to skim, and the one finding that mattered goes past unread.
