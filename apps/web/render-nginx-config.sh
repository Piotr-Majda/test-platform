#!/bin/sh
set -eu

dns_resolver="$(awk '/^nameserver[[:space:]]+/ { print $2; exit }' /etc/resolv.conf)"
if [ -z "$dns_resolver" ]; then
    echo "No DNS resolver found in /etc/resolv.conf" >&2
    exit 1
fi

# nginx requires brackets around an IPv6 resolver address.
case "$dns_resolver" in
    *:*) dns_resolver="[$dns_resolver]" ;;
esac

if [ -n "${API_UPSTREAM_HOST:-}" ]; then
    api_host="$API_UPSTREAM_HOST"
elif [ -n "${RAILWAY_ENVIRONMENT_ID:-}" ]; then
    api_host="api.railway.internal"
else
    api_host="api"
fi
api_port="${API_UPSTREAM_PORT:-8001}"

case "$api_host" in
    *[!A-Za-z0-9._-]*) echo "Invalid API_UPSTREAM_HOST" >&2; exit 1 ;;
esac
case "$api_port" in
    ''|*[!0-9]*) echo "Invalid API_UPSTREAM_PORT" >&2; exit 1 ;;
esac

sed \
    -e "s|__DNS_RESOLVER__|$dns_resolver|g" \
    -e "s|__API_UPSTREAM__|$api_host:$api_port|g" \
    /opt/test-platform/nginx.conf.template \
    > /etc/nginx/conf.d/default.conf

echo "Configured API upstream: $api_host:$api_port"
