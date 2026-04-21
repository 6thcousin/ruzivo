# mikrotik_wifi_fix_cmds.rsc
# Run these in MikroTik terminal (Winbox / SSH to 192.168.88.1) to fix devices failing to connect
# ─────────────────────────────────────────────────────────────────────────────────────────────────

# ── STEP 1: Diagnose first ────────────────────────────────────────────────────

# Check WiFi interfaces
/interface wifi print

# Check if wifi2 (5GHz) is disabled
/interface wifi print where disabled=yes

# Check for access-list reject rules (main culprit for total connection failure)
/interface wifi access-list print

# Check registered clients
/interface wifi registration-table print

# Check recent logs for association failures
/log print where topics~"wireless" or message~"assoc" or message~"auth" or message~"reject"

# Check what channel wifi1 is on
/interface wifi monitor wifi1 once

# Check hotspot status
/ip hotspot print
/ip hotspot ip-binding print where type=blocked

# ── STEP 2: Apply fixes ───────────────────────────────────────────────────────

# Fix A: Remove ALL access-list entries (if there are any reject rules)
# WARNING: This clears all MAC-based restrictions — safe for open hotspot
/interface wifi access-list remove [find]

# Fix B: Enable wifi2 if it's disabled
/interface wifi enable wifi2

# Fix C: Force wifi1 to channel 6 (2437 MHz) in 20MHz — most compatible
# Channel 6, 20MHz avoids interference and works with ALL 802.11b/g/n devices
/interface wifi set wifi1 channel.frequency=2437 channel.width=20mhz

# Fix D: Force wifi2 to a clean 5GHz channel (if hardware supports it)
# Channel 36 (5180 MHz) is universally supported
/interface wifi set wifi2 channel.frequency=5180 channel.width=20mhz

# Fix E: Remove max client limits
/interface wifi set wifi1 max-station-count=0
/interface wifi set wifi2 max-station-count=0

# Fix F: Clear blocked bindings
/ip hotspot ip-binding remove [find type=blocked]

# Fix G: Confirm bridge settings (RSTP off, fast-forward off for hotspot compatibility)
/interface bridge set [find] protocol-mode=none fast-forward=no
/interface bridge port set [find] edge=yes-discover

# Fix H: DHCP lease cleanup (clear stale leases that clog the pool)
/ip dhcp-server lease remove [find status=expired]
/ip dhcp-server lease remove [find status=abandoned]

# ── STEP 3: Verify ────────────────────────────────────────────────────────────
/interface wifi print
/interface wifi monitor wifi1 once
/interface wifi monitor wifi2 once
/ip hotspot print
/ip dhcp-server lease print count-only

# ── IMPORTANT: Country setting ────────────────────────────────────────────────
# If devices still fail, check country/regulatory domain
/interface wifi print detail
# Look for "country" field — if blank or wrong region, set it:
# /interface wifi set wifi1 configuration.country="Zimbabwe"
# /interface wifi set wifi2 configuration.country="Zimbabwe"
# Then check if channels are now allowed:
# /interface wifi channel print
