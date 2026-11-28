#!/usr/bin/env bash
# Tay karta hai ki ye run list bheje ya nahi, aur kitni der wait kare.
# Output: go=true/false, wait=<seconds>, id=<slot>
set -euo pipefail
OUT="${GITHUB_OUTPUT:-/dev/stdout}"
now="${NOW:-$(date +%s)}"
MAX_WAIT=$((5 * 3600 + 30 * 60)) # job limit 6 ghante hai

if [ "$EVENT" != "schedule" ]; then
  printf 'go=true\nwait=0\nid=\n' >> "$OUT"
  exit 0
fi

read -r minute hours _ <<< "$CRON"
case "$hours" in
  17,19,21) target_utc="00:30" ;; # 6:00 AM IST
  5,7,9)    target_utc="12:30" ;; # 6:00 PM IST
  *) echo "Unknown cron: $CRON"; exit 1 ;;
esac

# Ye run asal mein kis time ke liye tha: pichhle 24 ghante ka sabse naya cron time
today=$(date -u -d "@$now" +%F)
fired=0
for h in ${hours//,/ }; do
  t=$(date -u -d "$today $h:$minute" +%s)
  if [ "$t" -gt "$now" ]; then t=$((t - 86400)); fi
  if [ "$t" -gt "$fired" ]; then fired=$t; fi
done

# Us cron time ke baad aane wala pehla target
target=$(date -u -d "$(date -u -d "@$fired" +%F) $target_utc" +%s)
if [ "$target" -lt "$fired" ]; then target=$((target + 86400)); fi
id=$(TZ=Asia/Kolkata date -d "@$target" +%F_%H%M)
wait_s=$((target - now - 120)) # 2 minute pehle shuru, taaki list time par pahunche
if [ "$wait_s" -lt 0 ]; then wait_s=0; fi

go=true
if [ -f last_slot.txt ] && [ "$(cat last_slot.txt)" = "$id" ]; then
  go=false; echo "Slot $id ki list pehle hi bhej di gayi hai."
elif [ "$wait_s" -gt "$MAX_WAIT" ]; then
  go=false; echo "Slot $id abhi door hai, agla trigger sambhalega."
fi
echo "Slot=$id go=$go wait=${wait_s}s"
printf 'go=%s\nwait=%s\nid=%s\n' "$go" "$wait_s" "$id" >> "$OUT"
