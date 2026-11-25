#!/bin/bash
# Self-signed TLS cert for the HUD. Add your hostnames/IPs to the SAN list.
#   scripts/make-certs.sh              # auto-detect the LAN IP
#   scripts/make-certs.sh 192.168.1.10 # explicit IP
cd "$(dirname "$0")/.." || exit 1
mkdir -p certs

detect_ip() {
  local ip="${1:-}"
  [ -n "$ip" ] && { printf '%s\n' "$ip"; return; }
  ip="$(ipconfig getifaddr en0 2>/dev/null)"                       # macOS Wi-Fi
  [ -n "$ip" ] || ip="$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -vE '^(127\.|::|$)' | head -n1)"
  [ -n "$ip" ] || ip="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}')"
  [ -n "$ip" ] || ip="127.0.0.1"
  printf '%s\n' "$ip"
}

HOST_IP="$(detect_ip "${1:-}")"
openssl req -x509 -newkey rsa:2048 -keyout certs/key.pem -out certs/cert.pem -days 825 -nodes \
  -subj "/CN=Mia HUD" \
  -addext "subjectAltName=DNS:mia.local,DNS:mia,DNS:localhost,IP:$HOST_IP"
cp certs/cert.pem hud/mia.cer   # downloadable from the HUD for phones
echo "cert created for IP $HOST_IP — trust certs/cert.pem on your devices"
