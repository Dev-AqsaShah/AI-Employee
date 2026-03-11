"""
odoo_mcp.py — Odoo MCP Server for AI Employee (Gold Tier)

Exposes Odoo accounting operations as MCP tools via JSON-RPC.

Provides tools:
  - odoo_list_partners      List customers/vendors
  - odoo_create_invoice     Create draft customer invoice
  - odoo_list_invoices      List invoices with filters
  - odoo_get_invoice        Get invoice details
  - odoo_confirm_invoice    Confirm (validate) a draft invoice
  - odoo_list_products      List products/services
  - odoo_get_balance        Get account balance summary
  - odoo_create_expense     Log a business expense

Setup:
  1. docker compose up -d
  2. Open http://localhost:8069 → Create database → Install Accounting
  3. Settings → Technical → Users → Create API user
  4. Set in .env:
       ODOO_URL=http://localhost:8069
       ODOO_DB=odoo
       ODOO_USER=admin
       ODOO_PASSWORD=admin

Usage:
    python mcp_server/odoo_mcp.py
"""

from __future__ import annotations

import os
import sys
import json
import logging
import xmlrpc.client
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [OdooMCP] %(levelname)s: %(message)s",
)
logger = logging.getLogger("OdooMCP")

# ── Config ──────────────────────────────────────────────────────────────────────
ODOO_URL      = os.getenv("ODOO_URL", "http://localhost:8069")
ODOO_DB       = os.getenv("ODOO_DB", "odoo")
ODOO_USER     = os.getenv("ODOO_USER", "admin")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD", "admin")


# ── Odoo Client ─────────────────────────────────────────────────────────────────

class OdooClient:
    """Thin wrapper around Odoo XML-RPC API."""

    def __init__(self):
        self.url      = ODOO_URL
        self.db       = ODOO_DB
        self.username = ODOO_USER
        self.password = ODOO_PASSWORD
        self.uid: Optional[int] = None

        self._common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self._models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")

    def authenticate(self) -> int:
        """Authenticate and return user ID."""
        if self.uid:
            return self.uid
        self.uid = self._common.authenticate(self.db, self.username, self.password, {})
        if not self.uid:
            raise ConnectionError(
                f"Odoo auth failed. Check ODOO_URL/DB/USER/PASSWORD in .env. "
                f"Is Odoo running? docker compose up -d"
            )
        logger.info(f"Odoo authenticated: uid={self.uid}")
        return self.uid

    def execute(self, model: str, method: str, *args, **kwargs):
        uid = self.authenticate()
        return self._models.execute_kw(
            self.db, uid, self.password,
            model, method, list(args), kwargs
        )

    def search_read(self, model: str, domain: list, fields: list, limit: int = 50) -> list:
        return self.execute(model, "search_read", domain, fields=fields, limit=limit)

    def create(self, model: str, values: dict) -> int:
        return self.execute(model, "create", values)

    def write(self, model: str, ids: list, values: dict) -> bool:
        return self.execute(model, "write", ids, values)

    def call(self, model: str, method: str, ids: list) -> bool:
        return self.execute(model, method, ids)


# Global client instance
_client: Optional[OdooClient] = None

def get_client() -> OdooClient:
    global _client
    if _client is None:
        _client = OdooClient()
    return _client


# ── MCP Tool Handlers ───────────────────────────────────────────────────────────

