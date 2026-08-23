Here is the complete inline implementation. 

For a volume of a few thousand emails a day, **Claude 3 Haiku** is the most reasonable assumption for the model choice. It is incredibly fast, extremely cheap, and easily capable of simple classification tasks like this.

I've used **Pydantic** for strong typing and used Anthropic's native **Tool Calling** (Forced Tool Choice) to guarantee the output adheres exactly to the `RoutingDecision` schema every time.

```python
import os
from enum import Enum
import anthropic
from pydantic import BaseModel, Field

# ==========================================
# 1. Types
# ==========================================

class Email(BaseModel):
    subject: str
    body: str
    fromAddress: str

class RoutingDestination(str, Enum):
    BILLING = "billing"
    TECHNICAL = "technical"
    ACCOUNT = "account"

class RoutingDecision(BaseModel):
    destination: RoutingDestination = Field(
        description="The team to route the email to."
    )
    rationale: str = Field(
        description="A concise, one-line rationale for the routing decision."
    )


# ==========================================
# 2. Classifier
# ==========================================

class SupportEmailRouter:
    def __init__(self, api_key: str | None = None):
        # Initializes the standard Anthropic client
        self.client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
        )
        # Claude 3 Haiku is ideal for high-volume, low-latency classification
        self.model = "claude-3-haiku-20240307"

    def route(self, email: Email) -> RoutingDecision:
        prompt = (
            f"From: {email.fromAddress}\n"
            f"Subject: {email.subject}\n"
            f"Body:\n{email.body}\n"
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=256,
            temperature=0.0, # 0.0 for deterministic classification
            system="You are an expert customer support routing agent. Analyze the email and route it to the appropriate team.",
            tools=[
                {
                    "name": "record_routing_decision",
                    "description": "Records the final routing decision and rationale into the ticketing system.",
                    # Pydantic automatically generates the exact JSON schema Anthropic requires
                    "input_schema": RoutingDecision.model_json_schema()
                }
            ],
            # Force the model to use our specific tool to guarantee the output structure
            tool_choice={"type": "tool", "name": "record_routing_decision"},
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        # Extract the tool use payload
        for content in response.content:
            if content.type == "tool_use" and content.name == "record_routing_decision":
                return RoutingDecision(**content.input)
                
        raise RuntimeError("Model did not return a routing decision.")


# ==========================================
# 3. Calling Code
# ==========================================

if __name__ == "__main__":
    # Ensure you have your ANTHROPIC_API_KEY set in your environment
    router = SupportEmailRouter()
    
    incoming_email = Email(
        subject="Invoice #4928 double charged",
        body="Hello, I noticed that my credit card was charged twice for this month's subscription. Can you please refund one of the charges?",
        fromAddress="angry.customer@example.com"
    )
    
    print("Evaluating email...")
    decision = router.route(incoming_email)
    
    # Push into your ticketing system
    print("\n--- TICKETING SYSTEM PAYLOAD ---")
    print(f"Team      : {decision.destination.value}")
    print(f"Rationale : {decision.rationale}")
```