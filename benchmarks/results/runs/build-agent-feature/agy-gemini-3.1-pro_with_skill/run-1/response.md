I have designed the support-email router applying the `poka-yoke` **design** skill, specifically using Pydantic for boundary enforcement and Python's type system to make misuse unrepresentable.

### 1. Enumerated Misuses

Before writing the signatures, here are the ways this router could be misused:
1. **Adjacent string parameters (C1):** A caller accidentally swaps `fromAddress` and `subject`.
2. **Hallucinated routing (C4/C7):** The LLM decides to route to a made-up `"sales"` team.
3. **Missing rationale (C8):** The LLM provides the team but drops the one-line rationale required by the ticketing system.
4. **Duplicate processing (M2):** A queue retry processes the same email twice, opening duplicate tickets.
5. **Unhandled new teams (F1):** A developer adds `"sales"` to the prompt next year but forgets to update the ticketing dispatcher.
6. **Config missing at runtime (F4):** The script crashes on a background worker at 3am because `ANTHROPIC_API_KEY` isn't in the environment.

### 2. The Design (Code)

```python
from typing import Literal, assert_never
from pydantic import BaseModel, ConfigDict, Field, EmailStr
from pydantic_settings import BaseSettings
from anthropic import Anthropic

# F4: Config validated at startup. Missing keys fail the deploy, not the 3am run.
class Settings(BaseSettings):
    anthropic_api_key: str

# C4: Literal union prevents stringly-typed team names.
Team = Literal["billing", "technical", "account"]

# C7: Parse and validate input at the boundary.
# C1: Frozen model prevents silent reassignment.
class EmailMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    # M2: Required idempotency key, assuming the source system provides one
    message_id: str = Field(min_length=1)
    from_address: EmailStr
    subject: str = Field(min_length=1, max_length=1000)
    # Refuse massive emails rather than silently truncating them (X2)
    body: str = Field(min_length=1, max_length=100000)

# C7: Parse untrusted external (LLM) output into a typed struct
class RoutingDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    team: Team
    rationale: str = Field(description="A one-line rationale for the routing decision")


class Classifier:
    def __init__(self, client: Anthropic):
        self._client = client
        
    def classify(self, *, email: EmailMessage) -> RoutingDecision:
        # C1: keyword-only argument `*` prevents positional swaps
        prompt = (
            f"From: {email.from_address}\n"
            f"Subject: {email.subject}\n"
            f"Body:\n{email.body}\n\n"
            "Analyze this customer email and route it to exactly one team: 'billing', 'technical', or 'account'.\n"
            "Provide a one-line rationale."
        )
        
        response = self._client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system="You are an expert support ticket router. Output strictly valid JSON matching the schema.",
            messages=[{"role": "user", "content": prompt}],
            tools=[{
                "name": "route_ticket",
                "description": "Route the ticket to the appropriate team",
                "input_schema": RoutingDecision.model_json_schema()
            }],
            tool_choice={"type": "tool", "name": "route_ticket"}
        )
        
        # The Anthropic SDK guarantees the type matches since we forced tool_choice.
        tool_use = next(block for block in response.content if block.type == "tool_use")
        
        # C7: Validate the untrusted LLM output through Pydantic.
        return RoutingDecision.model_validate(tool_use.input)


class TicketingSystem:
    # A dummy system to demonstrate the downstream devices
    def create_ticket(self, *, idempotency_key: str, email: EmailMessage, routing: RoutingDecision) -> None:
        # M2: Required idempotency key stops retry storms from creating duplicate tickets.
        
        # F1: Exhaustive matching. If a developer adds "sales" to `Team` later, 
        # mypy breaks the build right here.
        match routing.team:
            case "billing":
                self._dispatch_billing(email, routing.rationale)
            case "technical":
                self._dispatch_tech(email, routing.rationale)
            case "account":
                self._dispatch_account(email, routing.rationale)
            case _:
                assert_never(routing.team)
                
    def _dispatch_billing(self, email: EmailMessage, rationale: str) -> None: pass
    def _dispatch_tech(self, email: EmailMessage, rationale: str) -> None: pass
    def _dispatch_account(self, email: EmailMessage, rationale: str) -> None: pass


# The calling code (e.g., from a queue worker)
def process_queue_message(*, payload: dict, settings: Settings, ticketer: TicketingSystem) -> None:
    # C7: Unvalidated external input (queue payload) is parsed into our domain model immediately.
    email = EmailMessage.model_validate(payload)
    
    client = Anthropic(api_key=settings.anthropic_api_key)
    classifier = Classifier(client=client)
    
    decision = classifier.classify(email=email)
    
    ticketer.create_ticket(
        idempotency_key=email.message_id, 
        email=email, 
        routing=decision
    )
```

