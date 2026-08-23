Here is the complete implementation for the support-email router, applying the poka-yoke design method. 

### Mistake-proofing Design Rationale

Before writing the code, we enumerate the misuses and close them:

1. **Unvalidated external input (C3/C7)**: A malformed payload from the email provider causes `KeyError`s deep inside the classifier. 
   - **Device**: `IncomingEmail` Pydantic model with `frozen=True` and `extra="forbid"`. We parse once at the boundary.
   - **Rung**: **Control**. Invalid data cannot cross the boundary.
2. **Stringly-typed enums & non-exhaustive branches (C4/F1)**: Claude returns "sales" instead of a valid team, or a new team is added next year and the routing code silently drops it.
   - **Device**: `Team` type as a `Literal["billing", "technical", "account"]`. We enforce this on Claude's output via Pydantic, and enforce it in the routing dispatcher via `match` and `assert_never`.
   - **Rung**: **Control**. The type checker fails the build if a branch is missed, and Pydantic raises at runtime if Claude hallucinates.
3. **Duplicate tickets on retry (M2)**: A network blip between the router and the ticketing system causes a retry, opening duplicate tickets.
   - **Device**: Added a required `message_id` to `IncomingEmail` to act as an idempotency key for the ticketing system.
   - **Rung**: **Control**. The idempotency key is un-skippable.
4. **Config discovered missing at runtime (F4)**: The script crashes at 3am because `os.environ["ANTHROPIC_API_KEY"]` fails.
   - **Device**: `pydantic_settings.BaseSettings` loaded exactly once at import.
   - **Rung**: **Control**. The process fails to boot without the key, failing the deploy instead of a request.
5. **Adjacent same-type parameters (C1)**: Swapping `team` and `rationale` in the ticketing call.
   - **Device**: Forced keyword-only arguments (`*`) on all function signatures.
   - **Rung**: **Warning**. Mypy will catch it if types differ, but keyword arguments make swaps visible.

**Consciously left possible**:
- **Claude hallucinating invalid JSON**: We use Anthropic's `tool_choice`, which heavily biases toward correct schema, but if Claude fails, Pydantic will raise a `ValidationError`. We leave this as a runtime exception (Warning/Self-check) to let the upstream queue (assuming one exists for thousand-a-day volume) retry it, rather than writing custom retry loops.

### The Code

```python
from typing import Literal, assert_never
import anthropic
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from pydantic_settings import BaseSettings

# F4. Config validated at startup. 
# A missing ANTHROPIC_API_KEY fails the deploy immediately.
class Settings(BaseSettings):
    anthropic_api_key: str

settings = Settings()
client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

# C4. Literal union instead of strings.
Team = Literal["billing", "technical", "account"]

# C3/C7. Parse at the boundary. Frozen so downstream cannot mutate it.
class IncomingEmail(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    message_id: str  # M2. Required idempotency key
    from_address: EmailStr
    subject: str = Field(min_length=1)
    body: str

# C8. Exact required fields instead of a bag of optionals.
class RoutingDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    team: Team
    rationale: str = Field(description="A one-line rationale for the routing decision.")

async def classify_email(*, email: IncomingEmail) -> RoutingDecision:
    """
    Classifies an email into a routing decision using Claude.
    """
    response = await client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        temperature=0.0,
        messages=[
            {
                "role": "user", 
                "content": f"From: {email.from_address}\nSubject: {email.subject}\n\n{email.body}"
            }
        ],
        tools=[
            {
                "name": "route_ticket",
                "description": "Route the support ticket to exactly one of the available teams.",
                "input_schema": RoutingDecision.model_json_schema()
            }
        ],
        tool_choice={"type": "tool", "name": "route_ticket"}
    )
    
    # Extract the tool use payload and parse it into our guaranteed type
    for block in response.content:
        if block.type == "tool_use" and block.name == "route_ticket":
            # If Claude hallucinates a team not in the Literal, Pydantic raises ValidationError
            return RoutingDecision.model_validate(block.input)
            
    raise RuntimeError("Claude did not return a routing decision")

async def process_webhook(*, raw_payload: dict) -> None:
    """
    The calling code that receives a raw payload and pushes to the ticketing system.
    """
    # 1. Parse at the boundary (Control)
    email = IncomingEmail.model_validate(raw_payload)
    
    # 2. Classify
    decision = await classify_email(email=email)
    
    # 3. Exhaustive branching for side effects (F1)
    match decision.team:
        case "billing":
            await create_ticket(team="billing", email=email, rationale=decision.rationale)
        case "technical":
            await create_ticket(team="technical", email=email, rationale=decision.rationale)
        case "account":
            await create_ticket(team="account", email=email, rationale=decision.rationale)
        case _:
            # If a team is added to the Team Literal but missed here, mypy breaks the build
            assert_never(decision.team)

async def create_ticket(*, team: Team, email: IncomingEmail, rationale: str) -> None:
    """
    Mocks sending the ticket to the upstream ticketing system.
    C1: Keyword-only arguments prevent swapping `team` and `rationale`.
    """
    # M2: Pass email.message_id to the ticketing system as an idempotency key 
    # to prevent duplicate tickets on retry.
    print(f"[{email.message_id}] Routing to {team}: {rationale}")

```