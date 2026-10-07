# pa-netbird (PA Shield)

Predicta image on top of the official NetBird self-hosted dashboard, branded as **PA Shield**. The management server stays `netbirdio/netbird-server`.

Live stack this was written against (7 Oct 2026):

| Piece | Image |
|---|---|
| Dashboard we replace | `netbirdio/dashboard:v2.90.3` |
| Server we do not replace | `netbirdio/netbird-server` 0.74.4 |

## What PA Shield adds

- **Look and feel:** orange `#FD9904` on purple-black `#1A0A22` (the PA Ticket palette), a shield mark, and the name "PA Shield".
  - `docker/apply-theme.sh` remaps the dashboard's compiled colours when the image is built.
  - `brand/inject.js` swaps the logo, tab icon, title and visible "NetBird" text at start. Code blocks and inputs are left alone so commands such as `netbird up` stay correct.
  - The favicon and app icon files are replaced inside the image (`brand/favicon.ico`, `brand/apple-icon.png`).
- **Login page** (`/oauth2`): the server draws it, so the gateway (`gateway/nginx.conf`) rewrites its colours, title, logo and icon, and adds the split layout, the bottom text and a "Forgot password?" link.
- **Password reset by email** (`reset/`): see below.
- **Invite emails:** creating or regenerating an invite in the dashboard emails the link.
- **Settings > Email Provider:** choose Microsoft Graph or SMTP in the dashboard (`brand/email-provider.js`).

## Run PA Shield from images (for anyone)

Everything ships as three images plus the official NetBird server, so nobody needs to edit config files:

| Image | What it holds |
|---|---|
| `pa-shield/dashboard` | NetBird dashboard with the PA Shield look, logo and icons |
| `pa-shield/reset` | Password reset, invite and test emails, and Settings > Email Provider |
| `pa-shield/gateway` | One address for everything, the branded login page, and the server-config generator |

```bash
docker compose -f docker-compose.standalone.yml up -d
```

Open http://localhost:8088. The first visit creates the owner account. The compose file builds the images from this repo, or pulls them if `PA_IMAGE_PREFIX` points at a registry that has them. The NetBird server config and its secrets are generated on first start and kept in a volume.

Settings are optional and go in `.env` (copy `.env.standalone.example`): `PUBLIC_URL`, ports, image prefix, versions. For a real deployment set `PUBLIC_URL` to your https address and put your own TLS proxy in front of the gateway port. Email can be set up later in the dashboard under Settings > Email Provider.

Build, publish or hand over the images:

```bash
scripts/build-images.sh                          # build and tag 1.0.0 and latest
PA_IMAGE_PREFIX=ghcr.io/your-org/pa-shield scripts/build-images.sh --push
scripts/build-images.sh --save pa-shield.tar     # one file for offline use, then: docker load -i pa-shield.tar
```

The version comes from `VERSION`. The brand name and logo are built into the images, so changing them means editing `brand/` and rebuilding.

## Run locally (development)

```bash
docker compose -f docker-compose.local.yml up -d --build
```

Open http://localhost:8088 and create the owner account on first visit. Nothing here uses the production domain. Server config for this stack is `local/config.yaml` (throwaway secrets).

## Email: password reset, invites, Settings

NetBird 0.74.4 cannot send mail, and its API only lets a user change their own password with the old one. So `reset/` fills the gap:

- The login page links to `/reset/forgot`. The user gets a signed, single-use link (30 minutes by default) and sets a new password, which is written to the login database (`idp.db`).
- Creating or regenerating an invite emails the invite link. The recipient comes from NetBird's own invite record.
- Settings > Email Provider (owners and admins only): choose **Microsoft Graph** (tenant ID, client ID, client secret, sender mailbox) or **SMTP**, then **Send test email**. For Graph, the Entra app needs the `Mail.Send` application permission with admin consent. Saved values are stored in the `reset_config` volume and override `smtp.env`.
- Emails use one template (banner, orange button, fallback link). The banner is `reset/email-banner.png`, attached inline because mail clients block SVG and localhost images.

With no provider configured, reset links are printed in the reset service log (`docker compose -f docker-compose.local.yml logs reset`).

### smtp.env (optional defaults)

```bash
cp smtp.env.example smtp.env
# set SMTP_PASSWORD (or leave SMTP_HOST empty and use Graph from the dashboard)
python3 scripts/check-smtp.sh
python3 scripts/check-smtp.sh --send you@example.com
```

`smtp.env` is the Hostinger mailbox Alertmanager already uses (`smtp.hostinger.com:587`, `common@predictaanalytics.io`, from `noreply@predictaanalytics.io`). It is not baked into any image. The NetBird server itself does not read it. When a NetBird release adds an `smtp` block to `config.yaml`, merge the settings there and restart `netbird-server` only.

Links in emails use `PUBLIC_URL`. Locally that is `http://localhost:8088`, which only opens on the same machine.

## Build (production dashboard image only)

```bash
cp .env.example .env
docker compose build
```

That produces `pa-netbird-dashboard:local` from `netbirdio/dashboard:${NETBIRD_DASHBOARD_TAG}`.

## Use it on the current host

Traefik already owns ports 80 and 443. Do not start a second copy. The dashboard container name is `netbird-dashboard`, on Docker network `netbird_netbird`.

Rancher rewrites `/opt/netbird/docker-compose.yml` from ConfigMap `netbird-compose` every minute. Change the image in that ConfigMap, not only on disk.

1. Build or load the dashboard image on the host.
2. In ConfigMap `netbird-compose`, set the dashboard service image to it. Leave `netbird-server` and Traefik digests as they are. Keep `env_file: ./dashboard.env`.
3. From `/opt/netbird`: `docker compose up -d dashboard`
4. Open the site and confirm the sidebar logo. Purge the Cloudflare cache if the old logo stays.

`dashboard.env` on the host is unchanged. `PA_BRAND_NAME` defaults to PA Shield.

The branded login page, the reset service and the email settings need the gateway layer (`gateway/nginx.conf`) in front of `netbird-server`, plus the `reset` service with the `netbird_data` volume and a `/reset/` route in Traefik. That part has not been set up on the live host.

## Upgrade when NetBird publishes a release

1. Read the [server release notes](https://github.com/netbirdio/netbird/releases) and the [dashboard release notes](https://github.com/netbirdio/dashboard/releases).
2. Set `NETBIRD_DASHBOARD_TAG` and `NETBIRD_SERVER_TAG` in `.env`.
3. `./scripts/upgrade.sh` rebuilds the dashboard image. Branding runs again at container start. The Settings tab and invite emails are added from outside the dashboard (`brand/email-provider.js`), so check them after an upgrade in case the dashboard markup changed.
4. Back up the `netbird_data` volume (`store.db`, `idp.db`, `events.db`) before recreating `netbird-server`.
5. Pin the new server image by digest in ConfigMap `netbird-compose`. For 0.79 and newer, set `reverseProxy.trustedPeers` to `172.30.0.10/32` next to the existing `trustedHTTPProxies` entry.
6. Move clients (this host, then staging, then POC) only after the server is healthy. The host client is apt-held at 0.74.6.

Official upgrade steps: https://docs.netbird.io/selfhosted/maintenance/upgrade
