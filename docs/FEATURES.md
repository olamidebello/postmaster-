# Feature coverage

| Requested area | Working implementation | Remaining work / external dependency |
|---|---|---|
| Public navigation | Products, industries, pricing, account, help, company/legal/API pages | Case studies, careers, locator lookup and final legal content |
| Dashboard | Tenant counts, balance, recent orders | Postal estimates require vendor data |
| Letters | PDF or text, templates, merge preview and printable merged letter PDFs with address covers, address/list selection, return address, print options, review, scheduling, service validation | Flyer editor, window-envelope imposition, sender logos |
| Limits | Server parses PDF pages; 59 simplex/118 duplex; 10 international; 170-day schedule | Contract-specific fulfillment restrictions |
| Postcards | Text/PDF upload, list audiences, 4x6/6x9, First Class, domestic/international validation | Visual two-sided design editor, production stock/printer integration |
| Checks | Premium gate, bank references and manual approval, US-only, amount/memo/number, five-page attachment, instructions review | Automated bank verification, authorization grants per shared bank, MICR printing, actual issuance/funding, logo |
| Address book/lists | CRUD recipients/senders/lists, five fields, CSV import/export, list selection | Purchased consumer/business lists and demographic targeting |
| Tracking/cancellation | Scoped history/details, operator status evidence, USPS link, eligible cancellation/refund | Automatic carrier webhooks, delivery evidence storage, claims automation |
| Account/security | Registration/login, SMTP resets, profile/password, TOTP, deletion requests | Automated deletion fulfillment and recovery codes |
| Team | Exact-email invitations, seats, role enforcement, removal, shared workspace balance/history | Custom granular permission editor, bank-specific access grants |
| Billing | Integer-cent ledger, atomic debit/refund, verified admin credit, optional Stripe hosted checkout with signed webhook credits, text receipts, plan administration | Saved payment methods UI, subscription charging, tax invoices |
| Developer | Hashed tokens, revocation, read/quote/create API, idempotency | Official Zapier/Google Docs apps and OAuth connectors |
| Integrations | Honest request/status catalog for named integrations | Live Clio/FileVine/HubSpot/QBO/Xero/Google Docs connectors |
| Retention | 90-day Free; configurable paid 1–1,095 days; preview expiry worker | Backup retention and object storage lifecycle policy |
| Support | Tickets, admin reply, FAQ, account deletion/plan/funds requests | Priority SLAs, external email notifications, signed BAA |
| Enterprise/admin | Tenant plans, seats/roles, audit, user suspension, credits, verification, fulfillment | SSO, dedicated support operations and expedited vendor dispatch |
| Deployment | Ansible pull, virtualenv, service hardening, Nginx/TLS, minute worker, CI | Production server/domain and real provider credentials |
