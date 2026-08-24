# private/

Local working material. **Everything in this directory is gitignored except this file.**

The ignore is on the directory contents (`private/*`), not on a list of filenames. That
matters: a new file dropped in here is private *by default*. A per-file ignore list is
something someone has to remember to extend, and the failure mode is publishing something
that was never meant to be public — which is the sort of thing this repository exists to
argue against.

This README is the exception, committed via `!private/README.md`, so the convention is
visible to anyone who clones the repo. Otherwise the directory is invisible and the next
person puts their working files in `docs/` again.

## What belongs here

- **`outreach.md`** — candidate venues for sharing the project, with submission routes and a
  hand-edited status column. It is a distribution plan, not documentation; a public list of
  places you intend to post reads very differently from a page explaining the method.
- **`copy-review.md`** — the raw output of `scripts/review_copy.py`: three models' criticism
  of every published document. Useful while working through it, odd to publish. Some of it
  was wrong, which is the point of adjudicating rather than applying.
- Draft posts, launch notes, pricing thinking, anything half-formed.

## What does not

Anything a reader needs in order to use or trust the project. If a document explains how the
thing works, why a decision was made, or what was measured, it belongs in `docs/` and in the
open — including the unflattering parts. `benchmarks/results/benchmark.md` reports exactly how many
stored runs are tied to the current prompts, and the README publishes the nine cells that came
out negative alongside the ~18 that chance alone would produce; those stay public precisely
because they are inconvenient.

## Regenerating

```bash
python3 scripts/find_outreach.py --reuse      # re-adjudicate the last search, 1 API call
python3 scripts/review_copy.py --dry-run      # what a full review would cost
```
