# Postmaster certificate hostname repair

For Chrome NET::ERR_CERT_COMMON_NAME_INVALID at postmaster.justisolve.com, run on the server actually hosting the existing Postmaster backend (loopback port 18870):

```bash
apt-get update
apt-get install -y ansible git
ansible-pull -U https://github.com/olamidebello/postmaster-.git \
  -C main -d /opt/postmaster-https-repair -i localhost, -c local \
  ansible/repair-https.yml
```

This requires the Postmaster application already to be installed and healthy. It does not deploy or modify the African Apps Store server. Domain A/AAAA records must lead to this server and inbound ports 80/443 must be reachable. Set POSTMASTER_TLS_EMAIL to override the default certificate contact.

The playbook checks nginx -T and refuses competing exact hostname declarations outside Postmaster's managed site. Wildcards for unrelated sites are retained. If it stops with a conflicting filename, inspect that file and consolidate only the Postmaster declaration; do not delete a shared virtual host. The script does not guess which other site is safe to remove.

The managed file is /etc/nginx/sites-available/postmaster-postmaster.justisolve.com. A backup is retained before replacement. ACME uses a dedicated webroot, with non-challenge HTTP traffic redirected to HTTPS. The certificate lineage is postmaster-justisolve-com, containing the exact hostname. Certbot is not allowed to rewrite other virtual hosts. Existing valid dedicated TLS routing is retained while renewal is attempted.

Success requires: certificate hostname and validity checks; local SNI trust validation against the system CA store; a 200 Postmaster health response through the HTTPS virtual host; and public DNS/HTTPS health verification. Failures restore the previous managed site and enabled-link state. Newly obtained certificates may remain on disk, but no unrelated certificate is deleted or replaced. Renewal has a validated Nginx reload hook and certbot.timer enabled.

If the upstream proxy/CDN terminates TLS, its edge certificate must also include postmaster.justisolve.com. If public verification fails despite successful local verification, investigate DNS, IPv6 and any upstream proxy rather than bypassing browser certificate warnings.

Sources: https://nginx.org/en/docs/http/server_names.html and https://eff-certbot.readthedocs.io/en/stable/using.html.


## Valid certificate on disk but local SNI mismatch
The strict local TLS check now retries ten times with a two-second interval so that a successful asynchronous Nginx reload can finish replacing its workers. A persistent mismatch is not ignored. Before rollback the playbook saves `/var/lib/postmaster-https-repair/diagnostics.json` (root-only), showing the actual IPv4/IPv6 listener process, served certificate names, expected certificate names, and Nginx listen/server_name/certificate paths. It does not print private key contents. This helps distinguish an address-specific listener, a different TLS process, or an unexpected Nginx instance from reload timing. No unrelated listener is stopped or rewritten automatically.
