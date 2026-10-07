#!/bin/bash
# Rebuild pa-netbird-dashboard on top of a newer official dashboard tag.
# Branding is inside the image entrypoint, so it is reapplied on start.
# Does not restart the live stack. See README for the host cutover.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

dashboard_tag="${NETBIRD_DASHBOARD_TAG:-v2.90.3}"
server_tag="${NETBIRD_SERVER_TAG:-0.74.4}"
image_tag="${PA_IMAGE_TAG:-local}"

echo "Building pa-netbird-dashboard:${image_tag} from netbirdio/dashboard:${dashboard_tag}"
docker compose build --pull dashboard

echo
echo "Built image:"
docker image inspect "pa-netbird-dashboard:${image_tag}" --format 'id={{.Id}}'

echo
echo "Official server image to pin next to it: netbirdio/netbird-server:${server_tag}"
echo "Resolve its digest before editing ConfigMap netbird-compose:"
echo "  docker pull netbirdio/netbird-server:${server_tag}"
echo "  docker image inspect netbirdio/netbird-server:${server_tag} --format '{{index .RepoDigests 0}}'"
echo
echo "Also read https://github.com/netbirdio/netbird/releases and"
echo "https://github.com/netbirdio/dashboard/releases before recreating containers."
echo "If config.yaml.example in that server release has an smtp block, merge smtp.env into config.yaml."
