Here is the support-email router, built according to the `design` mode Poka-Yoke principles.

### Design Reasoning

**Misuses enumerated:**
1. **Adjacent string parameters (C1):** Passing `body` as `subject` because both are bare strings.
2. **Unvalidated external input (C7):** Webhooks delivering malformed payloads or invalid email addresses.
3. **Stringly-typed LLM outputs (C4):** The LLM hallucinating a team like `"Tech"` or `"Billing"` instead of the exact system strings `"technical"` or `"billing"`.
4. **Non-exhaustive branching (F1):** Adding a new team later and forgetting to update the dispatch logic.
5. **Non-idempotent retryable effects (M2):** The webhook retrying on a timeout and creating two duplicate tickets in the system.

**What the design makes impossible (Control Rung):**
- **Swapping `subject` and `body`** is impossible. `classify_email` uses keyword-only arguments (`*`) and takes a single parsed `IncomingEmail` value object rather than primitive strings.
- **Malformed payloads** are blocked at the boundary by `IncomingEmail.model_validate` using `extra="forbid"` and `EmailStr`.
- **Hallucinated teams** cannot proceed. `Team` is a `Literal[...]`. If the LLM generates a bad team, `RoutingDecision.model_validate()` fails immediately rather than passing corrupted data downstream.
- **Unreachable routing branches** are a compiler error. Using `assert_never()` inside the `match` block ensures `mypy` breaks the build if someone adds `"sales"` to the `Team` literal without handling it here.
- **Duplicate ticket creation** is blocked by making `idempotency_key` a required argument on the external mutation (`submit_to_ticketing`), populated from an assumed `message_id`.

**What is consciously left possible:**
- **LLM validation failures:** If the LLM output violates the schema, the code throws a `ValidationError` (Warning rung: Fail fast and loud). The type system cannot force a non-deterministic LLM to output perfect JSON, so the device moves to runtime. A production system would catch this exception and route the payload to a dead-letter queue (DLQ) for human triage.

### The Code

```python
import json
from typing import Literal, assert_never
from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationError
import anthropic

# 1. The Types (Control-rung devices)

# Exhaustive literal. A typo here or an unhandled variant downstream breaks mypy.
Team = Literal["billing", "technical", "account"]

class IncomingEmail(BaseModel):
    """
    Boundary type for incoming emails. 
    frozen=True prevents silent downstream mutation.
    extra='forbid' catches malformed payloads loudly.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    message_id: str = Field(..., min_length=1)  # Assumed necessary for idempotency
    subject: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    from_address: EmailStr  # Enforces valid email format at the edge

class RoutingDecision(BaseModel):
    """
    Boundary type for the LLM's output.
    Forces exactly one valid team and a rationale.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    team: Team
    rationale: str = Field(..., description="One-line rationale for the routing decision")


# 2. The Classifier

def classify_email(*, client: anthropic.Anthropic, email: IncomingEmail) -> RoutingDecision:
    """
    Keyword-only arguments prevent parameter swapping.
    Takes a parsed IncomingEmail, returning a parsed RoutingDecision.
    """
    routing_tool = {
        "name": "route_email",
        "description": "Route the customer email to the appropriate team.",
        "input_schema": RoutingDecision.model_json_schema()
    }

    prompt = (
        f"From: {email.from_address}\n"
        f"Subject: {email.subject}\n"
        f"Body:\n{email.body}\n\n"
        "Please route this email to the correct team."
    )

    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
        tools=[routing_tool],
        tool_choice={"type": "tool", "name": "route_email"}
    )

    # Extract the tool use block
    tool_use = next(block for block in response.content if block.type == "tool_use")
    
    # Parse and validate the LLM output. If it hallucinated a wrong team, 
    # Pydantic raises ValidationError (Fail fast and loud).
    return RoutingDecision.model_validate(tool_use.input)


# 3. The Calling Code

def handle_incoming_webhook(*, raw_payload: dict, client: anthropic.Anthropic) -> None:
    """
    Simulates the entry point (e.g., an HTTP request handler).
    """
    try:
        # C7: Parse, don't validate. We only pass the typed object inward.
        email = IncomingEmail.model_validate(raw_payload)
        
        decision = classify_email(client=client, email=email)
        
        # F1: Exhaustive matching. 
        match decision.team:
            case "billing":
                queue = "billing_q"
            case "technical":
                queue = "tech_q"
            case "account":
                queue = "account_q"
            case _:
                # If a developer adds a Team variant but forgets a case here, mypy fails.
                assert_never(decision.team)

        # M2: Required idempotency key for external mutation.
        submit_to_ticketing(
            queue=queue, 
            decision=decision, 
            idempotency_key=email.message_id
        )

    except ValidationError as e:
        # X1: Don't swallow the error. In production, route to a dead-letter queue.
        raise RuntimeError(f"Failed to process email: {e}") from e


def submit_to_ticketing(*, queue: str, decision: RoutingDecision, idempotency_key: str) -> None:
    """
    External write. idempotency_key is required so retries don't double-create tickets.
    """
    pass
```