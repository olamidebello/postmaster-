# Developer API

All routes are same-origin `/api`. Session writes require the `X-CSRF-Token` returned by login, registration, or `/me`. API tokens use `Authorization: Bearer pm_…` and are hashed at rest. Tokens authorize the issuing user's current workspace role and cannot pay, cancel, modify resources, or administer users.

| Method | Route | Purpose |
|---|---|---|
| GET | /health | Database liveness |
| GET | /catalog | Services and plan features |
| GET | /me | Current identity/workspace |
| GET | /mail | Last 1,000 workspace orders |
| GET | /mail/:id | Scoped order detail |
| POST | /quote | Validated mailing price in USD cents |
| POST | /mail | Create unpaid order; optional Idempotency-Key |
| POST | /mail/:id/pay | Session only; atomically debit wallet |
| POST | /mail/:id/cancel | Session only; eligible cancellation/refund |
| GET | /resources/:kind | Workspace recipients, senders, lists, templates, banks, tickets, integrations |
| POST/PUT/DELETE | /resources/:kind[/:id] | Session and role controlled |
| POST | /documents | Base64 PDF upload, 15 MB maximum |
| GET | /documents/:id | Tenant-authorized PDF bytes |
| POST | /import | Atomic CSV import |
| GET | /export?list=ID | CSV export with formula protection |
| GET | /ledger | Workspace balance movements |
| GET | /audit | Owner/admin activity log |

Example POST `/mail` and `/quote`:

```json
{
  "kind": "letter",
  "body": "Dear {{name}},\nThank you.",
  "service": "first_class",
  "sender": {"name":"Acme","street":"1 Main St","city":"Austin","state":"TX","postal_code":"78701","country":"US"},
  "recipients": [{"name":"Alex","street":"2 Oak St","city":"Dallas","state":"TX","postal_code":"75201","country":"US","custom":{"custom_1":"ABC"}}],
  "color": false,
  "duplex": true,
  "scheduled": "2026-12-01T09:00:00+00:00",
  "description": "Invoice reminder"
}
```

Use `document_id` instead of written content after uploading a PDF through the session-authenticated interface. A check additionally needs an approved `bank_id` and positive integer `amount_cents`. A postcard requires `first_class` and `size` of `4x6` or `6x9`.

Errors: JSON `{"error":"message"}` with HTTP 400/401/403/404/409/410/413/429/503. POST `/mail` returns order ID, unpaid status and quote. Idempotency keys are scoped to workspace and persist for the order's lifetime; reuse returns the original response.

Internal states: `unpaid → scheduled/queued → preparing → on_the_way → tracking_available/delivered`. Scheduling only releases paid orders to `queued`; it never fabricates dispatch or delivery. Eligible failures can be explicitly refunded once. `cancelled` and `refunded` are terminal.