def odoo_list_partners(params: dict) -> dict:
    """List customers or vendors from Odoo."""
    client  = get_client()
    filter_ = params.get("filter", "customer")   # customer | vendor | all
    limit   = int(params.get("limit", 20))

    domain = []
    if filter_ == "customer":
        domain = [("customer_rank", ">", 0)]
    elif filter_ == "vendor":
        domain = [("supplier_rank", ">", 0)]

    try:
        records = client.search_read(
            "res.partner", domain,
            ["id", "name", "email", "phone", "customer_rank", "supplier_rank"],
            limit=limit,
        )
        return {
            "status": "success",
            "count": len(records),
            "partners": records,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def odoo_create_invoice(params: dict) -> dict:
    """Create a draft customer invoice in Odoo."""
    client = get_client()

    partner_name = params.get("partner_name", "")
    partner_id   = params.get("partner_id")
    lines        = params.get("lines", [])   # [{name, qty, price_unit}]
    currency     = params.get("currency", "USD")

    if not partner_id and not partner_name:
        return {"status": "error", "message": "Provide partner_id or partner_name"}

    try:
        # Resolve partner by name if ID not provided
        if not partner_id:
            matches = client.search_read(
                "res.partner",
                [("name", "ilike", partner_name)],
                ["id", "name"], limit=1,
            )
            if not matches:
                return {"status": "error", "message": f"Partner '{partner_name}' not found"}
            partner_id = matches[0]["id"]

        # Build invoice lines
        invoice_lines = []
        for line in lines:
            invoice_lines.append((0, 0, {
                "name":       line.get("name", "Service"),
                "quantity":   float(line.get("qty", 1)),
                "price_unit": float(line.get("price_unit", 0)),
            }))

        invoice_vals = {
            "move_type":      "out_invoice",
            "partner_id":     partner_id,
            "invoice_line_ids": invoice_lines,
        }

        invoice_id = client.create("account.move", invoice_vals)
        logger.info(f"Created invoice id={invoice_id} for partner_id={partner_id}")

        return {
            "status": "success",
            "invoice_id": invoice_id,
            "message": f"Draft invoice #{invoice_id} created. Use odoo_confirm_invoice to validate.",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def odoo_list_invoices(params: dict) -> dict:
    """List invoices with optional status filter."""
    client  = get_client()
    status  = params.get("status", "all")   # all | draft | posted | paid
    limit   = int(params.get("limit", 20))

    domain = [("move_type", "in", ["out_invoice", "out_refund"])]
    if status == "draft":
        domain.append(("state", "=", "draft"))
    elif status == "posted":
        domain.append(("state", "=", "posted"))
    elif status == "paid":
        domain.append(("payment_state", "=", "paid"))

    try:
        records = client.search_read(
            "account.move", domain,
            ["id", "name", "partner_id", "amount_total", "state",
             "payment_state", "invoice_date", "invoice_date_due"],
            limit=limit,
        )
        return {
            "status": "success",
            "count": len(records),
            "invoices": records,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def odoo_get_invoice(params: dict) -> dict:
    """Get details for a specific invoice."""
    client     = get_client()
    invoice_id = params.get("invoice_id")
    if not invoice_id:
        return {"status": "error", "message": "invoice_id is required"}

    try:
        records = client.search_read(
            "account.move",
            [("id", "=", int(invoice_id))],
            ["id", "name", "partner_id", "invoice_line_ids", "amount_total",
             "amount_tax", "state", "payment_state", "invoice_date",
             "invoice_date_due", "ref"],
        )
        if not records:
            return {"status": "error", "message": f"Invoice {invoice_id} not found"}

        inv = records[0]
        # Get line details
        lines = client.search_read(
            "account.move.line",
            [("move_id", "=", int(invoice_id)), ("display_type", "=", "product")],
            ["name", "quantity", "price_unit", "price_subtotal"],
        )
        inv["lines"] = lines
        return {"status": "success", "invoice": inv}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def odoo_confirm_invoice(params: dict) -> dict:
    """Confirm (validate/post) a draft invoice."""
    client     = get_client()
    invoice_id = params.get("invoice_id")
    if not invoice_id:
        return {"status": "error", "message": "invoice_id is required"}

    try:
        client.call("account.move", "action_post", [int(invoice_id)])
        return {
            "status": "success",
            "message": f"Invoice {invoice_id} confirmed and posted.",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def odoo_list_products(params: dict) -> dict:
    """List products/services."""
    client = get_client()
    limit  = int(params.get("limit", 30))
    type_  = params.get("type", "all")   # all | service | consu | product

    domain = []
    if type_ != "all":
        domain = [("type", "=", type_)]

    try:
        records = client.search_read(
            "product.template", domain,
            ["id", "name", "type", "list_price", "standard_price"],
            limit=limit,
        )
        return {"status": "success", "count": len(records), "products": records}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def odoo_get_balance(params: dict) -> dict:
    """Get a simplified account balance summary."""
    client = get_client()

    try:
        # Query key account types
        accounts = client.search_read(
            "account.account",
            [("account_type", "in", [
                "asset_receivable", "liability_payable",
                "asset_cash", "asset_bank",
            ])],
            ["id", "name", "code", "account_type", "current_balance"],
            limit=50,
        )

        summary = {
            "receivable": [],
            "payable":    [],
            "cash_bank":  [],
        }

        for acc in accounts:
            t = acc.get("account_type", "")
            if t == "asset_receivable":
                summary["receivable"].append(acc)
            elif t == "liability_payable":
                summary["payable"].append(acc)
            elif t in ("asset_cash", "asset_bank"):
                summary["cash_bank"].append(acc)

        return {"status": "success", "summary": summary}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def odoo_create_expense(params: dict) -> dict:
    """Log a business expense (vendor bill)."""
    client       = get_client()
    vendor_name  = params.get("vendor_name", "Unknown Vendor")
    amount       = float(params.get("amount", 0))
    description  = params.get("description", "Business expense")
    date         = params.get("date", "")

    try:
        # Find or create vendor
        matches = client.search_read(
            "res.partner",
            [("name", "ilike", vendor_name)],
            ["id", "name"], limit=1,
        )
        if matches:
            partner_id = matches[0]["id"]
        else:
            partner_id = client.create("res.partner", {
                "name": vendor_name,
                "supplier_rank": 1,
            })

        bill_vals = {
            "move_type":  "in_invoice",
            "partner_id": partner_id,
            "invoice_line_ids": [(0, 0, {
                "name":       description,
                "quantity":   1,
                "price_unit": amount,
            })],
        }
        if date:
            bill_vals["invoice_date"] = date

        bill_id = client.create("account.move", bill_vals)
        return {
            "status": "success",
            "bill_id": bill_id,
            "message": f"Expense logged as vendor bill #{bill_id} for {vendor_name}: ${amount}",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── MCP Protocol ─────────────────────────────────────────────────────────────────

TOOLS = {
    "odoo_list_partners": {
        "fn": odoo_list_partners,
        "description": "List customers or vendors from Odoo. Use filter='customer', 'vendor', or 'all'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filter": {"type": "string", "enum": ["customer", "vendor", "all"], "default": "customer"},
                "limit":  {"type": "integer", "default": 20},
            },
        },
    },
    "odoo_create_invoice": {
        "fn": odoo_create_invoice,
        "description": "Create a draft customer invoice in Odoo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "partner_name": {"type": "string", "description": "Customer name (used to look up partner_id)"},
                "partner_id":   {"type": "integer", "description": "Odoo partner ID (faster, use instead of partner_name)"},
                "lines": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name":       {"type": "string"},
                            "qty":        {"type": "number"},
                            "price_unit": {"type": "number"},
                        },
                    },
                    "description": "Invoice line items",
                },
            },
        },
    },
    "odoo_list_invoices": {
        "fn": odoo_list_invoices,
        "description": "List customer invoices. Filter by status: all, draft, posted, paid.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["all", "draft", "posted", "paid"], "default": "all"},
                "limit":  {"type": "integer", "default": 20},
            },
        },
    },
    "odoo_get_invoice": {
        "fn": odoo_get_invoice,
        "description": "Get full details of a specific invoice by ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_id": {"type": "integer"},
            },
            "required": ["invoice_id"],
        },
    },
    "odoo_confirm_invoice": {
        "fn": odoo_confirm_invoice,
        "description": "Confirm (post/validate) a draft invoice so it becomes official.",
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_id": {"type": "integer"},
            },
            "required": ["invoice_id"],
        },
    },
    "odoo_list_products": {
        "fn": odoo_list_products,
        "description": "List products or services from Odoo catalog.",
        "input_schema": {
            "type": "object",
            "properties": {
                "type":  {"type": "string", "enum": ["all", "service", "consu", "product"], "default": "all"},
                "limit": {"type": "integer", "default": 30},
            },
        },
    },
    "odoo_get_balance": {
        "fn": odoo_get_balance,
        "description": "Get account balance summary: receivables, payables, cash & bank.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    "odoo_create_expense": {
        "fn": odoo_create_expense,
        "description": "Log a business expense as a vendor bill in Odoo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "vendor_name":  {"type": "string", "description": "Vendor/supplier name"},
                "amount":       {"type": "number", "description": "Expense amount"},
                "description":  {"type": "string", "description": "What the expense is for"},
                "date":         {"type": "string", "description": "Date (YYYY-MM-DD), defaults to today"},
            },
            "required": ["amount"],
        },
    },
}


