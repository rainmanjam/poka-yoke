```python
import json
from dataclasses import dataclass
from typing import Literal
from anthropic import Anthropic


@dataclass
class Email:
    """Incoming customer support email."""
    subject: str
    body: str
    from_address: str


@dataclass
class RoutingResult:
    """Routed email with team assignment and reasoning."""
    team: Literal["billing", "technical", "account"]
    rationale: str


class SupportEmailRouter:
    """Routes support emails to the correct team using Claude."""

    def __init__(self, api_key: str | None = None):
        self.client = Anthropic(api_key=api_key)
        self.model = "claude-3-5-sonnet-20241022"

    def classify(self, email: Email) -> RoutingResult:
        """Classify a single email and return routing decision."""
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=256,
            temperature=0,
            tools=[
                {
                    "name": "route_support_email",
                    "description": "Route the email to the appropriate support team",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "team": {
                                "type": "string",
                                "enum": ["billing", "technical", "account"],
                                "description": "Target support team"
                            },
                            "rationale": {
                                "type": "string",
                                "description": "One-line reasoning for this routing"
                            }
                        },
                        "required": ["team", "rationale"]
                    }
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": f"""Route this customer support email to exactly one team.

From: {email.from_address}
Subject: {email.subject}

Body:
{email.body}

Categories:
- billing: Payments, invoices, refunds, subscription issues
- technical: Bugs, crashes, features, performance
- account: Access, passwords, profile, permissions

Call route_support_email with your decision."""
                }
            ]
        )

        # Extract tool use response
        for block in response.content:
            if block.type == "tool_use":
                return RoutingResult(
                    team=block.input["team"],
                    rationale=block.input["rationale"]
                )

        raise ValueError("Claude did not return a routing decision")

    def route_batch(self, emails: list[Email]) -> list[RoutingResult]:
        """Route multiple emails. For high volume, consider parallel processing."""
        return [self.classify(email) for email in emails]


def save_to_ticketing_system(result: RoutingResult, email: Email) -> None:
    """Write routed email to ticketing system (mock implementation)."""
    ticket = {
        "team": result.team,
        "from": email.from_address,
        "subject": email.subject,
        "body": email.body,
        "routing_reason": result.rationale
    }
    print(json.dumps(ticket, indent=2))


if __name__ == "__main__":
    router = SupportEmailRouter()

    # Example emails
    test_emails = [
        Email(
            subject="Refund request for order #12345",
            body="I was charged twice for my subscription last month. Can you refund the duplicate charge?",
            from_address="alice@example.com"
        ),
        Email(
            subject="App crashes on startup - iOS",
            body="Updated to v2.1 this morning. Now the app crashes immediately after launch. Tried reinstalling.",
            from_address="bob@example.com"
        ),
        Email(
            subject="Can't reset my password",
            body="I forgot my password. Clicked reset but never received the email. Been locked out for 2 days.",
            from_address="charlie@example.com"
        ),
        Email(
            subject="Invoice question",
            body="The November invoice shows a different amount than our contract. Which charges are these?",
            from_address="dave@example.com"
        ),
    ]

    # Route and save each email
    for email in test_emails:
        result = router.classify(email)
        print(f"\n{'='*60}")
        print(f"From: {email.from_address}")
        print(f"Subject: {email.subject}")
        print(f"→ Routed to: {result.team.upper()}")
        print(f"Reason: {result.rationale}")
        save_to_ticketing_system(result, email)
```

**Key design choices:**

- **Tool use for routing**: The `route_support_email` tool ensures Claude always returns valid JSON with the three categories enforced by the schema—no parsing errors or invalid values.
- **Temperature=0**: Deterministic classification for consistency at scale.
- **Types first**: `Email` and `RoutingResult` make the contract clear and enable type checking.
- **Batch support**: `route_batch()` processes multiple emails; for thousands/day, add async calls or a queue.
- **Clear instructions**: The prompt explicitly lists what each team handles so Claude doesn't drift between categories.

For production at 1000s/day, add: async batching with `asyncio`, token counting to optimize costs, retry logic, and logging for misclassifications.