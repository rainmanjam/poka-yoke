# Designing the third arm

`baseline` is the bare prompt. `with_skill` prepends a preamble telling the model to read the
router at `skills/poka-yoke/SKILL.md`, follow its routing to a sub-skill, read that in full, and
follow it. So the treatment is not "extra tokens", it is **read a structured methodology document
and follow it**. A control has to match that mechanism or it is not a control.

Measured load per `with_skill` run: router 2,041 words, sub-skill 1,232 to 1,657 words, plus
whichever references the sub-skill points at (6,867 words available across five files).

## Two candidate controls; they answer different questions

### A. Generic methodology placebo

A skill of matched shape and length carrying real but unrelated quality guidance: SOLID,
naming, cohesion, readability, DRY. Same frontmatter, same router, same "read this then answer"
mechanism.

**Answers:** is the effect the *method*, or is it *any* structured document in context?

**If the delta collapses**, the honest headline becomes "structure in context helps and this
particular method is unproven", which is a materially weaker claim than the one currently
published. That is exactly why it is worth running.

### B. Defensive-programming arm

A skill of matched shape carrying the methodology this project explicitly argues against:
validate at every boundary, null-check defensively, fall back to safe defaults, wrap in
try/except and log.

**Answers:** does poka-yoke beat the thing it claims is the wrong answer?

`video/broll/scene-08-absorb.html` and the script assert that defensive code "does not stop it,
it absorbs it". Nothing in the benchmark tests that. This arm turns the project's central
rhetorical claim into a measured one, and a null or negative result here would be the most
important finding available.

## Recommendation

**Run A first.** It is the load-bearing one: without it, every published delta is equally
consistent with "any methodology document helps", and that is the objection a sceptic raises
before they ever get to defensive programming. B is more interesting to read and less
threatening to the headline, which is precisely the order not to do them in.

Cost is +50% runs each, grading unchanged. Both is +100%.

## What the placebo must not be

A straw man. If the control is obviously weak guidance, beating it proves nothing and the
comparison is worse than not running it. The placebo has to be advice a competent engineer
would defend: that is what makes the comparison mean something.

**Pre-register the placebo text before any grading**, and commit its hash the same way scenario
prompts are hashed, or the temptation to tune it after seeing the result is unmanaged.

## Open question for the run

Whether the placebo router should route to mode-specific sub-skills (matching poka-yoke's
routing exactly) or to a single document. Routing matches the mechanism more faithfully; a
single document is cheaper and simpler to pre-register. Matching the mechanism is probably worth
the extra authoring, since routing is part of what is being tested.
