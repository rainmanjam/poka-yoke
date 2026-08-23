`★ Insight ─────────────────────────────────────`
The core device here is **enumerate, don't generate**: `team` is typed `Literal["billing","technical","account"]`, not `str`. Combined with Anthropic's structured-output mode (`output_config` / `client.messages.parse`), the model is constrained to pick from a fixed set — it can't invent a fourth category the way it could with free-text classification, and Pydantic's `extra="forbid"` rejects anything smuggled in alongside it.

At a few-thousand-emails/day volume, `claude-haiku-4-5-20251001` (pinned, not the floating alias) is the right tier — it's a closed-set classification task, not a reasoning task, so paying for Opus/Sonnet buys nothing. Pinning the dated ID matters *because* volume is high: a silent model swap under a floating alias would change routing behavior for thousands of tickets/day with no changelog.
`─────────────────────────────────────────────────`

```python
"""
Support-email router — classifies inbound support emails into exactly one
team (billing/technical/account) using the Anthropic SDK's structured
output mode, then hands the decision to a ticketing system.

pip install anthropic pydantic
"""

from __future__ import annotations

import logging
import time
from typing import Literal

import anthropic
from anthropic import APIError, APIStatusError, APITimeoutError
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("support_router")

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

Team = Literal["billing", "technical", "account"]


class InboundEmail(BaseModel):
    """What arrives from the mail pipeline: { subject, body, fromAddress }."""

    model_config = ConfigDict(frozen=True)

    subject: str
    body: str
    from_address: str = Field(alias="fromAddress")


class RoutingDecision(BaseModel):
    """The only shape the classifier is allowed to produce.

    `team` is a Literal, not `str` — the model chooses one of three IDs,
    it cannot invent a fourth. Constrained decoding makes anything else
    structurally unrepresentable; Pydantic validates what comes back.
    """

    model_config = ConfigDict(extra="forbid")

    team: Team
    rationale: str = Field(min_length=1, max_length=140)


class RoutingFailure(Exception):
    """Raised when the model can't produce a valid decision after retries.

    Deliberately not swallowed into a default team — see escalate_for_manual_triage.
    """


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

# Pinned dated ID, not the floating "claude-haiku-4-5" alias — at this volume
# an unannounced model update is an unannounced deploy of the router.
_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM_PROMPT = """You triage inbound support emails for a SaaS product.

Classify each email into exactly one team:
- billing: invoices, payments, refunds, subscription plan/pricing, failed charges
- technical: product bugs, errors, integration/API issues, outages, how-to-use questions
- account: login/password/2FA, account access, team/seat management, profile/security settings

If an email could plausibly fit more than one team, pick the team that owns
the underlying cause, not the symptom (e.g. "I was charged twice after a
login retry" is billing, not account -- the money is the problem to fix).

Give a one-line rationale (<=140 chars) naming the specific signal in the
email that drove the decision."""


def _build_user_message(email: InboundEmail) -> str:
    return f"From: {email.from_address}\nSubject: {email.subject}\n\n{email.body}"


def route_email(
    client: anthropic.Anthropic,
    email: InboundEmail,
    *,
    max_attempts: int = 2,
) -> RoutingDecision:
    """Classify one email. Raises RoutingFailure rather than guessing.

    Callers must catch RoutingFailure and escalate to manual triage, not
    default it to any of the three teams -- a wrong-but-confident ticket is
    worse than a visibly unclassified one.
    """
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = client.messages.parse(
                model=_MODEL,
                max_tokens=300,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": _build_user_message(email)}],
                output_format=RoutingDecision,
                timeout=10.0,
            )
        except (APIStatusError, APITimeoutError, APIError) as exc:
            last_error = exc
            logger.warning("routing attempt %d/%d failed: %s", attempt, max_attempts, exc)
            if attempt < max_attempts:
                time.sleep(0.5 * attempt)
            continue

        if getattr(response, "stop_reason", None) == "refusal":
            last_error = RoutingFailure(f"model refused to classify: {email.subject!r}")
            logger.warning("routing attempt %d/%d refused", attempt, max_attempts)
            continue

        decision = response.parsed_output
        if decision is None:
            last_error = RoutingFailure("model output failed schema validation")
            logger.warning("routing attempt %d/%d: no parsed_output", attempt, max_attempts)
            continue

        return decision

    raise RoutingFailure(f"could not classify email after {max_attempts} attempts") from last_error


# ---------------------------------------------------------------------------
# Calling code — wire the router into the ticketing system
# ---------------------------------------------------------------------------


def create_ticket(*, team: Team, rationale: str, email: InboundEmail, idempotency_key: str) -> str:
    """Stub for the real ticketing API call.

    `idempotency_key` must come from the mail pipeline (e.g. the email's
    Message-ID header) rather than being generated here -- at this volume,
    queue redelivery will happen, and creating two tickets for one email is
    a worse failure than a duplicate-suppressed no-op.
    """
    raise NotImplementedError("wire this up to your ticketing API")


def escalate_for_manual_triage(*, email: InboundEmail, message_id: str, reason: str) -> None:
    """Deliberately NOT a ticket in billing/technical/account.

    A misrouted ticket looks identical to a correctly-routed one until a
    human wonders why it's in the wrong queue. An email that couldn't be
    classified should look obviously unclassified, not land silently in
    whichever team is the fallback default.
    """
    raise NotImplementedError("wire this up to your on-call / triage inbox")


def process_inbound_email(client: anthropic.Anthropic, raw: dict, message_id: str) -> None:
    email = InboundEmail.model_validate(raw)

    try:
        decision = route_email(client, email)
    except RoutingFailure as exc:
        logger.exception("routing failed for message %s -- escalating", message_id)
        escalate_for_manual_triage(email=email, message_id=message_id, reason=str(exc))
        return

    create_ticket(
        team=decision.team,
        rationale=decision.rationale,
        email=email,
        idempotency_key=message_id,
    )


if __name__ == "__main__":
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    for raw_email, message_id in fetch_batch_from_queue():  # your mail pipeline
        process_inbound_email(client, raw_email, message_id)
```

`★ Insight ─────────────────────────────────────`
`response.parsed_output is None` and `stop_reason == "refusal"` are handled as *distinct* failure signals before falling into the generic retry path — a refusal means the model chose not to answer (rare for neutral triage text, but email bodies are untrusted user input and could contain something that trips a safety classifier), while a `None` parsed output means it answered but the shape didn't validate. Collapsing both into one `except: pass` would hide which failure mode is actually happening in your logs.
`─────────────────────────────────────────────────`

Design notes:
- **Made impossible:** the model cannot route to a team outside the three named ones (Literal + `extra="forbid"` + retry-then-fail), and a failed/refused classification cannot silently masquerade as a real routing decision — it's forced through `RoutingFailure` into a visibly separate manual-triage path.
- **Left possible on purpose:** a wrong-but-valid classification (e.g. billing vs. technical judgment call) — no model call catches that, only an eval set with real examples would. I didn't build one here since none was requested; add `RoutingDecision` assertions over a held-out set before changing the prompt or model in production.
- **Idempotency and ticket creation** are stubbed rather than implemented, since "the ticketing system" wasn't specified — but the `idempotency_key` parameter is load-bearing, not decorative, given the volume.