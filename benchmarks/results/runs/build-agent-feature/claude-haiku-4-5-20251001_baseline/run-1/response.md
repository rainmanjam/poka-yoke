```python
from typing import Literal
from pydantic import BaseModel, EmailStr
from anthropic import Anthropic

# ─────────────────────────────────────────────────────────────────
# Types
# ─────────────────────────────────────────────────────────────────

class SupportEmail(BaseModel):
    subject: str
    body: str
    from_address: EmailStr

class RoutingDecision(BaseModel):
    team: Literal["billing", "technical", "account"]
    rationale: str

# ─────────────────────────────────────────────────────────────────
# Classifier
# ─────────────────────────────────────────────────────────────────

def classify_support_email(email: SupportEmail) -> RoutingDecision:
    """Route a support email to billing, technical, or account team."""
    
    client = Anthropic()
    
    # Define the routing tool
    tools = [
        {
            "name": "route_email",
            "description": "Route a support email to the appropriate team",
            "input_schema": {
                "type": "object",
                "properties": {
                    "team": {
                        "type": "string",
                        "enum": ["billing", "technical", "account"],
                        "description": "The support team to route this email to"
                    },
                    "rationale": {
                        "type": "string",
                        "description": "One-line reason for this routing decision"
                    }
                },
                "required": ["team", "rationale"]
            }
        }
    ]
    
    # Build the prompt
    prompt = f"""You are a support email router. Analyze this customer email and route it to the appropriate team.

Subject: {email.subject}
Body: {email.body}
From: {email.from_address}

Categories:
- billing: payment issues, invoices, pricing, subscription, refunds, cancellations
- technical: bugs, errors, features, integration, API, performance, compatibility
- account: profile, password, access, permissions, settings, deactivation

Use the route_email tool to classify this email. Be precise and consistent."""
    
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=256,
        tools=tools,
        messages=[{"role": "user", "content": prompt}]
    )
    
    # Extract the tool use response
    for block in response.content:
        if block.type == "tool_use":
            return RoutingDecision(
                team=block.input["team"],
                rationale=block.input["rationale"]
            )
    
    # Fallback (shouldn't reach here with valid response)
    raise ValueError("No routing decision generated")

# ─────────────────────────────────────────────────────────────────
# Calling Code
# ─────────────────────────────────────────────────────────────────

# Example: Single email
example_email = SupportEmail(
    subject="Charge on my card - please explain",
    body="I see a $50 charge on my statement from last Tuesday. I only have a free account. What is this?",
    from_address="alice@example.com"
)

decision = classify_support_email(example_email)
print(f"Team: {decision.team}")
print(f"Rationale: {decision.rationale}")
# Output: Team: billing
#         Rationale: Customer inquiring about unexpected charge


# Batch processing for ~1000s/day
def process_email_batch(emails: list[SupportEmail]) -> list[tuple[SupportEmail, RoutingDecision]]:
    """Process multiple emails. For high volume, consider batching API calls."""
    results = []
    for email in emails:
        decision = classify_support_email(email)
        results.append((email, decision))
    return results

# Example batch
batch = [
    SupportEmail(
        subject="Getting 404 errors on API",
        body="My integration script stopped working yesterday. I'm getting 404 responses.",
        from_address="dev@startup.com"
    ),
    SupportEmail(
        subject="How do I update my password?",
        body="I want to change my account password. Where's the setting?",
        from_address="bob@corp.com"
    ),
    SupportEmail(
        subject="Cancel subscription",
        body="Please cancel my account immediately.",
        from_address="cancel@domain.com"
    ),
]

results = process_email_batch(batch)
for email, decision in results:
    print(f"{email.subject:40} → {decision.team:10} ({decision.rationale})")
```

**Key design choices:**

- **Tool use** — Claude returns structured JSON reliably via tool_use blocks, avoiding parsing fragility at scale.
- **Sonnet 3.5** — Fast enough for thousands/day with good accuracy for routing. Swap to Opus if precision is critical.
- **Single client instantiation** — In production, reuse `Anthropic()` across calls to amortize connection overhead.
- **Batch pattern** — For actual volume, spawn concurrent requests (e.g., `asyncio` + `max_concurrent_requests` parameter to the SDK).
- **Fallback categories** — The prompt ties keywords to teams so edge cases land in reasonable buckets (e.g., "cancel" → billing, API errors → technical).

**For production volume:**

1. Use the Anthropic Batch API for thousands/day — 50% cheaper and handles retries.
2. Cache system prompts via prompt caching to reduce input tokens (~90% savings on repeated routing logic).
3. Add telemetry: log team distribution, confidence scores (claude-3-5-sonnet returns low-confidence routing).
4. Test accuracy on a sample of 100–200 emails against manual ground truth before rolling out.