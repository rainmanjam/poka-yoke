## Goal Description
Build a reliable, high-throughput email router using the Anthropic SDK. Given a volume of a few thousand emails a day, Claude 3 Haiku is the recommended model—it provides sub-second latency and costs fractions of a cent per email, while being highly accurate for text classification. 

We will use Anthropic's **Tool Use (Function Calling)** to guarantee a structured response containing the target team and a rationale.

## Proposed Implementation
- **Types**: We'll use `pydantic` to define strict schemas for the input (`SupportEmail`) and output (`RoutingDecision`).
- **Classifier**: The `classify_email` function will format the email, provide strict system instructions, and force the model to use a `record_routing_decision` tool. 
- **Calling Code**: A script simulating a queue of emails being processed and routed to a mock ticketing system function.

Here is the complete, inline code:

```python
import os
from typing import Literal
from pydantic import BaseModel, Field
from anthropic import Anthropic

# --- Types ---

class SupportEmail(BaseModel):
    subject: str
    body: str
    from_address: str

class RoutingDecision(BaseModel):
    team: Literal["billing", "technical", "account"] = Field(
        description="The target team for the ticket."
    )
    rationale: str = Field(
        description="One-line rationale for the routing decision."
    )


# --- Classifier ---

def classify_email(client: Anthropic, email: SupportEmail) -> RoutingDecision:
    """Routes an email to the appropriate support team using Claude."""
    
    system_prompt = (
        "You are an expert support email router. Your job is to read an incoming customer email "
        "and route it to the correct team: 'billing', 'technical', or 'account'.\n\n"
        "- billing: for invoices, payments, refunds, and subscription charges.\n"
        "- technical: for bugs, errors, system outages, API issues, and integration problems.\n"
        "- account: for password resets, email changes, login issues, and user management."
    )
    
    prompt = (
        f"From: {email.from_address}\n"
        f"Subject: {email.subject}\n"
        f"Body:\n{email.body}"
    )

    response = client.messages.create(
        # Haiku is ideal for this volume (~3k/day) due to low latency and high cost-efficiency
        model="claude-3-haiku-20240307", 
        max_tokens=256,
        temperature=0.0, # 0.0 for deterministic classification
        system=system_prompt,
        messages=[
            {"role": "user", "content": prompt}
        ],
        tools=[
            {
                "name": "record_routing_decision",
                "description": "Record the team routing decision and rationale.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "team": {
                            "type": "string",
                            "enum": ["billing", "technical", "account"],
                            "description": "The target team."
                        },
                        "rationale": {
                            "type": "string",
                            "description": "One-line rationale for the routing decision."
                        }
                    },
                    "required": ["team", "rationale"]
                }
            }
        ],
        # Force the model to use our specific tool to guarantee structured JSON output
        tool_choice={"type": "tool", "name": "record_routing_decision"}
    )
    
    # Extract the structured data from the tool call
    for block in response.content:
        if block.type == "tool_use" and block.name == "record_routing_decision":
            return RoutingDecision(**block.input)
            
    raise ValueError("Model failed to return a valid routing decision.")


# --- Calling Code ---

def create_ticket(email: SupportEmail, decision: RoutingDecision):
    """Mock integration with a ticketing system (e.g., Zendesk, Jira)."""
    print(f"Creating ticket in [{decision.team.upper()}] queue...")
    print(f"  From: {email.from_address}")
    print(f"  Subject: {email.subject}")
    print(f"  Rationale: {decision.rationale}")
    print("-" * 50)


if __name__ == "__main__":
    # Initialize the Anthropic client (expects ANTHROPIC_API_KEY env var to be set)
    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    # Simulated incoming email queue
    incoming_emails = [
        SupportEmail(
            from_address="user@example.com",
            subject="Can't log in to my dashboard",
            body="Hi, I keep getting a 'wrong password' error even though I just reset it. Help!"
        ),
        SupportEmail(
            from_address="dev@startup.io",
            subject="500 Error on /v1/users endpoint",
            body="We started seeing 500 errors on the users endpoint this morning. Is there an outage?"
        ),
        SupportEmail(
            from_address="finance@corp.com",
            subject="Missing invoice for October",
            body="Please send us the PDF invoice for our October enterprise subscription."
        )
    ]
    
    # Process the queue
    for email in incoming_emails:
        try:
            decision = classify_email(client, email)
            create_ticket(email, decision)
        except Exception as e:
            print(f"Failed to route email from {email.from_address}: {e}")
```