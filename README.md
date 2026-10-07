# pa-netbird

Predicta image on top of the official NetBird self-hosted dashboard. The management server stays `netbirdio/netbird-server`.

Live stack this was written against (7 Oct 2026):

| Piece | Image |
|---|---|
| Dashboard we replace | `netbirdio/dashboard:v2.90.3` |
| Server we do not replace | `netbirdio/netbird-server` 0.74.4 |
| Built image | `pa-netbird-dashboard:local` |

## What this image adds

On every start it copies `brand/logo.png` into the dashboard and adds `/brand/inject.js` to each HTML page. The script swaps the NetBird logo and tab icon for the Predicta mark. It runs after NetBird's own init, so a newer base image's HTML is patched without a fork.

The login page at `/oauth2` is drawn by the server binary. This image does not change that page. `config.yaml` has no logo field.

## SMTP

NetBird 0.74.4 and the current 0.80.0 server have no SMTP setting. Invite and reset mail are not sent. Users are created in the dashboard with a password.

`smtp.env` is the Hostinger mailbox Alertmanager already uses (`smtp.hostinger.com:587`, `common@predictaanalytics.io`, from `noreply@predictaanalytics.io`). It is not baked into the image.

```bash
cp smtp.env.example smtp.env
# set SMTP_PASSWORD
python3 scripts/check-smtp.sh
python3 scripts/check-smtp.sh --send you@example.com
```

When a NetBird release adds an `smtp` block to `config.yaml`, merge `smtp.env` into `/opt/netbird/config.yaml` (Rancher secret `netbird-config`) and restart `netbird-server` only.

## Build

```bash
cp .env.example .env
docker compose build
```

That produces `pa-netbird-dashboard:local` from `netbirdio/dashboard:${NETBIRD_DASHBOARD_TAG}`.

## Use it on the current host

Traefik already owns ports 80 and 443. Do not start a second copy. The dashboard container name is `netbird-dashboard`, on Docker network `netbird_netbird`.

Rancher rewrites `/opt/netbird/docker-compose.yml` from ConfigMap `netbird-compose` every minute. Change the image in that ConfigMap, not only on disk.

1. Build or load `pa-netbird-dashboard:local` on the host.
2. In ConfigMap `netbird-compose`, set the dashboard service image to `pa-netbird-dashboard:local`. Leave `netbird-server` and Traefik digests as they are. Keep `env_file: ./dashboard.env`.
3. From `/opt/netbird`: `docker compose up -d dashboard`
4. Open https://netbird.predictaanalytics.io/ and confirm the sidebar logo. Purge the Cloudflare cache if the old logo stays.

`dashboard.env` on the host is unchanged. `PA_BRAND_NAME` defaults to Predicta.

## Upgrade when NetBird publishes a release

1. Read the [server release notes](https://github.com/netbirdio/netbird/releases) and the [dashboard release notes](https://github.com/netbirdio/dashboard/releases).
2. Set `NETBIRD_DASHBOARD_TAG` and `NETBIRD_SERVER_TAG` in `.env`.
3. `./scripts/upgrade.sh` rebuilds this image. Branding runs again at container start.
4. Back up the `netbird_data` volume (`store.db`, `idp.db`, `events.db`) before recreating `netbird-server`.
5. Pin the new server image by digest in ConfigMap `netbird-compose`. For 0.79 and newer, set `reverseProxy.trustedPeers` to `172.30.0.10/32` next to the existing `trustedHTTPProxies` entry.
6. Move clients (this host, then staging, then POC) only after the server is healthy. The host client is apt-held at 0.74.6.

Official upgrade steps: https://docs.netbird.io/selfhosted/maintenance/upgrade
