---
name: ux
description: >-
  Forms, flows and screens. Structure, naming and clarity of user-facing interaction code:
  component boundaries, state ownership, and keeping presentation separable from the rules
  behind it.
---

# UX: Structuring Interaction Code

Interface code accumulates faster than any other kind, because every requirement arrives as
"and also, when the user does X". Without structure a screen becomes one component holding
fetching, validation, formatting, submission and error display, and every change risks all of
them.

The discipline is ordinary: single responsibility, explicit state ownership, and names that
survive being read alone. What is different is that the pressure to skip it is higher, because
interface code is visible and the deadline is usually visual.

## Decide where state lives, once

Most interface bugs are state-ownership bugs wearing other clothes.

**One owner per piece of state.** If two components can both change a value, they will
disagree, and the disagreement will be intermittent. Lift the state to the nearest common
parent and pass it down, or move it out of the tree entirely.

**Derive rather than duplicate.** A `total` stored alongside the `items` it sums is two facts
that must agree. Compute it. If computing it is expensive, memoise the computation rather than
storing a second copy.

**Keep server state and form state distinct.** What the server last said and what the user has
typed are different things with different lifetimes. Conflating them is why "the form reset
itself" bugs are so hard to reproduce.

**Name state for what it is, not what it shows.** `isSubmitting` is a fact. `showSpinner` is a
consequence, and it will eventually need to be true for a second reason.

## Split components along seams that will move

**By responsibility, not by size.** A 400-line component that renders one coherent thing is
easier to work with than four components passing state between them.

**Separate what fetches from what displays.** A component that both loads and renders cannot be
previewed, tested, or reused with different data. Take data as props; let a parent decide where
it came from.

**Keep the rules out of the markup.** Whether a discount applies is a business question with a
right answer that does not depend on React. It should be a function you can test without
rendering.

**Push formatting to the edge.** Currency, dates and pluralisation are presentation. Keep the
underlying values unformatted until the moment they are shown, or you will parse your own
output later.

## Handle the states that are not "success"

Every screen that loads has at least four states, and most code writes one.

- **Loading**, including a second load over existing content, which is a different visual case
- **Empty**, which is not an error and should not look like one
- **Error**, with something the user can act on
- **Partial**, where some of the data arrived

If those live as branches inside one render, the component is doing five things. A small
discriminated union describing the state, matched once, keeps them separable and makes it
obvious when one is missing.

## What good output looks like

- **Show the component boundary and the prop types.** Most of the design is visible from the signature.
- **Say where each piece of state lives and why.** Ownership is the decision worth recording.
- **Cover the non-success states explicitly**, or say which are out of scope.
- **Point at specific components.** "The table" is not reviewable.

## What to avoid

**Prop drilling as a default.** Passing a value through four components that do not use it
couples all four. Either lift it out of the tree or restructure so the intermediate layers do
not exist.

**Premature component extraction.** Splitting a component that has one caller, to "keep files
small", adds a hop with no benefit. Wait for the second use.

**Effects that synchronise state.** An effect that copies one piece of state into another is
almost always a derivation that should have been computed.

**Styling decisions in a structural review.** Spacing and colour are real work and a different
conversation. Mixing them in means the structural comments get skimmed.
