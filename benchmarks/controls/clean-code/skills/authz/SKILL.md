---
name: authz
description: >-
  Permission and access-control code. Structure, clarity and testability of authorisation
  logic: where the decision lives, how it is named, and keeping it separable from the code
  that acts on it.
---

# Authz: Structuring Access Control

Authorisation code is where structural sloppiness costs most, because a permission check that
is hard to read is a permission check nobody re-reads. The discipline here is the ordinary one,
applied somewhere the consequences are unusual.

## Put the decision in one place

**Separate deciding from enforcing.** A function that answers "may this actor do this thing to
this resource" should not also perform the thing. Once separated, the decision can be tested
exhaustively, listed, audited, and reused by a second caller without dragging the action along.

**One vocabulary for actors, actions and resources.** If some code says `user`, some says
`account`, and some says `principal`, a reader cannot tell whether they are the same concept.
Pick the words and use them everywhere, including in the database columns.

**Avoid boolean soup.** `if (user.isAdmin || (user.isOwner && !resource.locked))` scattered
across twelve call sites is twelve places to update and twelve chances to differ. Name the
rule once: `canEditResource(user, resource)`.

**Make the decision total.** A function returning `true`, `false` or `undefined` will be used
as though `undefined` is one of the other two. Return a decision that covers every case, and
make the default deny rather than allow, because a missing branch should fail closed.

## Structure that makes the check hard to skip

**Take the actor as a parameter, never from ambient context.** A function reaching for a global
`currentUser` can be called from a background job that has none, and the failure will be a
`null` reference in an unrelated place rather than an authorisation error.

**Pass the actor down the call chain rather than re-fetching it.** Re-fetching invites two
layers to disagree about who the actor is.

**Keep the resource identity typed.** A function taking two adjacent strings for
`resourceId` and `ownerId` accepts them in either order. Distinct types make the transposition
a compile error rather than a security incident.

## Make it testable, then test the negative cases

The structural test of an authorisation design is whether you can write a table of
`(actor, action, resource) -> expected` cases and run it without a server.

If you cannot, the decision is tangled with transport, persistence or session handling, and the
first thing to fix is that tangle rather than any individual rule.

The cases that matter are the ones that should be denied. A test suite that only covers
permitted actions passes just as happily against a function that returns `true` unconditionally.

## What good output looks like

- **Name the decision function and its signature.** Where the decision lives is most of the design.
- **Show one call site**, because whether the check is easy to skip is visible from the caller.
- **List the rules as a table** when there is more than one actor kind. Prose describing a matrix is harder to check than the matrix.
- **Say what is deliberately permitted.** A review that lists only denials leaves the reader unsure whether the permitted set was considered.

## What to avoid

**Checks distributed across layers with no owner.** A rule enforced in the controller, the
service and the query, differently, is three rules.

**Comments as enforcement.** `// only admins should call this` is not a check.

**Roles as a substitute for a decision.** `if (role === "admin")` scattered around means adding
a role requires finding every site. Ask what the role *permits* and name that.

**Reviewing the policy instead of the code.** Whether marketing should see billing data is a
question for whoever owns that; whether the code expresses the intended answer legibly is
this review.
