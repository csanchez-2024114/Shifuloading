"""Demo CRM app built with @tool_spec: a reference to copy when adding real apps.

Everything is SIMULATED in memory (resets when the server restarts); nothing real is created or sent.
It exercises prerequisites: orders need a customer_id, obtainable by email OR by listing customers.
"""
import copy
from datetime import date

from langchain_core.tools import BaseTool

from assistant.core.tool_spec import AutoResolve, tool_spec

_SEED_CUSTOMERS = {
    "c-001": {"id": "c-001", "name": "Ana López", "email": "ana@example.com", "city": "Monterrey"},
    "c-002": {"id": "c-002", "name": "Luis Pérez", "email": "luis@example.com", "city": "Guadalajara"},
    "c-003": {"id": "c-003", "name": "María García", "email": "maria@example.com", "city": "CDMX"},
}
_SEED_ORDERS = [
    {"id": "o-1001", "customer_id": "c-002", "product": "Laptop", "quantity": 1, "date": "2026-09-30"},
    {"id": "o-1002", "customer_id": "c-002", "product": "Mouse", "quantity": 2, "date": "2026-10-02"},
]
CUSTOMERS: dict[str, dict] = {}
ORDERS: list[dict] = []


def reset() -> None:
    """Restore the seed data (used by tests)."""
    CUSTOMERS.clear()
    CUSTOMERS.update(copy.deepcopy(_SEED_CUSTOMERS))
    ORDERS[:] = copy.deepcopy(_SEED_ORDERS)


reset()

_GET_CUSTOMER_ID = ["crm_find_customer_by_email", "crm_list_customers"]


@tool_spec(
    app="crm", resource="customer", action="find_by_email",
    summary="Find a CRM customer by their email address and return the customer record (id, name, email, city).",
    when_to_use="You have a customer's email and need their customer_id or details.",
    when_not_to_use="If you only know the name, use crm_list_customers with name_contains.",
    tags=["customer", "client", "lookup", "email", "id"],
    examples=["find the customer with email ana@example.com", "busca al cliente ana@example.com",
              "what is the customer id for luis@example.com"],
)
def crm_find_customer_by_email(email: str) -> dict:
    """Find a customer by email.

    Args:
        email: Exact customer email address.
    """
    found = next((c for c in CUSTOMERS.values() if c["email"].lower() == email.strip().lower()), None)
    return found or {"found": False, "message": f"No customer with email {email}"}


@tool_spec(
    app="crm", resource="customer", action="list",
    summary="List CRM customers (id, name, email), optionally filtered by part of the name.",
    when_to_use="You need a customer_id but only know the customer's name, or the user wants to see customers.",
    when_not_to_use="If you have the exact email, crm_find_customer_by_email is more precise.",
    tags=["customers", "clients", "list", "directory", "search by name"],
    examples=["list all customers", "muéstrame los clientes", "which customers are called Luis"],
)
def crm_list_customers(name_contains: str = "") -> list[dict]:
    """List customers.

    Args:
        name_contains: Optional case-insensitive part of the customer name to filter by.
    """
    q = name_contains.strip().lower()
    return [{k: c[k] for k in ("id", "name", "email")} for c in CUSTOMERS.values() if q in c["name"].lower()]


@tool_spec(
    app="crm", resource="customer", action="get",
    summary="Get the full record of a CRM customer by customer_id.",
    when_to_use="You already have a customer_id and need the customer's details.",
    when_not_to_use="To find a customer without an id use crm_find_customer_by_email or crm_list_customers.",
    tags=["customer", "details", "profile"],
    examples=["show details of customer c-001", "dame los datos del cliente c-002"],
    requires={"customer_id": _GET_CUSTOMER_ID},
)
def crm_get_customer(customer_id: str = "") -> dict:
    """Get a customer.

    Args:
        customer_id: CRM customer id (e.g. c-001).
    """
    return CUSTOMERS.get(customer_id) or {"error": f"Unknown customer_id {customer_id}"}


@tool_spec(
    app="crm", resource="order", action="create",
    summary="Create a new order for a CRM customer (simulated, in memory).",
    when_to_use="The user wants to place or register a new order or purchase for a customer.",
    when_not_to_use="To see existing orders use crm_list_orders.",
    tags=["order", "purchase", "sale", "buy"],
    examples=["place an order of 3 laptops for ana@example.com", "crea un pedido de 2 monitores para Luis",
              "register a purchase of 5 keyboards for customer c-003"],
    requires={"customer_id": _GET_CUSTOMER_ID},
    auto={"customer_id": AutoResolve(source="crm_find_customer_by_email", args={"email": "customer_email"},
                                     field="id")},
    effect="write",
)
def crm_create_order(product: str, quantity: int, customer_id: str = "", customer_email: str = "") -> dict:
    """Create an order.

    Args:
        product: Product name or SKU.
        quantity: Number of units.
        customer_id: CRM customer id. Get it with crm_find_customer_by_email or crm_list_customers.
        customer_email: Customer email; used to resolve customer_id automatically when it is missing.
    """
    if customer_id not in CUSTOMERS:
        return {"error": f"Unknown customer_id {customer_id}"}
    order = {"id": f"o-{1001 + len(ORDERS)}", "customer_id": customer_id, "product": product,
             "quantity": quantity, "date": date.today().isoformat()}
    ORDERS.append(order)
    return {"created": True, "order": order, "simulated": True}


@tool_spec(
    app="crm", resource="order", action="list",
    summary="List the orders of a CRM customer.",
    when_to_use="The user asks what a customer has ordered or bought, or for their order history.",
    when_not_to_use="To create a new order use crm_create_order.",
    tags=["orders", "purchases", "history"],
    examples=["what orders does Luis have", "¿qué pedidos tiene luis@example.com?", "order history of customer c-002"],
    requires={"customer_id": _GET_CUSTOMER_ID},
)
def crm_list_orders(customer_id: str = "") -> list[dict] | dict:
    """List orders of a customer.

    Args:
        customer_id: CRM customer id. Get it with crm_find_customer_by_email or crm_list_customers.
    """
    return [o for o in ORDERS if o["customer_id"] == customer_id]


def crm_tools() -> list[BaseTool]:
    return [crm_find_customer_by_email, crm_list_customers, crm_get_customer, crm_create_order, crm_list_orders]
