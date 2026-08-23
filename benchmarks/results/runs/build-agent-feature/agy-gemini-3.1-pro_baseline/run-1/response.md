Here is the complete inline implementation. 

For a volume of a few thousand emails a day, **Claude 3 Haiku** is the most reasonable assumption here—it is exceptionally fast and cost-effective, which is perfect for high-volume text classification. To guarantee we always receive a valid team and a rationale, we use **Pydantic** for our types and Anthropic's **Forced Tool Use** to strictly coerce the model into returning structured JSON matching our schema.

```python
import os
from typing import Literal
from pydantic import BaseModel, Field
from anthropic import Anthropic

# ==========================================
# 1. The Types
# ==========================================
class RoutingDecision(BaseModel):
    team: Literal["billing", "technical", "account"] = Field(
        description="The target team for this email."
    )
    rationale: str = Field(
        description="A one-line rationale explaining why this team was chosen based on the email content."
    )

# ==========================================
# 2. The Classifier
# ==========================================
class SupportRouter:
    def __init__(self, api_key: str | None = None):
        # Initializes the Anthropic client (automatically falls back to ANTHROPIC_API_KEY environment variable)
        self.client = Anthropic(api_key=api_key)
        
        # Claude 3 Haiku is chosen for this task because it's highly cost-effective and fast,
        # making it ideal for processing thousands of emails a day for a simple routing classification.
        self.model = "claude-3-haiku-20240307"
        
        # We define a tool to force Claude to output strictly according to our Pydantic schema
        self.routing_tool = {
            "name": "route_ticket",
            "description": "Route the ticket to the appropriate team and provide a rationale.",
            "input_schema": RoutingDecision.model_json_schema()
        }

    def route_email(self, from_address: str, subject: str, body: str) -> RoutingDecision:
        prompt = f"""
From: {from_address}
Subject: {subject}
Body:
{body}
"""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=200,
            temperature=0.0, # 0.0 for maximum consistency in classification
            system="You are an expert customer support router. Read the incoming email and route it to exactly one of these teams: 'billing', 'technical', or 'account'.",
            tools=[self.routing_tool],
            # Force the model to use our specific tool to guarantee structured JSON output
            tool_choice={"type": "tool", "name": "route_ticket"},
            messages=[{"role": "user", "content": prompt}]
        )

        # Extract the tool use arguments and parse them into our Pydantic model
        for block in response.content:
            if block.type == "tool_use":
                return RoutingDecision(**block.input)
                
        raise RuntimeError("Failed to generate a routing decision.")


# ==========================================
# 3. The Calling Code
# ==========================================
def mock_ticketing_system_ingest(email_metadata: dict, decision: RoutingDecision):
    """Mocks ingesting the routed result into a downstream ticketing system."""
    print(f"[{decision.team.upper()} QUEUE] New Ticket Created")
    print(f"  Customer : {email_metadata['from_address']}")
    print(f"  Subject  : {email_metadata['subject']}")
    print(f"  Rationale: {decision.rationale}\n")


if __name__ == "__main__":
    # Ensure ANTHROPIC_API_KEY is set in your environment variables
    router = SupportRouter()

    incoming_emails = [
        {
            "from_address": "finance@corp.com",
            "subject": "Invoice #40492 Discrepancy",
            "body": "Hi, we noticed we were charged for 10 seats this month instead of 8. Can you issue a refund for the difference?"
        },
        {
            "from_address": "dev@startup.io",
            "subject": "API 500 Errors on /v2/users",
            "body": "Since yesterday's deployment, our integration is failing. The endpoint returns an Internal Server Error."
        },
        {
            "from_address": "founder@newbiz.com",
            "subject": "Need help adding a new admin",
            "body": "How do I grant admin privileges to my co-founder? I can't find the setting in the dashboard."
        }
    ]

    print("Starting email routing pipeline...\n")
    for email in incoming_emails:
        # 1. Classify the email
        decision = router.route_email(
            from_address=email["from_address"],
            subject=email["subject"],
            body=email["body"]
        )
        
        # 2. Hand off to the ticketing system
        mock_ticketing_system_ingest(email, decision)
```
{"answer":"Here is the complete inline implementation. \n\nFor a volume of a few thousand emails a day, **Claude 3 Haiku** is the most reasonable assumption here—it is exceptionally fast and cost-effective, which is perfect for high-volume text classification. To guarantee we always receive a valid team and a rationale, we use **Pydantic** for our types and Anthropic's **Forced Tool Use** to strictly coerce the model into returning structured JSON matching our schema.\n\n```python\nimport os\nfrom typing import Literal\nfrom pydantic import BaseModel, Field\nfrom anthropic import Anthropic\n\n# ==========================================\n# 1. The Types\n# ==========================================\nclass RoutingDecision(BaseModel):\n    team: Literal[\"billing\", \"technical\", \"account\"] = Field(\n        description=\"The target team for this email.\"\n    )\n    rationale: str = Field(\n        description=\"A one-line rationale explaining why this team was chosen based on the email content.\"\n    )\n\n# ==========================================\n# 2. The Classifier\n# ==========================================\nclass SupportRouter:\n    def __init__(self, api_key: str | None = None):\n        # Initializes the Anthropic client (automatically falls back to ANTHROPIC_API_KEY environment variable)\n        self.client = Anthropic(api_key=api_key)\n        \n        # Claude 3 Haiku is chosen for this task because it's highly cost-effective and fast,\n        # making it ideal for processing thousands of emails a day for a simple routing classification.\n        self.model = \"claude-3-haiku-20240307\"\n        \n        # We define a tool to force Claude to output strictly according to our Pydantic schema\n        self.routing_tool = {\n            \"name\": \"route_ticket\",\n            \"description\": \"Route the ticket to the appropriate team and provide a rationale.\",\n            \"input_schema\": RoutingDecision.model_json_schema()\n        }\n\n    def route_email(self, from_address: str, subject: str, body: str) -\u003e RoutingDecision:\n        prompt = f\"\"\"\nFrom: {from_address}\nSubject: {subject}\nBody:\n{body}\n\"\"\"\n        response = self.client.messages.create(\n            model=self.model,\n            max_tokens=200,\n            temperature=0.0, # 0.0 for maximum consistency in classification\n            system=\"You are an expert customer support router. Read the incoming email and route it to exactly one of these teams: 'billing', 'technical', or 'account'.\",\n            tools=[self.routing_tool],\n            # Force the model to use our specific tool to guarantee structured JSON output\n            tool_choice={\"type\": \"tool\", \"name\": \"route_ticket\"},\n            messages=[{\"role\": \"user\", \"content\": prompt}]\n        )\n\n        # Extract the tool use arguments and parse them into our Pydantic model\n        for block in response.content:\n            if block.type == \"tool_use\":\n                return RoutingDecision(**block.input)\n                \n        raise RuntimeError(\"Failed to generate a routing decision.\")\n\n\n# ==========================================\n# 3. The Calling Code\n# ==========================================\ndef mock_ticketing_system_ingest(email_metadata: dict, decision: RoutingDecision):\n    \"\"\"Mocks ingesting the routed result into a downstream ticketing system.\"\"\"\n    print(f\"[{decision.team.upper()} QUEUE] New Ticket Created\")\n    print(f\"  Customer : {email_metadata['from_address']}\")\n    print(f\"  Subject  : {email_metadata['subject']}\")\n    print(f\"  Rationale: {decision.rationale}\\n\")\n\n\nif __name__ == \"__main__\":\n    # Ensure ANTHROPIC_API_KEY is set in your environment variables\n    router = SupportRouter()\n\n    incoming_emails = [\n        {\n            \"from_address\": \"finance@corp.com\",\n            \"subject\": \"Invoice #40492 Discrepancy\",\n            \"body\": \"Hi, we noticed we were charged for 10 seats this month instead of 8. Can you issue a refund for the difference?\"\n        },\n        {\n            \"from_address\": \"dev@startup.io\",\n            \"subject\": \"API 500 Errors on /v2/users\",\n            \"body\": \"Since yesterday's deployment, our integration is failing. The endpoint returns an Internal Server Error.\"\n        },\n        {\n            \"from_address\": \"founder@newbiz.com\",\n            \"subject\": \"Need help adding a new admin\",\n            \"body\": \"How do I grant admin privileges to my co-founder? I can't find the setting in the dashboard.\"\n        }\n    ]\n\n    print(\"Starting email routing pipeline...\\n\")\n    for email in incoming_emails:\n        # 1. Classify the email\n        decision = router.route_email(\n            from_address=email[\"from_address\"],\n            subject=email[\"subject\"],\n            body=email[\"body\"]\n        )\n        \n        # 2. Hand off to the ticketing system\n        mock_ticketing_system_ingest(email, decision)\n```","toolAction":"Finishing task","toolSummary":"Finish task"}