def handle_request(request: dict) -> dict:
    method = request.get("method", "")
    req_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "ai-employee-odoo", "version": "1.0.0"},
            },
        }

    if method == "tools/list":
        tools_list = [
            {
                "name": name,
                "description": info["description"],
                "inputSchema": info["input_schema"],
            }
            for name, info in TOOLS.items()
        ]
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools_list}}

    if method == "tools/call":
        params  = request.get("params", {})
        name    = params.get("name", "")
        inputs  = params.get("arguments", {})

        if name not in TOOLS:
            return {
                "jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {name}"},
            }

        try:
            result = TOOLS[name]["fn"](inputs)
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                    "isError": result.get("status") == "error",
                },
            }
        except Exception as e:
            logger.exception(f"Tool {name} failed")
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps({"status": "error", "message": str(e)})}],
                    "isError": True,
                },
            }

    return {
        "jsonrpc": "2.0", "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def run_server():
    logger.info(f"Odoo MCP server starting — connecting to {ODOO_URL}")
    logger.info("Waiting for requests on stdin...")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request  = json.loads(line)
            response = handle_request(request)
            print(json.dumps(response), flush=True)
        except json.JSONDecodeError as e:
            error = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {e}"}}
            print(json.dumps(error), flush=True)
        except Exception as e:
            logger.exception("Unhandled error")
            error = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}}
            print(json.dumps(error), flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        # Quick connection test
        try:
            client = OdooClient()
            uid    = client.authenticate()
            print(f"Odoo connection OK — uid={uid}")
        except Exception as e:
            print(f"Odoo connection FAILED: {e}")
            print("Make sure Odoo is running: docker compose up -d")
            sys.exit(1)
    else:
        run_server()
