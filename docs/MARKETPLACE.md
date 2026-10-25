# Marketplace and payment gateways

## Customer navigation

**Marketplace** lists published operator products and services. Workspace owners and administrators review quantity and the final USD total, then pay from their wallet. Purchases have immutable name/price snapshots, workspace-scoped history, order notes and references. Billing contains transaction receipts. Repeated submissions of the same purchase request do not debit twice. Other workspace roles may browse and read orders but cannot spend marketplace funds.

**Billing** supports Stripe hosted checkout, Paystack hosted checkout, and operator-verified manual funding. Both gateways fund the same USD wallet used for mailing and marketplace orders. No client redirect alone grants balance. Paystack customers return to Billing and click **Verify payment** in the pending list; the server checks the provider response and credits at most once. Verification is also available after a dropped browser connection. This is not an automatic Paystack webhook integration.

## Super admin navigation

- **Super admin → Manage marketplace:** add/edit product name, description, category, final unit price and published/hidden visibility; manage paid orders, record processing/completion with evidence notes, refund eligible paid/processing orders to the wallet. Hiding products retains order history. Completed orders cannot be refunded with this workflow.
- **Super admin → Payment gateways:** enable/disable new Stripe and Paystack checkouts and inspect readiness. Disabling new checkout does not prevent verification of outstanding payments while the keys remain available.
- **Super admin → Keys & tokens:** configure STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_ENABLED (true/false), PAYSTACK_SECRET_KEY, PAYSTACK_ENABLED (true/false). Existing SMTP controls remain available. Secrets are never returned to the browser.
- Manual funding remains a verified operator process using Add credit; it is not a bank gateway connection.

The marketplace deployment now publishes eight starter operator services at suggested USD prices. The operator can edit prices, descriptions and visibility before accepting orders and must fulfill purchased services. Prices are proposed storefront prices, not contracted vendor or postal rates. Marketplace does not implement third-party sellers, payouts, subscriptions, automatic tax calculation, stock/shipping, or a digital download entitlement system. Wallet refunds do not refund a Stripe/Paystack card charge.

## Provider setup

Stripe: configure both keys, set STRIPE_ENABLED=true, and register the existing `/api/payments/webhook` for checkout.session.completed and checkout.session.async_payment_succeeded. Signed events are matched to stored wallet checkouts.

Paystack: configure PAYSTACK_SECRET_KEY and PAYSTACK_ENABLED=true. This USD wallet requires a merchant account enabled for USD; no currency conversion is performed. The server uses https://api.paystack.co/transaction/initialize and /transaction/verify/{reference}. Only a success matching the stored reference, amount, currency and customer email is credited. Live provider transactions were not executed during development. Test with your eligible merchant account before launch.

Reference: https://paystack.com/docs/api/transaction/ and https://paystack.com/docs/payments/verify-payments/.

## Deploy on Olamidepanel as root

```bash
apt-get update
apt-get install -y ansible git
ansible-pull -U https://github.com/olamidebello/postmaster-.git \
  -C main -d /opt/postmaster-bootstrap -i localhost, -c local \
  ansible/marketplace.yml
```

The deployment initializes the additional tables without replacing existing records, preserves protected provider configuration, restarts the app, and verifies HTTPS/application health. No credentials are embedded and no new administrator privileges are granted by this entry point.


## Automatically populated starter catalog

| Service | Starter price (USD) |
|---|---:|
| Letter formatting (up to 5 pages) | $9.99 |
| PDF print-readiness review (up to 25 pages) | $14.99 |
| Custom letterhead layout | $29.99 |
| Two-sided postcard design | $49.99 |
| Mailing-list cleanup (up to 500 rows) | $19.99 |
| Mail-merge template setup (up to 5 fields) | $24.99 |
| Campaign setup (up to 1,000 supplied recipients) | $79.99 |
| Developer API onboarding session (up to 60 minutes) | $99.99 |

Prices are independently proposed starter prices for defined operator work; they are not third-party quotations or a measured market average. Printing, postage, purchased address lists and third-party subscriptions are excluded. No deliverability, legal-compliance or automated fulfillment promise is made.

`ansible/marketplace.yml` runs `python -m app.starter_catalog` as the restricted service user. Stable starter IDs and INSERT OR IGNORE prevent duplicate entries and preserve edited prices, descriptions and hidden status. Additional custom products are untouched. Only missing starter IDs are inserted; future recommended-price changes will not overwrite existing listings. Each successful population is audited.

Super admin → Manage marketplace → Populate starter catalog runs the same operation without shell access. New starter entries are immediately published; hide or edit any entry using Edit. Each successful purchase enters the existing operator fulfillment queue under Manage marketplace.
