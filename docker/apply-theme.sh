#!/bin/sh
# Build-time: remap the dashboard's compiled colours to the PA Ticket palette.
# Orange accent #F09F40 on a navy base (#0D1B37). Only CSS files are touched.
set -eu
ROOT="${1:-/usr/share/nginx/html}"

# "r g b" triplets (Tailwind rgb() form) and the matching hex, old -> new.
MAP='
246 131 48|240 159 64|f68330|f09f40
244 109 27|232 138 38|f46d1b|e88a26
229 114 42|214 126 30|e5722a|d67e1e
22 24 27|9 20 42|16181b|09142a
24 26 29|13 27 55|181a1d|0d1b37
24 25 29|13 27 55|18191d|0d1b37
28 30 33|17 33 64|1c1e21|112140
30 33 35|19 36 69|1e2123|132445
31 33 36|20 37 70|1f2124|142546
37 40 44|24 42 78|25282c|182a4e
37 40 45|24 42 78|25282d|182a4e
27 31 34|22 40 74|1b1f22|16284a
43 47 51|29 49 88|2b2f33|1d3158
46 50 56|33 54 94|2e3238|21365e
54 59 64|41 63 104|363b40|293f68
63 68 75|51 73 114|3f444b|334972
71 78 87|62 83 124|474e57|3e537c
'

SCRIPT=$(mktemp)
printf '%s\n' "$MAP" | while IFS='|' read -r old_rgb new_rgb old_hex new_hex; do
  [ -n "$old_rgb" ] || continue
  echo "s/rgb($old_rgb\\([\\/)]\\)/rgb($new_rgb\\1/g" >> "$SCRIPT"
  echo "s/#$old_hex/#$new_hex/g" >> "$SCRIPT"
done

find "$ROOT" -name '*.css' -type f -exec sed -i -f "$SCRIPT" {} +
echo "pa-netbird: theme applied to $(find "$ROOT" -name '*.css' -type f | wc -l) css files"
