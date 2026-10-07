#!/bin/bash
# Runs after the official dashboard init (supervisord priority 250, init is 201).
# Copies the Predicta logo and inserts one same-origin script tag into each HTML
# file. The script is allowed by the dashboard Content-Security-Policy (script-src 'self').
set -euo pipefail

BRAND_NAME="${PA_BRAND_NAME:-PA Shield}"
LOGO_SRC="${PA_LOGO_SRC:-/brand/logo.svg}"
SRC="/opt/pa-netbird/brand"
DEST="/usr/share/nginx/html/brand"
HTML_ROOT="/usr/share/nginx/html"
MARKER='src="/brand/inject.js"'

mkdir -p "$DEST"
cp -f "${SRC}/logo.svg" "${SRC}/icon.png" "${SRC}/email-provider.js" "${DEST}/"
awk -v brand="$BRAND_NAME" -v logo="$LOGO_SRC" '
{
  gsub("__PA_BRAND_NAME__", brand)
  gsub("__PA_LOGO_SRC__", logo)
  gsub("__PA_ICON_SRC__", "/brand/icon.png")
  print
}
' "${SRC}/inject.js" > "${DEST}/inject.js"
chmod 644 "${DEST}/logo.svg" "${DEST}/icon.png" "${DEST}/email-provider.js" "${DEST}/inject.js"

init_running() {
  local cmdline
  for cmdline in /proc/[0-9]*/cmdline; do
    [[ -r "$cmdline" ]] || continue
    if tr '\0' ' ' < "$cmdline" | grep -q 'init_react_envs.sh'; then
      return 0
    fi
  done
  return 1
}

# Official init exits in under a second, so supervisord treats that as a failed
# start and runs it once more (startsecs default is 1). Patch only after it has
# stayed stopped, otherwise the second run overwrites the HTML.
ready=false
seen_init=false
quiet=0
for i in $(seq 1 60); do
  if init_running; then
    seen_init=true
    quiet=0
  else
    quiet=$((quiet + 1))
    if { [[ "$seen_init" == true ]] && [[ "$quiet" -ge 3 ]]; } || [[ "$quiet" -ge 8 ]]; then
      ready=true
      break
    fi
  fi
  echo "pa-netbird: waiting for official dashboard init (${i})"
  sleep 1
done
if [[ "$ready" != true ]]; then
  echo "pa-netbird: dashboard init did not finish; HTML was not branded" >&2
  exit 1
fi

patched=0
while IFS= read -r -d '' file; do
  if grep -q "$MARKER" "$file"; then
    continue
  fi
  if grep -q '</head>' "$file"; then
    sed -i 's|</head>|<script src="/brand/inject.js"></script><script src="/brand/email-provider.js"></script></head>|' "$file"
    patched=$((patched + 1))
  fi
done < <(find "$HTML_ROOT" -type f -name '*.html' ! -path '*/_next/*' -print0)

echo "pa-netbird: branded ${patched} html files as ${BRAND_NAME}"
