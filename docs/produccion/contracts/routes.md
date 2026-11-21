# Route, job, and event inventory

- **Contract:** Route / job / event inventory (server surface)
- **Version:** 1.0
- **Owner:** D2 Contracts — Pro domain owner
- **Consumers:** I1, I2, I3, M1, M2, M3, M4, M5, M6, I4, G1, G2
- **Scope:** `server/main.py` (all routes), `server/payments.py`, `server/pey.py`, `server/db.py`, `server/reports.py`

## Routes

| Method | Path | Purpose |
| --- | --- | --- |
| GET | /api/health | Liveness/readiness: DB check, demo/live mode, peyConfigured |
| GET | /api/bootstrap | App bootstrap: store profile, active employees, products, demoMode |
| GET | /api/store/profile | Store name, business type, owner name |
| PUT | /api/store/profile | Update store profile (owner) |
| POST | /api/store/photo | Upload store photo as data URL (owner, ≤5 MB) |
| GET | /api/store/photo | Serve store photo (404 if absent) |
| GET | /api/employees | List employees (owner) |
| PATCH | /api/employees/{employee_id} | Update employee name/nickname/active/permissions (owner) |
| POST | /api/employees/invites | Create employee invite → token, employeeId, url (owner) |
| GET | /api/employees/invites/{token} | Read invite (404 if expired, 410 if accepted) |
| POST | /api/employees/invites/{token}/accept | Accept invite, activate employee |
| DELETE | /api/employees/invites/{token} | Revoke a pending invite (owner) |
| GET | /api/inventory | Inventory items with value + last-updated + total value |
| POST | /api/inventory/set | Set absolute stock (owner/can_inventory) |
| POST | /api/inventory/voice | Interpret a count phrase (read-only, no write) |
| GET | /api/catalog | List/search catalog (q/category/kind/limit/offset) |
| POST | /api/catalog | Create catalog item (owner) |
| PATCH | /api/catalog/{product_id} | Update catalog item (owner) |
| DELETE | /api/catalog/{product_id} | Delete item (owner; 409 if it has sales/movements) |
| POST | /api/catalog/templates/apply | Apply a business-type template (owner; empty store only) |
| GET | /api/tasks | List day tasks (owner: all; employee: assigned only) |
| PATCH | /api/tasks/{task_id} | Assign/activate/retitle a task (owner) |
| POST | /api/expenses | Create an expense (any active employee) |
| POST | /api/expenses/voice | Interpret an expense phrase (read-only, no write) |
| GET | /api/expenses | List expenses + today's total (owner) |
| POST | /api/cart/parse | Parse free text into cart items (prices from DB) |
| POST | /api/barcode/lookup | Resolve a barcode to a product |
| POST | /api/barcode/link | Link a barcode to a product |
| POST | /api/sales | Create a sale (cash/fiado/pey); PEY creates a QR with failure paths |
| GET | /api/sales/{sale_id} | Read a sale; reconciles pending PEY against pey |
| POST | /api/sales/{sale_id}/cancel | Cancel a sale (restores inventory if it was paid) |
| GET | /api/reports/today | Today's report (owner) |
| GET | /api/fiado/customers | List fiado customers |
| POST | /api/fiado/customers | Create a fiado customer |
| GET | /api/fiado/customers/{customer_id} | Customer with balance + entries |
| GET | /api/fiado/customers/{customer_id}/entries | Customer entries (owner/canFiado) |
| POST | /api/fiado/customers/{customer_id}/abono | Register an abono (payment) |
| POST | /api/inventory/adjust | Adjust stock by delta (owner/can_inventory) |
| POST | /api/support/tickets | Create a support ticket |
| GET | /api/support/tickets | List support tickets (owner) |
| PATCH | /api/support/tickets/{ticket_id} | Resolve/reopen a ticket (owner) |
| POST | /api/console/login | PIN login for the owner console |
| GET | /api/console/summary | Console dashboard summary (X-Owner-Pin) |
| GET | /api/console/sales | Recent sales (X-Owner-Pin) |
| GET | /api/console/pending | Pending/por_conciliar/failed sales (X-Owner-Pin) |
| GET | /api/console/inventory | Product list (X-Owner-Pin) |
| GET | /api/console/webhooks | Recent webhook events (X-Owner-Pin) |
| GET | /api/console/fiado | Fiado customers + total outstanding (X-Owner-Pin) |
| GET | /api/console/fiado/{customer_id} | Fiado customer + entries (X-Owner-Pin) |
| POST | /api/webhooks/pey | PEY webhook alias (same handler as /webhooks/pey) |
| POST | /webhooks/pey | PEY webhook: signed `codi.qr.payment_received` |
| GET | /console | Serve the owner console HTML |
| GET | /console/ | Redirect to /console |
| GET | /invite/{token} | Employee invite deep-link HTML |
| GET | /.well-known/assetlinks.json | Android App Links declaration |
| GET | / | Redirect to /console |

## Background jobs

None. The server is a single-process FastAPI + SQLite application with one connection per request. There are no scheduled tasks, queue workers, or asyncio background loops. The only startup work is the lifespan hook: `initialize_db` (schema + additive migrations + seed) and `PeyClient` instantiation; shutdown closes the `PeyClient`.

## Durable events

| Event | Trigger | Persistence |
| --- | --- | --- |
| PEY webhook receipt | `POST /webhooks/pey` (`codi.qr.payment_received`, Standard-Webhooks HMAC) | `webhook_events` (PK `webhook_id`) for dedup, then `apply_payment` |
| Payment application | `apply_payment` (webhook or reconciliation) | `payments` (PK `tx_id`, `applied` flag) |
| Inventory movement | sale, cancel, set, adjust | `inventory_movements` (delta, reason, sale_id, employee_id) |
| Fiado movement | fiado sale (charge) or abono (payment) | `fiado_entries` (kind `charge`/`payment`) |
| PEY QR creation (outbound) | `POST /api/sales` for `paymentMethod=pey` | `PeyClient.create_qr` → `sales.pey_qr_id` |
| PEY reconciliation (outbound) | `GET /api/sales/{id}`, cancel `pendingOnly` | `PeyClient.qr_transactions` → `apply_payment` |

## Notes

- `apply_payment` in `server/payments.py` is the only place a sale transitions to `paid_pey` (see `contracts/banking.md`).
- All routes are single-tenant (demo `STORE_ID = "tiendita-esquina"`); production replaces the simulated `X-Employee-Id` / `X-Owner-Pin` with verified identity + `app.tenant_id` per `contracts/tenancy.md`.
- `server/catalog_templates.py` is data-only (no routes); `server/parser.py`, `server/serializers.py`, and `server/reports.py` are helpers.
