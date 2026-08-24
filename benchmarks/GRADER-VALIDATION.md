# Grader validation: what was measured and what it found

`focus.md` and the sample files are gitignored working material. This is the durable record.

**Status: not complete.** The verdicts below are a careful machine read, not a human one, and
the accuracy figure the exercise exists to produce is still outstanding.

---

## What was established

**Consistency, across three independent graders on 60 stratified verdicts** covering both arms
and all six runtimes:

| pair | agreement | Cohen's kappa |
|---|---:|---:|
| primary vs codex | 86% | +0.733 |
| primary vs agy | 88% | +0.767 |
| codex vs agy | 91% | +0.833 |

50 of 60 unanimous. **No detectable arm bias**: disagreement ran 11% on baseline against 15%
on with_skill, and the direction of the lean was 4-vs-1 toward the grader being *stricter* on
treatment responses, which would deflate deltas rather than inflate them. At those counts it
is noise, and the earlier claim that disagreement concentrated on baseline runs was an
artifact of a broken sample; see `validation/baseline-only-2026-08-24/`.

## What was not established

**Accuracy.** Consistency is not correctness, and this exercise produced a concrete
demonstration rather than an argument for that:

> **Item 12.** The assertion asks whether the response sweeps for other non-idempotent side
> effects reachable from a retry. The primary grader said FAIL, codex said FAIL, agy said
> UNCLEAR, and Claude said UNCLEAR. All four were wrong. The sweep is present, near the end:
> *"every other effect reachable from that queue, refunds, payouts, subscription creation,
> outbound webhooks, inventory decrements, has the same hazard until proven otherwise."*
>
> The response was 3,765 characters and every grader saw all of it. Each appears to have
> anchored on the opening disclaimer, "I can't run the class sweep against your code", and
> stopped. Four models, one shared blind spot, perfect agreement, wrong.

## Machine verdicts on the focused sample

18 items: the 10 the three graders split on, plus 8 they agreed on, shuffled as controls so
the reviewer cannot tell which is which. **11 PASS, 7 FAIL** after a full read of all 10,981
words. Two verdicts were corrected by checking evidence rather than by opinion:

| item | first pass | corrected | what settled it |
|---|---|---|---|
| 12 | UNCLEAR | **PASS** | reading to the end of the response |
| 7 | PASS | **FAIL** | the response writes its own Prisma schema with no `@@unique`, then calls `findUnique({where:{id, tenantId}})`. Prisma permits only unique fields there, so the tenant scoping does not compile. `findFirst` appears zero times |

## Three ways the graders failed, none caught by another opinion

**A shared blind spot** (item 12, above). Found by reading the whole response.

**A confidently wrong reason.** agy failed item 5 because the code was "cut off mid-comment".
It was not: the response closes its tag, its brace and its fence. agy was reading a truncation
introduced by the harness that sent it the item, and reported it as a property of the response,
with a quotation. Found by reading the original file.

**A right answer from a wrong premise.** codex failed item 7 because the scoping "is not valid
for the supplied Prisma `Order` schema". No schema was supplied: the scenario is greenfield
with `files: []`, and the prompt asks the model to write the schema itself. The conclusion was
right and the reason was not. Found by reading the scenario and the response's own schema.

Every one was caught by checking against something external. None by another grader.

## Harness defects found and fixed

| Defect | Effect | Device |
|---|---|---|
| `rpartition("_")` split `model_with_skill` into `model_with` / `skill` | 97 treatment cells silently excluded; the sample was 100% baseline while reporting success | `test_grader_validator_sees_every_arm`, plus a coverage assertion that fails when the draw misses an arm |
| An adjudication brief truncated responses at 4,000 characters | 4 of 10 adjudications judged on partial text; 2 of codex's 4 verdicts flipped once given the full text | a guard that refuses to grade when the response does not survive into the prompt intact |
| Machine verdicts written into the worksheet | would have produced an "accuracy" figure that was a fourth model agreeing with three others | `--report` refuses while any `SUGGESTED` marker remains |

## What is still needed

A human read of the 18. `focus.md` carries the machine verdicts with reasoning per line, so it
is a review rather than a cold start. Every number in this repository is produced by an
instrument that has been checked for bias and never for truth, and item 12 is what that costs.
