"""Client-specific functions for Acme Corp workflows.

Each public function here is available to code steps in workflow.yaml
via the `function` field.
"""


def lookup_order(intent: str, ticket: str) -> dict:
    """Look up order status based on ticket content.

    In production this would call Acme's Order History API.
    """
    return {
        "order_id": "ORD-12345",
        "status": "shipped",
        "shipped_date": "2026-03-10",
        "carrier": "FedEx",
        "tracking": "FX123456789",
    }
