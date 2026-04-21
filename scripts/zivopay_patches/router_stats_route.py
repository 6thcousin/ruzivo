"""
router_stats_route.py
─────────────────────
Add this route to /opt/zivopay/app/app.py (or app/routes/admin.py if split).

Paste the route function below into the Flask app, anywhere after the existing
MikroTik-related routes.

The route connects to the MikroTik via the WireGuard tunnel and returns:
  - cpu_load   → "42%"
  - memory     → "45% (180/400 MB)"
  - uptime     → "3d 14h 22m"
  - boot_time  → "2024-04-09 08:15"
  - sessions   → 7
  - bindings   → 12
"""

# ── paste this into app.py ────────────────────────────────────────────────────
from flask import jsonify
import datetime as _dt


@app.route("/admin/api/router-stats")
def api_router_stats():
    """Return live MikroTik stats for the admin dashboard panel."""
    try:
        # Read saved MikroTik settings (same way the rest of the admin routes do)
        mt = _load_mikrotik_settings()          # your existing helper
        if not mt.get("enabled"):
            return jsonify({"error": "MikroTik integration disabled"}), 503

        from app.router_tools import RouterConnection  # adjust import path
        conn = RouterConnection(
            host=mt["host"],
            port=int(mt.get("port", 8728)),
            username=mt.get("username", "admin"),
            # password is hardcoded in RouterConnection.__init__ default ("558920")
        )
        api = conn.connect()

        # ── /system/resource ─────────────────────────────────────────────────
        resource = api(cmd="/system/resource/print")[0]

        cpu_load   = resource.get("cpu-load", "?") + "%"

        free_mem   = int(resource.get("free-memory",  0))
        total_mem  = int(resource.get("total-memory", 1))
        used_mb    = round((total_mem - free_mem) / 1_048_576, 1)
        total_mb   = round(total_mem / 1_048_576, 1)
        mem_pct    = round((total_mem - free_mem) / total_mem * 100)
        memory     = f"{mem_pct}% ({used_mb}/{total_mb} MB)"

        uptime_raw = resource.get("uptime", "")      # e.g. "3d14h22m5s"
        uptime     = _fmt_uptime(uptime_raw)

        # Boot time = now − uptime
        boot_dt    = _dt.datetime.now() - _parse_uptime(uptime_raw)
        boot_time  = boot_dt.strftime("%Y-%m-%d %H:%M")

        # ── /ip/hotspot/active ───────────────────────────────────────────────
        active     = api(cmd="/ip/hotspot/active/print")
        sessions   = len(active)

        # ── /ip/hotspot/ip-binding ───────────────────────────────────────────
        bindings_r = api(cmd="/ip/hotspot/ip-binding/print")
        bindings   = len(bindings_r)

        conn.disconnect()

        return jsonify({
            "cpu_load":  cpu_load,
            "memory":    memory,
            "uptime":    uptime,
            "boot_time": boot_time,
            "sessions":  sessions,
            "bindings":  bindings,
        })

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── helpers ───────────────────────────────────────────────────────────────────

import re as _re

def _parse_uptime(s: str) -> _dt.timedelta:
    """Parse MikroTik uptime string like '3d14h22m5s' into timedelta."""
    d = int(_re.search(r'(\d+)d', s).group(1)) if 'd' in s else 0
    h = int(_re.search(r'(\d+)h', s).group(1)) if 'h' in s else 0
    m = int(_re.search(r'(\d+)m', s).group(1)) if 'm' in s else 0
    sc = int(_re.search(r'(\d+)s', s).group(1)) if 's' in s else 0
    return _dt.timedelta(days=d, hours=h, minutes=m, seconds=sc)


def _fmt_uptime(s: str) -> str:
    """Format '3d14h22m5s' → '3d 14h 22m'."""
    parts = []
    for unit in ('d', 'h', 'm'):
        m = _re.search(r'(\d+)' + unit, s)
        if m:
            parts.append(m.group(1) + unit)
    return ' '.join(parts) if parts else s
