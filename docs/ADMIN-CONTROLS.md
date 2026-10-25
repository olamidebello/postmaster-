# Super admin keys and tokens

Sign in with a super administrator account, open Platform administration, and select **Keys & tokens**.

- Configure SMTP_HOST, SMTP_PORT, SMTP_FROM, SMTP_USER, SMTP_PASSWORD, STRIPE_SECRET_KEY, and STRIPE_WEBHOOK_SECRET.
- Only configured/not-configured status and source are returned. Values cannot be revealed; enter a replacement to rotate a credential.
- Blank values explicitly disable a setting, overriding an environment value. Updates take effect immediately across workers.
- Credentials are saved atomically in `/var/lib/postmaster/provider-credentials.json`, mode 0600, inside the restricted data directory. This file uses filesystem access protection, not application-level encryption; protect server backups accordingly.
- List all workspace API token metadata and revoke tokens immediately. Token values and hashes are omitted. Issue replacements from the relevant workspace's Settings → Tokens.
- Bearer API tokens cannot use any platform administrator endpoints, even when their owner is a super administrator. Administrative mutations require session authentication and CSRF protection.
- Changes record setting names or token IDs in the platform audit log, never credential values. Saving does not test a provider connection.

## Deploy as root on the Olamidepanel server

```bash
apt-get update
apt-get install -y ansible git
ansible-pull -U https://github.com/olamidebello/postmaster-.git \
  -C main -d /opt/postmaster-bootstrap -i localhost, -c local \
  ansible/admin-controls.yml
```

The existing database and protected credential file are preserved during updates. The playbook verifies application health and the exact HTTPS hostname. DNS must point postmaster.justisolve.com at this server.

To also promote the already-registered, active dobcalldemo@gmail.com account, use `ansible/olamidepanel-admin.yml` instead. That explicit entry point preserves the password and requires signing in again after promotion.
