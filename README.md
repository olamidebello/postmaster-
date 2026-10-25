# Postmaster

A self-hosted digital-to-physical mailing application with a responsive customer portal, persistent tenant-scoped records, a developer API, and super administrator fulfillment and billing tools.

## Run locally

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m app.server init
python -m app.server admin --email admin@example.com
POSTMASTER_INSECURE=1 python -m app.server serve --port 8080
```

Open http://localhost:8080. The administrator command prompts for a password; no default credentials are included. Self-registration creates an isolated Free workspace. Production must use HTTPS and secure cookies; do not set `POSTMASTER_INSECURE=1` in production.

## Deploy on Debian 12+

Point a domain's DNS to the server, allow inbound 80/443, then run as root:

```bash
apt-get update
apt-get install -y ansible git
export POSTMASTER_DOMAIN=mail.your-domain.com
export POSTMASTER_TLS_EMAIL=you@your-domain.com
ansible-pull -U https://github.com/olamidebello/postmaster-.git \
  -C main -d /opt/postmaster-bootstrap -i localhost, -c local \
  ansible/pull-and-deploy.yml
```

Then create the administrator:

```bash
cd /opt/postmaster/repo
sudo -u postmaster env POSTMASTER_DATA=/var/lib/postmaster \
  /opt/postmaster/venv/bin/python -m app.server admin --email you@your-domain.com
```

Set SMTP and optional Stripe credentials in `/etc/postmaster/environment` and restart `postmaster`. Environment files are preserved on subsequent deployments. Service: `postmaster`; minute timer: `postmaster-worker.timer`; app loopback port: `18870`. Re-run the pull command to update. See [operations](docs/OPERATIONS.md).

## Included workflows

- Registration, sign-in/out, SMTP password reset, password changes, TOTP two-factor authentication, workspace switching, deletion requests.
- Owner/admin/sender/viewer permissions, invitations for existing users, revocation, plan seat limits.
- Dashboard, letters/postcards/checks history, filters, detail and PDF preview, service-aware tracking links.
- PDF upload with parsed page counts and plan retention, saved text templates, merge preview, reusable return addresses.
- Single recipients, address-book selection, bulk mailing lists, atomic CSV import and safe CSV export, five custom fields.
- Server-side quote validation, domestic/international limits, print options, scheduling up to 170 days, postcards and verified-bank check preparation.
- Unpaid review, atomic wallet debit, queueing, eligible cancellation/refund, operator-reviewed failed-order refund, transaction receipts.
- Scoped/revocable API tokens, idempotent order submission, activity records, support tickets and operator replies.
- Super admin: workspace plans, verified manual balance credits, suspension/reactivation, bank reference approval, fulfillment queue, source PDF download, audited postal status updates.
- Responsive public product/pricing/industry pages, help, API guide, clearly marked legal drafts, integration setup requests.
- Ansible deployment, systemd/Gunicorn, Nginx/Let's Encrypt, scheduled worker, automated tests and GitHub Actions.

## Operational boundaries — read before launch

This is a working **manual-fulfillment platform**, not a claim that all DocuPost services or external integrations are implemented. No postage is purchased and no checks are issued automatically. Paid orders enter the operator's queue; administrators download source PDFs or text instructions, arrange production with a mailing vendor, and record verified references. Written letters have printable merged PDFs and address covers. Postcard artwork editing, window-envelope imposition and MICR check rendering are not implemented. Checks record instructions and require external verified issuance; the check principal is not deducted from the mailing wallet.

Balances support Stripe hosted card checkout with signature-verified, replay-safe webhook credits when configured, plus audited manual credits. Recurring billing is not implemented. Named integration cards record setup requests; OAuth apps and marketplace add-ons are not implemented. Purchased demographic mailing lists, Picsart, logos on envelopes/checks, postal claims integrations, automatic delivery evidence, and automated provider dispatch remain future work. Subscription prices are not invented. The rates in `app/core.py` are sample operator-configured estimates and must be replaced with actual contracted rates before accepting paid orders.

Legal notices are marked drafts and require operator identity and review. No HIPAA certification or BAA is implied. See the exact [feature coverage matrix](docs/FEATURES.md) and [API](docs/API.md).

## Verify

```bash
python -m unittest discover -s tests -v
node --check app/app.js
ansible-playbook -i localhost, ansible/pull-and-deploy.yml --syntax-check
```

## Optional card funding

Set `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, and an HTTPS `PUBLIC_URL` in the protected environment. Register `/api/payments/webhook` for `checkout.session.completed` and `checkout.session.async_payment_succeeded`. Restart the service. Billing shows hosted card checkout only when both keys are configured. Verify in Stripe test mode before accepting real payments. Credits require a matching stored checkout, paid status, currency, amount, workspace, and verified signature; redirects never grant funds. No live payment was attempted during development.

## Brand identity and artwork

The original envelope-in-flight mark appears in the header, sign-in screen, sidebar, favicon and touch icon. The concept portrait illustrates a digital document becoming a physical delivery and appears in the homepage hero and dashboard. Original PNG assets and final generation prompts are recorded in [the brand guide](docs/BRAND.md).

A deployment wrapper is also available after cloning the repository:

```bash
sudo bash scripts/deploy.sh --domain mail.your-domain.com --email you@your-domain.com
```

The wrapper installs Ansible and pulls `main`; the playbook installs/updates the service, preserves configuration, obtains TLS, and checks health and branded asset delivery. Administrator creation remains the interactive step described above.
