My mistake — you asked for the code shown inline, not written to disk. Here it is.

## `types.py` — request/response contracts

```python
"""Shared types for the support-email router."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Team(str, Enum):
    BILLING = "billing"
    TECHNICAL = "technical"
    ACCOUNT = "account"


@dataclass(frozen=True)
class InboundEmail:
    subject: str
    body: str
    from_address: str


@dataclass(frozen=True)
class RoutingResult:
    team: Team
    rationale: str  # one-line justification, shown to agents in the ticket
```

★ Insight ─────────────────────────────────────
`Team` is a `str, Enum` rather than a bare string type hint. A bare `str` lets any typo (`"biling"`) sail through silently and land a ticket in a queue nobody watches. Because the Anthropic tool schema below also constrains `team` to an `enum`, you get two independent backstops: the model can't emit an invalid value, and even if it somehow did, `Team(payload["team"])` raises instead of creating a `RoutingResult` with garbage in it.
─────────────────────────────────────────────────

## `classifier.py` — the routing call

```python
"""Classifies inbound support emails into billing / technical / account."""

from __future__ import annotations

import logging

import anthropic

from types import InboundEmail, RoutingResult, Team

logger = logging.getLogger(__name__)

# Haiku is deliberately chosen over Sonnet/Opus: this is single-label
# classification over short text at a few thousand calls/day — the task
# doesn't need deep reasoning, and Haiku's lower per-call cost and latency
# matter far more at that volume than marginal accuracy gains.
MODEL = "claude-haiku-4-5-20251001"
MAX_RETRIES = 3

CLASSIFY_TOOL = {
    "name": "classify_email",
    "description": "Route a customer support email to exactly one team.",
    "input_schema": {
        "type": "object",
        "properties": {
            "team": {
                "type": "string",
                "enum": [t.value for t in Team],
                "description": (
                    "billing: invoices, payments, refunds, plan/subscription cost. "
                    "technical: product bugs, errors, integration/API issues, how-to. "
                    "account: login, password, profile, permissions, org/user management."
                ),
            },
            "rationale": {
                "type": "string",
                "description": "One sentence explaining the routing decision.",
            },
        },
        "required": ["team", "rationale"],
    },
}

SYSTEM_PROMPT = (
    "You triage inbound customer support emails for a SaaS product. "
    "Read the subject and body, then call classify_email with the single "
    "best-fit team and a one-sentence rationale. Always pick exactly one "
    "team, even if the email touches more than one area — choose the team "
    "that owns the primary ask."
)


class ClassificationError(Exception):
    """Raised when the model fails to return a usable classification after retries."""


def classify_email(client: anthropic.Anthropic, email: InboundEmail) -> RoutingResult:
    user_content = (
        f"From: {email.from_address}\n"
        f"Subject: {email.subject}\n\n"
        f"{email.body}"
    )

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=256,
                system=SYSTEM_PROMPT,
                tools=[CLASSIFY_TOOL],
                tool_choice={"type": "tool", "name": "classify_email"},
                messages=[{"role": "user", "content": user_content}],
            )
            return _parse_response(response)
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
            last_error = exc
            logger.warning(
                "classify_email attempt %d/%d failed: %s", attempt, MAX_RETRIES, exc
            )
        except ClassificationError as exc:
            last_error = exc
            logger.warning(
                "classify_email attempt %d/%d produced bad payload: %s",
                attempt, MAX_RETRIES, exc,
            )

    raise ClassificationError(f"exhausted {MAX_RETRIES} attempts") from last_error


def _parse_response(response: anthropic.types.Message) -> RoutingResult:
    for block in response.content:
        if block.type == "tool_use" and block.name == "classify_email":
            payload = block.input
            try:
                team = Team(payload["team"])
            except (KeyError, ValueError) as exc:
                raise ClassificationError(f"invalid team in payload: {payload!r}") from exc
            rationale = payload.get("rationale", "").strip()
            if not rationale:
                raise ClassificationError(f"missing rationale in payload: {payload!r}")
            return RoutingResult(team=team, rationale=rationale)
    raise ClassificationError("no classify_email tool_use block in response")
```

★ Insight ─────────────────────────────────────
`tool_choice={"type": "tool", "name": "classify_email"}` forces the model to call that specific tool on this turn — it can't respond with plain text instead. Combined with the JSON-Schema `enum` on `team`, this is Anthropic's answer to "make the LLM return exactly one of N labels": you get typed, parseable output without asking the model to emit raw JSON in prose (which invites markdown fences, preambles, and occasional schema drift that free-text parsing has to defend against).
─────────────────────────────────────────────────

## `ticketing.py` — calling code / hand-off

```python
"""Wires classification output into the ticketing system."""

from __future__ import annotations

import logging

import anthropic

from classifier import ClassificationError, classify_email
from types import InboundEmail, RoutingResult

logger = logging.getLogger(__name__)


def build_ticket_payload(email: InboundEmail, routing: RoutingResult) -> dict:
    return {
        "subject": email.subject,
        "body": email.body,
        "from_address": email.from_address,
        "team": routing.team.value,
        "rationale": routing.rationale,
    }


def route_and_file_ticket(client: anthropic.Anthropic, email: InboundEmail) -> dict:
    """Classify one email and return the payload to send to the ticketing API.

    Swap the final line for your real ticketing client call, e.g.
    `ticketing_client.tickets.create(**payload)`.
    """
    routing = classify_email(client, email)
    payload = build_ticket_payload(email, routing)
    logger.info("routed email from=%s -> team=%s", email.from_address, routing.team.value)
    return payload


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    example = InboundEmail(
        subject="Can't log in after password reset",
        body="I reset my password an hour ago but the app still says my credentials are invalid.",
        from_address="customer@example.com",
    )

    try:
        ticket = route_and_file_ticket(client, example)
        print(ticket)
    except ClassificationError:
        logger.exception("failed to route email from=%s", example.from_address)
        # TODO: your call — see below
```

## One decision I've deliberately left for you

The `try/except ClassificationError` block at the bottom is where retries are exhausted and every attempt still failed. What happens next is a product/ops call, not a technical one, and it changes the shape of the code around it:

- **Route to a default/catch-all team** (e.g. `account`) so nothing is silently dropped, accepting some tickets land in the wrong queue.
- **Route to a human-triage queue** distinct from the three teams, so misroutes never masquerade as confident classifications.
- **Fail the whole ingestion and alert on-call**, accepting that a transient API blip stalls ticket creation until someone looks.

At a few thousand emails/day, a few dozen of these will happen — pick the one whose failure mode you'd rather explain to a customer. Write it as the body of a `handle_classification_failure(email: InboundEmail, error: ClassificationError) -> dict` function and I'll wire it into `route_and_file_ticket`.