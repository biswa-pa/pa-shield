#!/bin/sh
# Writes /cfg/config.yaml for netbird-server. Secrets are created once and kept
# in /cfg/secrets.env; the rest follows PUBLIC_URL, so changing it just works.
set -eu
: "${PUBLIC_URL:?PUBLIC_URL is required}"
PUBLIC_URL="${PUBLIC_URL%/}"
if [ ! -f /cfg/secrets.env ]; then
  {
    echo "AUTH_SECRET=$(head -c 32 /dev/urandom | base64 | tr -d '\n')"
    echo "STORE_KEY=$(head -c 32 /dev/urandom | base64 | tr -d '\n')"
  } > /cfg/secrets.env
  chmod 600 /cfg/secrets.env
fi
# shellcheck disable=SC1091
. /cfg/secrets.env
cat > /cfg/config.yaml <<YAML
server:
  listenAddress: ":80"
  exposedAddress: "${PUBLIC_URL}"
  healthcheckAddress: ":9000"
  logLevel: "info"
  logFile: "console"
  authSecret: "${AUTH_SECRET}"
  dataDir: "/var/lib/netbird"
  auth:
    issuer: "${PUBLIC_URL}/oauth2"
    localAuthDisabled: false
    signKeyRefreshEnabled: true
    dashboardRedirectURIs:
      - "${PUBLIC_URL}/nb-auth"
      - "${PUBLIC_URL}/nb-silent-auth"
    cliRedirectURIs:
      - "http://localhost:53000/"
  store:
    engine: "sqlite"
    encryptionKey: "${STORE_KEY}"
  disableAnonymousMetrics: true
  disableGeoliteUpdate: ${DISABLE_GEOLITE:-true}
YAML
echo "pa-shield: wrote /cfg/config.yaml for ${PUBLIC_URL}"