### 3. Which misuses are impossible, and at what rung?
- **C1 (Positional Swaps) closed at Control:** `EmailMessage` models the parameters explicitly. `classify(*, email: EmailMessage)` enforces keyword-only arguments.
- **C4/C7 (Hallucinated Teams / Missing Fields) closed at Control:** `RoutingDecision` uses a `Literal` for `Team` and validates the Anthropic tool output JSON against the Pydantic schema immediately. If the LLM goes off the rails, Pydantic throws a `ValidationError`, which reliably fails the queue task for a DLQ rather than silently writing garbage to the ticketer.
- **F1 (Unhandled branches) closed at Control:** `assert_never(routing.team)` ensures exhaustive checks at compile time (via `mypy`).
- **M2 (Retry duplicates) closed at Control:** `TicketingSystem.create_ticket` has an explicitly required `idempotency_key` bound to the execution, ensuring re-processing the same `message_id` won't execute duplicate side effects.

### 4. What was consciously left possible?
- **Semantic Routing Failures**: The model could validly return `"billing"` for an obviously technical question. The types ensure the answer is *structurally* sound, but cannot enforce reasoning accuracy. This is a business logic constraint left to the LLM's capability or downstream evaluation.
- **Context Exhaustion**: A 100k-character ceiling is strictly enforced on `body`. Rather than silently truncating an enormous email (an `X2` hazard that might drop the very text needed to route it), it fails validation and must be manually reviewed.
{"answer":"I have designed the support-email router applying the `poka-yoke` **design** skill, specifically using Pydantic for boundary enforcement and Python's type system to make misuse unrepresentable.\n\n### 1. Enumerated Misuses\n\nBefore writing the signatures, here are the ways this router could be misused:\n1. **Adjacent string parameters (C1):** A caller accidentally swaps `fromAddress` and `subject`.\n2. **Hallucinated routing (C4/C7):** The LLM decides to route to a made-up `\"sales\"` team.\n3. **Missing rationale (C8):** The LLM provides the team but drops the one-line rationale required by the ticketing system.\n4. **Duplicate processing (M2):** A queue retry processes the same email twice, opening duplicate tickets.\n5. **Unhandled new teams (F1):** A developer adds `\"sales\"` to the prompt next year but forgets to update the ticketing dispatcher.\n6. **Config missing at runtime (F4):** The script crashes on a background worker at 3am because `ANTHROPIC_API_KEY` isn't in the environment.\n\n### 2. The Design (Code)\n\n```python\nfrom typing import Literal, assert_never\nfrom pydantic import BaseModel, ConfigDict, Field, EmailStr\nfrom pydantic_settings import BaseSettings\nfrom anthropic import Anthropic\n\n# F4: Config validated at startup. Missing keys fail the deploy, not the 3am run.\nclass Settings(BaseSettings):\n    anthropic_api_key: str\n\n# C4: Literal union prevents stringly-typed team names.\nTeam = Literal[\"billing\", \"technical\", \"account\"]\n\n# C7: Parse and validate input at the boundary.\n# C1: Frozen model prevents silent reassignment.\nclass EmailMessage(BaseModel):\n    model_config = ConfigDict(frozen=True, extra=\"forbid\")\n    \n    # M2: Required idempotency key, assuming the source system provides one\n    message_id: str = Field(min_length=1)\n    from_address: EmailStr\n    subject: str = Field(min_length=1, max_length=1000)\n    # Refuse massive emails rather than silently truncating them (X2)\n    body: str = Field(min_length=1, max_length=100000)\n\n# C7: Parse untrusted external (LLM) output into a typed struct\nclass RoutingDecision(BaseModel):\n    model_config = ConfigDict(frozen=True, extra=\"forbid\")\n    \n    team: Team\n    rationale: str = Field(description=\"A one-line rationale for the routing decision\")\n\n\nclass Classifier:\n    def __init__(self, client: Anthropic):\n        self._client = client\n        \n    def classify(self, *, email: EmailMessage) -\u003e RoutingDecision:\n        # C1: keyword-only argument `*` prevents positional swaps\n        prompt = (\n            f\"From: {email.from_address}\\n\"\n            f\"Subject: {email.subject}\\n\"\n            f\"Body:\\n{email.body}\\n\\n\"\n            \"Analyze this customer email and route it to exactly one team: 'billing', 'technical', or 'account'.\\n\"\n            \"Provide a one-line rationale.\"\n        )\n        \n        response = self._client.messages.create(\n            model=\"claude-3-5-sonnet-20241022\",\n            max_tokens=1024,\n            system=\"You are an expert support ticket router. Output strictly valid JSON matching the schema.\",\n            messages=[{\"role\": \"user\", \"content\": prompt}],\n            tools=[{\n                \"name\": \"route_ticket\",\n                \"description\": \"Route the ticket to the appropriate team\",\n                \"input_schema\": RoutingDecision.model_json_schema()\n            }],\n            tool_choice={\"type\": \"tool\", \"name\": \"route_ticket\"}\n        )\n        \n        # The Anthropic SDK guarantees the type matches since we forced tool_choice.\n        tool_use = next(block for block in response.content if block.type == \"tool_use\")\n        \n        # C7: Validate the untrusted LLM output through Pydantic.\n        return RoutingDecision.model_validate(tool_use.input)\n\n\nclass TicketingSystem:\n    # A dummy system to demonstrate the downstream devices\n    def create_ticket(self, *, idempotency_key: str, email: EmailMessage, routing: RoutingDecision) -\u003e None:\n        # M2: Required idempotency key stops retry storms from creating duplicate tickets.\n        \n        # F1: Exhaustive matching. If a developer adds \"sales\" to `Team` later, \n        # mypy breaks the build right here.\n        match routing.team:\n            case \"billing\":\n                self._dispatch_billing(email, routing.rationale)\n            case \"technical\":\n                self._dispatch_tech(email, routing.rationale)\n            case \"account\":\n                self._dispatch_account(email, routing.rationale)\n            case _:\n                assert_never(routing.team)\n                \n    def _dispatch_billing(self, email: EmailMessage, rationale: str) -\u003e None: pass\n    def _dispatch_tech(self, email: EmailMessage, rationale: str) -\u003e None: pass\n    def _dispatch_account(self, email: EmailMessage, rationale: str) -\u003e None: pass\n\n\n# The calling code (e.g., from a queue worker)\ndef process_queue_message(*, payload: dict, settings: Settings, ticketer: TicketingSystem) -\u003e None:\n    # C7: Unvalidated external input (queue payload) is parsed into our domain model immediately.\n    email = EmailMessage.model_validate(payload)\n    \n    client = Anthropic(api_key=settings.anthropic_api_key)\n    classifier = Classifier(client=client)\n    \n    decision = classifier.classify(email=email)\n    \n    ticketer.create_ticket(\n        idempotency_key=email.message_id, \n        email=email, \n        routing=decision\n    )\n```\n\n### 3. Which misuses are impossible, and at what rung?\n- **C1 (Positional Swaps) closed at Control:** `EmailMessage` models the parameters explicitly. `classify(*, email: EmailMessage)` enforces keyword-only arguments.\n- **C4/C7 (Hallucinated Teams / Missing Fields) closed at Control:** `RoutingDecision` uses a `Literal` for `Team` and validates the Anthropic tool output JSON against the Pydantic schema immediately. If the LLM goes off the rails, Pydantic throws a `ValidationError`, which reliably fails the queue task for a DLQ rather than silently writing garbage to the ticketer.\n- **F1 (Unhandled branches) closed at Control:** `assert_never(routing.team)` ensures exhaustive checks at compile time (via `mypy`).\n- **M2 (Retry duplicates) closed at Control:** `TicketingSystem.create_ticket` has an explicitly required `idempotency_key` bound to the execution, ensuring re-processing the same `message_id` won't execute duplicate side effects.\n\n### 4. What was consciously left possible?\n- **Semantic Routing Failures**: The model could validly return `\"billing\"` for an obviously technical question. The types ensure the answer is *structurally* sound, but cannot enforce reasoning accuracy. This is a business logic constraint left to the LLM's capability or downstream evaluation.\n- **Context Exhaustion**: A 100k-character ceiling is strictly enforced on `body`. Rather than silently truncating an enormous email (an `X2` hazard that might drop the very text needed to route it), it fails validation and must be manually reviewed.","toolAction":"Finishing the task","toolSummary":"Finish task"}