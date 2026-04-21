#!/bin/bash
# apply.sh — run on the VPS as root to apply the MikroTik page layout changes
# Usage: bash /tmp/zivopay_patches/apply.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="/opt/zivopay/app"
TEMPLATE="$APP_DIR/templates/admin_mikrotik.html"
APP_PY="$APP_DIR/app.py"

echo "=== ZivoPay: MikroTik Admin Layout Patch ==="
echo

# ── 1. Patch the HTML template ────────────────────────────────────────────────
echo "[1] Patching admin_mikrotik.html …"
python3 "$SCRIPT_DIR/patch_mikrotik_page.py"

# ── 2. Inject the /admin/api/router-stats route into app.py ──────────────────
echo
echo "[2] Adding /admin/api/router-stats route to app.py …"

if grep -q "router-stats" "$APP_PY"; then
    echo "  [!] Route already present in app.py — skipping"
else
    # Append the route to the end of app.py
    # We inline the essential code (no imports needed — Flask & re already imported)
    cat >> "$APP_PY" << 'PYEOF'


# ── Live Router Stats (added by zivopay_patches/apply.sh) ────────────────────
import re as _re
import datetime as _dt

@app.route("/admin/api/router-stats")
def api_router_stats():
    try:
        # Load settings the same way the rest of the admin routes do
        cfg = _load_mikrotik_cfg()           # adjust if your helper has a different name
        if not cfg.get("enabled"):
            return jsonify({"error": "disabled"}), 503

        from router_tools import RouterConnection
        conn = RouterConnection(
            host=cfg["host"],
            port=int(cfg.get("port", 8728)),
            username=cfg.get("username", "admin"),
        )
        api = conn.connect()

        res = api(cmd="/system/resource/print")[0]

        cpu_load  = str(res.get("cpu-load", "?")) + "%"

        free_mem  = int(res.get("free-memory",  0))
        total_mem = int(res.get("total-memory", 1))
        used_mb   = round((total_mem - free_mem) / 1_048_576, 1)
        total_mb  = round(total_mem / 1_048_576, 1)
        mem_pct   = round((total_mem - free_mem) / total_mem * 100)
        memory    = f"{mem_pct}% ({used_mb}/{total_mb} MB)"

        uptime_raw = res.get("uptime", "")
        def _parse(s):
            d=int(_re.search(r'(\d+)d',s).group(1)) if 'd' in s else 0
            h=int(_re.search(r'(\d+)h',s).group(1)) if 'h' in s else 0
            m=int(_re.search(r'(\d+)m',s).group(1)) if 'm' in s else 0
            sc=int(_re.search(r'(\d+)s',s).group(1)) if 's' in s else 0
            return _dt.timedelta(days=d,hours=h,minutes=m,seconds=sc)

        boot_dt  = _dt.datetime.now() - _parse(uptime_raw)
        parts    = [_re.search(r'(\d+)'+u, uptime_raw) for u in ('d','h','m')]
        uptime   = ' '.join(p.group(1)+u for p,u in zip(parts,('d','h','m')) if p)

        active   = api(cmd="/ip/hotspot/active/print")
        binds    = api(cmd="/ip/hotspot/ip-binding/print")
        conn.disconnect()

        return jsonify({
            "cpu_load":  cpu_load,
            "memory":    memory,
            "uptime":    uptime or uptime_raw,
            "boot_time": boot_dt.strftime("%Y-%m-%d %H:%M"),
            "sessions":  len(active),
            "bindings":  len(binds),
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
PYEOF
    echo "  [✓] Route appended to app.py"
fi

# ── 3. Restart service ────────────────────────────────────────────────────────
echo
echo "[3] Restarting zivopay.service …"
systemctl restart zivopay.service
sleep 2
systemctl is-active zivopay.service && echo "  [✓] Service running" || echo "  [✗] Service failed — check: journalctl -u zivopay.service -n 30"

echo
echo "Done. Open https://admin.zivopay.online/admin/mikrotik to verify."
