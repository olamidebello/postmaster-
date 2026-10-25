#!/usr/bin/env bash
# Install/update Postmaster on Debian. Run as root with --domain and --email.
set -euo pipefail
postmaster_domain="${POSTMASTER_DOMAIN:-}"
postmaster_contact="${POSTMASTER_TLS_EMAIL:-}"
while (($#)); do
  case "$1" in
    --domain) postmaster_domain="${2:?Missing domain}"; shift 2 ;;
    --email) postmaster_contact="${2:?Missing certificate contact email}"; shift 2 ;;
    *) echo "Usage: sudo bash scripts/deploy.sh --domain mail.example.com --email you@example.com" >&2; exit 2 ;;
  esac
done
[[ $EUID -eq 0 ]] || { echo 'Run as root or with sudo.' >&2; exit 1; }
[[ $postmaster_domain =~ ^[a-z0-9][a-z0-9.-]*[a-z0-9]$ && $postmaster_domain == *.* && $postmaster_contact == *@* ]] || {
  echo 'Supply --domain and --email, and point the domain DNS to this server first.' >&2; exit 2;
}
export POSTMASTER_DOMAIN="$postmaster_domain"
export POSTMASTER_TLS_EMAIL="$postmaster_contact"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ansible git sudo
exec ansible-pull -U https://github.com/olamidebello/postmaster-.git \
  -C main -d /opt/postmaster-bootstrap -i localhost, -c local \
  ansible/pull-and-deploy.yml
