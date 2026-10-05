#!/usr/bin/env bash
# One-time preparation of a fresh Ubuntu 24.04 server (run once, as root or with sudo):
#
#   sudo ./deploy/install-server.sh
#
# Installs Docker from Docker's own package repository, opens only SSH, HTTP and HTTPS
# in the firewall, adds swap on small machines and turns on automatic security updates.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo ./deploy/install-server.sh"; exit 1
fi
. /etc/os-release
if [ "${ID:-}" != "ubuntu" ]; then
  echo "This script is written for Ubuntu (found: ${ID:-unknown}). Install Docker by hand: https://docs.docker.com/engine/install/"
  exit 1
fi

# Oracle Cloud's Ubuntu images ship their own iptables rules (netfilter-persistent) that
# reject everything but SSH; ufw would conflict with them. There, the ports are opened in
# those rules instead (and in the Oracle console's security list - see DEPLOY.md).
ORACLE_RULES=0
if [ -f /etc/iptables/rules.v4 ] && grep -q "REJECT" /etc/iptables/rules.v4; then
  ORACLE_RULES=1
fi

echo "== Docker (official repository)"
apt-get update -y
apt-get install -y ca-certificates curl git unattended-upgrades
[ "$ORACLE_RULES" = 1 ] || apt-get install -y ufw
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
if [ -n "${SUDO_USER:-}" ] && [ "${SUDO_USER}" != "root" ]; then
  usermod -aG docker "$SUDO_USER"
  echo "   $SUDO_USER can use docker after logging out and in again."
fi

echo "== Firewall: SSH, HTTP, HTTPS only"
if [ "$ORACLE_RULES" = 1 ]; then
  # before the image's final REJECT rule, and saved so it survives a reboot
  for rule in "-p tcp --dport 80" "-p tcp --dport 443" "-p udp --dport 443"; do
    # shellcheck disable=SC2086
    iptables -C INPUT $rule -j ACCEPT 2>/dev/null || iptables -I INPUT 1 $rule -j ACCEPT
  done
  netfilter-persistent save
  echo "   Oracle image: ports 80/443 opened in its iptables rules."
  echo "   Also open them in the Oracle console (security list) - docs/DEPLOY.md, Oracle section."
else
  ufw allow OpenSSH
  ufw allow 80/tcp
  ufw allow 443/tcp
  ufw allow 443/udp
  ufw --force enable
fi

echo "== Swap (the web app build needs memory)"
if ! swapon --show | grep -q . && [ "$(free -m | awk '/Mem:/ {print $2}')" -lt 8000 ]; then
  fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo "/swapfile none swap sw 0 0" >> /etc/fstab
  echo "   4 GB swap added"
else
  echo "   not needed"
fi

echo "== Automatic security updates"
dpkg-reconfigure -f noninteractive unattended-upgrades

echo
echo "Done. Docker: $(docker --version)"
echo "Next: ./deploy/make-env.sh   (see DEPLOY.md)"
