# Odoo Invoice — Gold Tier Skill

Create, list, or manage invoices in Odoo ERP via the MCP server.

## Usage

```
/odoo-invoice create "Client Name" <amount> "<description>"
/odoo-invoice list
/odoo-invoice balance
```

Examples:
```
/odoo-invoice create "Acme Corp" 1500 "AI consulting services - March 2026"
/odoo-invoice list
/odoo-invoice balance
```

## Instructions

### Create Invoice

1. Parse the arguments: client name, amount, description.
2. Use the `odoo_list_partners` MCP tool to find the client's partner ID.
   - If client not found: ask user to confirm creating a new partner.
3. Use the `odoo_create_invoice` MCP tool:
   ```
   partner_id: <ID>
   amount: <amount>
   description: <description>
   ```
4. Save a record to `AI_Employee_Vault/Needs_Action/INVOICE_<client>_<date>.md` for tracking.
5. Log to `AI_Employee_Vault/Logs/YYYY-MM-DD.log`.
6. Report: "Invoice created for <client>: $<amount> — Invoice #<ID>"

### List Invoices

1. Use `odoo_list_invoices` MCP tool.
2. Display a table:
   ```
   Recent Invoices
   # | Client      | Amount  | Status  | Date
   --|-------------|---------|---------|----------
   1 | Acme Corp   | $1,500  | Draft   | 2026-03-10
   2 | Beta LLC    | $800    | Paid    | 2026-03-05
   ```

### Account Balance

1. Use `odoo_get_balance` MCP tool.
2. Display current balance and recent transactions.

## Odoo Setup

Odoo must be running before using these commands:
```bash
# Start Odoo + PostgreSQL
docker compose up -d

# Verify MCP connection
python mcp_server/odoo_mcp.py --test

# Open Odoo dashboard
# http://localhost:8069
```

## Available MCP Tools

| Tool                  | Description                    |
|-----------------------|--------------------------------|
| `odoo_list_partners`  | List all clients/partners      |
| `odoo_create_invoice` | Create a new invoice           |
| `odoo_list_invoices`  | List recent invoices           |
| `odoo_get_balance`    | Get current account balance    |
| `odoo_create_expense` | Log a business expense         |

## Approval Required

Creating invoices and expenses are logged automatically but **do not require human approval** — they are accounting actions with audit trails in Odoo.

Payments > $500 to new vendors always require manual approval per `Company_Handbook.md`.
