#!/bin/sh
# Build-time: remap the dashboard's compiled colours to the PA Ticket palette.
# Orange accent #FD9904 on a purple-black base (#1A0A22). Only CSS files are touched.
set -eu
ROOT="${1:-/usr/share/nginx/html}"

# "r g b" triplets (Tailwind rgb() form) and the matching hex, old -> new.
MAP='
246 131 48|253 153 4|f68330|fd9904
244 109 27|228 135 0|f46d1b|e48700
229 114 42|228 135 0|e5722a|e48700
22 24 27|20 8 27|16181b|14081b
24 26 29|26 10 34|181a1d|1a0a22
24 25 29|26 10 34|18191d|1a0a22
28 30 33|32 14 41|1c1e21|200e29
30 33 35|35 16 45|1e2123|23102d
31 33 36|37 18 48|1f2124|251230
37 40 44|42 22 54|25282c|2a1636
37 40 45|42 22 54|25282d|2a1636
27 31 34|38 17 49|1b1f22|261131
43 47 51|50 27 62|2b2f33|321b3e
46 50 56|56 32 69|2e3238|382045
54 59 64|66 40 80|363b40|422850
63 68 75|78 52 94|3f444b|4e345e
71 78 87|92 66 108|474e57|5c426c
'

SCRIPT=$(mktemp)
printf '%s\n' "$MAP" | while IFS='|' read -r old_rgb new_rgb old_hex new_hex; do
  [ -n "$old_rgb" ] || continue
  echo "s/rgb($old_rgb\\([\\/)]\\)/rgb($new_rgb\\1/g" >> "$SCRIPT"
  echo "s/#$old_hex/#$new_hex/g" >> "$SCRIPT"
done

find "$ROOT" -name '*.css' -type f -exec sed -i -f "$SCRIPT" {} +
echo "pa-netbird: theme applied to $(find "$ROOT" -name '*.css' -type f | wc -l) css files"
