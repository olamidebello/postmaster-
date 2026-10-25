# Operator runbook

1. Set DNS and deploy. Create a super administrator with the local CLI. There is no unauthenticated admin bootstrap endpoint or default password.
2. Configure SMTP (STARTTLS required), operator identity/legal notices, real mailing rates in `app/core.py`, subscription pricing, approved fulfillment arrangements, and payment instructions before opening registration publicly.
3. Independently verify bank authority and business eligibility with the bank/check vendor. Store only last four digits and vendor references. Approval is an operator attestation, not automated verification. Do not upload raw financial credentials to notes.
4. Credit workspace balances only after verified payment; record payment reference. Set plans only after subscription agreement. Optional Stripe hosted top-ups are available when both Stripe credentials and signed webhook delivery are configured; recurring billing is not connected.
5. Paid queue → review source documents and instructions → prepare printing → record real handoff reference → record tracking and delivery only with evidence. First Class/Standard letters may have no trackable USPS identifier. If not fulfilled, mark failed and explicitly refund mailing fee. Check principal is handled by an external bank/vendor, never by wallet credit.
6. Review tickets in Super admin and answer them there. No automatic email notifications are sent for tickets. Password reset requires SMTP. Invitation tokens are shared manually and only accepted by the exact registered email.
7. `journalctl -u postmaster -n 100`; `systemctl status postmaster-worker.timer`; `curl http://127.0.0.1:18870/api/health`; `nginx -t`. Certbot manages renewal.
8. Back up `/var/lib/postmaster` and `/etc/postmaster/environment` to encrypted off-host storage. Use SQLite's backup API or stop services while copying; copying only the database without its WAL while running is unsafe. Test restoration and retention behavior. Backups contain private documents and are not expired by the preview worker.
9. To restore: stop web service and timer; restore database and documents together; set ownership `postmaster:postmaster` and restrictive permissions; start services and verify tenant isolation and source PDF access.
10. Plan capacity for SQLite and local disk. Two web workers are configured. Use PostgreSQL/object storage and a durable job system before larger-scale or multi-host operation. In-process auth throttling is supplemental; enforce reverse-proxy rate limits for public deployment. The app binds to loopback; do not expose Gunicorn directly.

## Security notes

Passwords use salted scrypt; session/API/reset/invitation tokens are hashed; sessions expire in 12 hours. Cookies are HttpOnly/SameSite/Secure. CSRF is required on session mutations. SQL is parameterized; UI data is escaped; CSP restricts resources. All regular records are tenant-scoped and roles are checked server side. Admin downloads and fulfillment edits are audited. Store SMTP secrets only in protected environment configuration.

The application intentionally does not delete accounts irreversibly: deletion requests enter the support queue for operator review and implementation of applicable retention. No protected-health-information processing agreement or compliance certification is bundled. No self-service TOTP recovery codes are implemented; after identity verification the operator can reset 2FA using a controlled database maintenance process.

Known implementation limits and feature coverage are explicit in FEATURES.md. Do not describe this version as fully equivalent to DocuPost or automatically connected to USPS, banks, card networks, or the named SaaS integrations.
