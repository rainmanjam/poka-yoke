I'll write a complete support-email router using the Anthropic SDK with structured output for reliable classification.

```python
from dataclasses import dataclass
from typing import Literal
from anthropic import Anthropic

# Types
@dataclass
class Email:
    subject: str
    body: str
    from_address: str

@dataclass
class RoutingResult:
    team: Literal["billing", "technical", "account"]
    rationale: str
    email: Email

# Classifier
class SupportEmailRouter:
    def __init__(self, api_key: str | None = None):
        self.client = Anthropic(api_key=api_key)
        self.model = "claude-3-5-sonnet-20241022"
    
    def classify_email(self, email: Email) -> RoutingResult:
        """Route a support email to exactly one team using Claude."""
        
        message = self.client.messages.create(
            model=self.model,
            max_tokens=256,
            system="""You are a support email router. Classify each email to exactly one team.

Teams and their scope:
- billing: payment issues, invoices, subscriptions, refunds, pricing questions
- technical: bugs, feature requests, API issues, integration problems, error messages
- account: login issues, password resets, profile changes, account access, permissions

Respond with your classification as JSON.""",
            messages=[
                {
                    "role": "user",
                    "content": f"""Email to classify:

From: {email.from_address}
Subject: {email.subject}

Body:
{email.body}

Respond with ONLY valid JSON (no markdown, no extra text):
{{"team": "billing" | "technical" | "account", "rationale": "one sentence explanation"}}"""
                }
            ],
        )
        
        import json
        response_text = message.content[0].text
        classification = json.loads(response_text)
        
        return RoutingResult(
            team=classification["team"],
            rationale=classification["rationale"],
            email=email
        )
    
    def format_for_ticketing(self, result: RoutingResult) -> dict:
        """Format routing result for ticketing system."""
        return {
            "team": result.team,
            "rationale": result.rationale,
            "from": result.email.from_address,
            "subject": result.email.subject,
            "body": result.email.body,
        }

# Calling code with examples
if __name__ == "__main__":
    router = SupportEmailRouter()
    
    # Example emails
    emails = [
        Email(
            subject="Can't log into my account",
            body="I'm getting an 'invalid credentials' error even though I'm sure my password is correct. I haven't changed it in months.",
            from_address="sarah@acme.com"
        ),
        Email(
            subject="API integration failing with 500 errors",
            body="We're getting persistent 500 errors when calling the /api/v2/webhooks endpoint. Started this morning after your deployment. Can you check the service status?",
            from_address="dev@startup.io"
        ),
        Email(
            subject="Unexpected charge on invoice",
            body="We were billed $4,500 this month but our plan should only cost $999. Can you review the charges and correct this immediately?",
            from_address="finance@bigcorp.com"
        ),
        Email(
            subject="Request for custom integration",
            body="We need to connect your system to our internal CRM. Is custom API access available on our plan or do we need an upgrade?",
            from_address="ops@techfirm.com"
        ),
        Email(
            subject="Password reset not working",
            body="I clicked 'Forgot Password' but never received the reset email. I've checked spam too.",
            from_address="john.doe@example.com"
        ),
    ]
    
    print("Support Email Router - Classification Results\n" + "=" * 50)
    
    for email in emails:
        result = router.classify_email(email)
        ticket = router.format_for_ticketing(result)
        
        print(f"\nFrom: {ticket['from']}")
        print(f"Subject: {ticket['subject']}")
        print(f"Team: {ticket['team']}")
        print(f"Rationale: {ticket['rationale']}")
        print("-" * 50)
```

**Key design decisions:**

- **Structured output**: Claude returns JSON directly, avoiding parse-only-structured-output overhead for high-volume routing
- **Single model call**: No multi-turn conversation; each email classified in one request
- **Clear team definitions**: System prompt explicitly defines scope to reduce ambiguity
- **Deterministic JSON**: Removes markdown formatting so parsing is robust
- **Type safety**: Dataclasses provide clear contracts between components

For a few thousand daily emails, consider:
- **Batching with threads**: Use `concurrent.futures` to parallelize classify calls
- **Caching**: Cache identical subject+body hashes to skip redundant classifications
- **Fallback routing**: Add a catch-all for edge cases that don't fit cleanly

This routes emails reliably and integrates directly with any ticketing system that accepts team+rationale pairs.