#!/usr/bin/env python3
"""
fix_all.py — ZivoPay VPS frontend patch
────────────────────────────────────────
Run as root on the VPS:
    python3 /tmp/ruzivo_patches/scripts/zivopay_patches/fix_all.py

Applies every frontend change in one shot:
  1. app.py         — hardcode password "558920", fix SW header, add router-stats route
  2. router_tools.py — hardcode password default
  3. admin_mikrotik.html — remove password field + JS, remove Setup Guide / Speed Profiles,
                           inject Live Router Stats card (below REST API section)
  4. base.html       — improved PWA install script (iOS + Chrome)

Backs up every file before touching it.
"""

import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

APP_DIR = Path("/opt/zivopay/app")

# ── backup helper ─────────────────────────────────────────────────────────────

def backup(p: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = p.with_suffix(p.suffix + f".bak_{stamp}")
    shutil.copy(p, bak)
    print(f"    backup → {bak.name}")
    return bak


# ══════════════════════════════════════════════════════════════════════════════
# 1. app.py
# ══════════════════════════════════════════════════════════════════════════════

def fix_app_py():
    p = APP_DIR / "app.py"
    if not p.exists():
        print(f"  [!] {p} not found — skipping"); return
    print(f"\n[1] Patching {p} …")
    backup(p)
    src = p.read_text()

    changed = []

    # a) Hardcode password wherever it reads from form/config
    for pattern, repl in [
        (r'cfg\.get\(["\']password["\'],\s*["\']["\']?\)',  '"558920"'),
        (r'mt\.get\(["\']password["\'],\s*["\']["\']?\)',   '"558920"'),
        (r'request\.form\.get\(["\']password["\'][^)]*\)',  '"558920"'),
        (r'form\.get\(["\']password["\'][^)]*\)',           '"558920"'),
        (r'data\.get\(["\']password["\'][^)]*\)',           '"558920"'),
        (r'config\.get\(["\']password["\'][^)]*\)',         '"558920"'),
    ]:
        new, n = re.subn(pattern, repl, src)
        if n:
            changed.append(f"hardcoded password ({n}×)")
            src = new

    # b) Service-Worker-Allowed header
    new, n = re.subn(
        r'(Service-Worker-Allowed["\']]\s*=\s*)["\'][^"\']+["\']',
        r'\1"/"',
        src,
    )
    if n:
        changed.append("Service-Worker-Allowed → /")
        src = new

    # c) Inject /admin/api/router-stats route (only once)
    if "router-stats" not in src:
        route_code = '''

# ── Live Router Stats (injected by fix_all.py) ───────────────────────────────
import re as _re, datetime as _dt

@app.route("/admin/api/router-stats")
def api_router_stats():
    try:
        # find the helper that loads mikrotik settings
        cfg = None
        for fn in [_load_mikrotik_cfg, _load_mt_cfg, load_mikrotik_settings]:
            try: cfg = fn(); break
            except NameError: pass
        if cfg is None:
            # fallback: read saved JSON directly
            import json, os
            cfg_path = os.path.join(os.path.dirname(__file__), "mikrotik_cfg.json")
            if os.path.exists(cfg_path):
                with open(cfg_path) as f: cfg = json.load(f)
        if not cfg or not cfg.get("enabled"):
            return jsonify({"error": "MikroTik integration disabled"}), 503
        from router_tools import RouterConnection
        conn = RouterConnection(
            host=cfg["host"],
            port=int(cfg.get("port", 8728)),
            username=cfg.get("username", "admin"),
        )
        api = conn.connect()
        res = api(cmd="/system/resource/print")[0]
        cpu   = str(res.get("cpu-load", "?")) + "%"
        fm    = int(res.get("free-memory", 0))
        tm    = int(res.get("total-memory", 1))
        umb   = round((tm - fm) / 1_048_576, 1)
        tmb   = round(tm / 1_048_576, 1)
        mem   = f"{round((tm-fm)/tm*100)}% ({umb}/{tmb} MB)"
        uraw  = res.get("uptime", "")
        def _td(s):
            d=int(_re.search(r"(\\d+)d",s).group(1)) if "d" in s else 0
            h=int(_re.search(r"(\\d+)h",s).group(1)) if "h" in s else 0
            m=int(_re.search(r"(\\d+)m",s).group(1)) if "m" in s else 0
            sc=int(_re.search(r"(\\d+)s",s).group(1)) if "s" in s else 0
            return _dt.timedelta(days=d,hours=h,minutes=m,seconds=sc)
        parts = [(_re.search(r"(\\d+)"+u, uraw), u) for u in ("d","h","m")]
        uptime = " ".join(p.group(1)+u for p,u in parts if p) or uraw
        boot   = (_dt.datetime.now() - _td(uraw)).strftime("%Y-%m-%d %H:%M")
        active  = api(cmd="/ip/hotspot/active/print")
        binds   = api(cmd="/ip/hotspot/ip-binding/print")
        conn.disconnect()
        return jsonify({"cpu_load":cpu,"memory":mem,"uptime":uptime,
                        "boot_time":boot,"sessions":len(active),"bindings":len(binds)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
'''
        src += route_code
        changed.append("added /admin/api/router-stats route")

    p.write_text(src)
    print(f"  [✓] {', '.join(changed) or 'no changes needed'}")


# ══════════════════════════════════════════════════════════════════════════════
# 2. router_tools.py
# ══════════════════════════════════════════════════════════════════════════════

def fix_router_tools():
    p = APP_DIR / "router_tools.py"
    if not p.exists():
        print(f"\n[2] router_tools.py not found — skipping"); return
    print(f"\n[2] Patching {p} …")
    backup(p)
    src = p.read_text()

    # Change default password="" to password="558920" in __init__
    new, n = re.subn(
        r'(def __init__\s*\([^)]*password\s*=\s*)["\']["\']',
        r'\1"558920"',
        src,
    )
    if n:
        p.write_text(new)
        print(f"  [✓] Default password hardcoded to 558920")
    else:
        print(f"  [~] Password default already set or pattern not matched")


# ══════════════════════════════════════════════════════════════════════════════
# 3. admin_mikrotik.html
# ══════════════════════════════════════════════════════════════════════════════

LIVE_STATS_HTML = """\

  <!-- ── Live Router Stats ──────────────────────────────────────────────── -->
  <div class="card shadow-sm mt-4" id="live-stats-card">
    <div class="card-header fw-semibold d-flex justify-content-between align-items-center">
      <span><i class="bi bi-activity me-2"></i>Live Router Stats</span>
      <button class="btn btn-sm btn-outline-secondary" onclick="fetchRouterStats()">
        &#x21bb; Refresh
      </button>
    </div>
    <div class="card-body">
      <div id="stats-spinner" class="text-center py-3 text-muted">
        <span class="spinner-border spinner-border-sm me-1"></span>Loading&hellip;
      </div>
      <div id="stats-grid" class="row g-3" style="display:none">
        <div class="col-6 col-md-4">
          <div class="p-3 bg-secondary bg-opacity-10 rounded text-center">
            <div class="text-muted small mb-1">Identity</div>
            <div class="fw-bold" id="stat-identity">&mdash;</div>
          </div>
        </div>
        <div class="col-6 col-md-4">
          <div class="p-3 bg-secondary bg-opacity-10 rounded text-center">
            <div class="text-muted small mb-1">CPU Load</div>
            <div class="fs-4 fw-bold" id="stat-cpu">&mdash;</div>
          </div>
        </div>
        <div class="col-6 col-md-4">
          <div class="p-3 bg-secondary bg-opacity-10 rounded text-center">
            <div class="text-muted small mb-1">Memory Used</div>
            <div class="fw-bold" id="stat-memory">&mdash;</div>
          </div>
        </div>
        <div class="col-6 col-md-4">
          <div class="p-3 bg-secondary bg-opacity-10 rounded text-center">
            <div class="text-muted small mb-1">Uptime</div>
            <div class="fw-bold" id="stat-uptime">&mdash;</div>
          </div>
        </div>
        <div class="col-6 col-md-4">
          <div class="p-3 bg-secondary bg-opacity-10 rounded text-center">
            <div class="text-muted small mb-1">Hotspot Active</div>
            <div class="fs-4 fw-bold text-success" id="stat-sessions">&mdash;</div>
          </div>
        </div>
        <div class="col-6 col-md-4">
          <div class="p-3 bg-secondary bg-opacity-10 rounded text-center">
            <div class="text-muted small mb-1">IP Bindings</div>
            <div class="fs-4 fw-bold text-info" id="stat-bindings">&mdash;</div>
          </div>
        </div>
      </div>
      <div id="stats-err" class="alert alert-warning mb-0" style="display:none"></div>
      <p class="text-muted small mt-3 mb-0" id="stats-ts"></p>
    </div>
  </div>

  <script>
  (function(){
    async function fetchRouterStats(){
      document.getElementById('stats-err').style.display='none';
      try{
        const r=await fetch('/admin/api/router-stats');
        if(!r.ok) throw new Error('HTTP '+r.status);
        const d=await r.json();
        if(d.error) throw new Error(d.error);
        const set=(id,v)=>{const el=document.getElementById(id);if(el)el.textContent=v??'—';};
        set('stat-identity', d.identity);
        set('stat-cpu',      d.cpu_load);
        set('stat-memory',   d.memory);
        set('stat-uptime',   d.uptime);
        set('stat-sessions', d.sessions);
        set('stat-bindings', d.bindings);
        document.getElementById('stats-ts').textContent='Updated: '+new Date().toLocaleTimeString();
        document.getElementById('stats-spinner').style.display='none';
        document.getElementById('stats-grid').style.display='';
      }catch(e){
        document.getElementById('stats-spinner').style.display='none';
        const el=document.getElementById('stats-err');
        el.textContent='Stats unavailable: '+e.message;
        el.style.display='';
      }
    }
    window.fetchRouterStats=fetchRouterStats;
    fetchRouterStats();
    setInterval(fetchRouterStats,30000);
  })();
  </script>
"""


def _remove_block_containing(html: str, phrase: str) -> str:
    """Remove the outermost div (or its col- wrapper) containing phrase."""
    idx = html.find(phrase)
    if idx == -1:
        return html

    # walk back to find enclosing <div
    open_pos = html.rfind("<div", 0, idx)
    # check one level further for col- wrapper
    prev = html.rfind("<div", 0, open_pos)
    if re.search(r'class=["\'][^"\']*col', html[prev:open_pos + 5]):
        open_pos = prev

    depth, pos, end = 0, open_pos, -1
    while pos < len(html):
        od = html.find("<div", pos)
        cd = html.find("</div>", pos)
        if od == -1 and cd == -1:
            break
        if od != -1 and (cd == -1 or od < cd):
            depth += 1; pos = od + 4
        else:
            depth -= 1; pos = cd + 6
            if depth == 0:
                end = pos; break

    if end == -1:
        return html
    return html[:open_pos] + html[end:]


def fix_mikrotik_html():
    p = APP_DIR / "templates" / "admin_mikrotik.html"
    if not p.exists():
        print(f"\n[3] admin_mikrotik.html not found — skipping"); return
    print(f"\n[3] Patching {p} …")
    backup(p)
    html = p.read_text()
    changes = []

    # a) Remove password <label> … </label> block
    new = re.sub(
        r'<label[^>]*>[^<]*[Pp]assword[^<]*</label>\s*',
        '', html)
    if new != html:
        changes.append("removed password <label>"); html = new

    # b) Remove password <input> tag
    new = re.sub(
        r'<input[^>]*(?:id|name)=["\'](?:mt-pass|password|mt_pass)["\'][^>]*/?>',
        '', html)
    if new != html:
        changes.append("removed password <input>"); html = new

    # c) Remove password form-group wrapper div (if present)
    new = _remove_block_containing(html, 'id="mt-pass"')
    if new != html:
        changes.append("removed password form-group"); html = new
    new = _remove_block_containing(html, "mt-pass")
    if new != html:
        changes.append("removed password wrapper div"); html = new

    # d) Remove JS line that appends password
    new = re.sub(r'[ \t]*fd\.append\(["\']password["\'][^\n]*\n?', '', html)
    if new != html:
        changes.append("removed fd.append(password)"); html = new

    # e) Remove Setup Guide card
    new = _remove_block_containing(html, "Setup Guide")
    if new != html:
        changes.append("removed Setup Guide card"); html = new

    # f) Remove Speed Profiles card
    new = _remove_block_containing(html, "Speed Profile")
    if new != html:
        changes.append("removed Speed Profiles card"); html = new

    # g) Widen left column to full width
    new = re.sub(r'\bcol-(md|lg|sm)-6\b', 'col-12', html, count=1)
    if new != html:
        changes.append("widened column to col-12"); html = new

    # h) Remove empty row divs left behind
    new = re.sub(r'<div[^>]*class="[^"]*row[^"]*"[^>]*>\s*</div>', '', html)
    if new != html:
        changes.append("cleaned empty row divs"); html = new

    # i) Inject Live Router Stats (only once, before {% endblock %})
    if "Live Router Stats" not in html and "live-stats-card" not in html:
        endblock = html.rfind("{% endblock %}")
        if endblock == -1:
            html += LIVE_STATS_HTML
        else:
            html = html[:endblock] + LIVE_STATS_HTML + "\n" + html[endblock:]
        changes.append("injected Live Router Stats")
    else:
        changes.append("Live Router Stats already present")

    p.write_text(html)
    print(f"  [✓] {', '.join(changes)}")


# ══════════════════════════════════════════════════════════════════════════════
# 4. base.html — PWA install improvements
# ══════════════════════════════════════════════════════════════════════════════

PWA_SCRIPT = """\
  <!-- PWA install (injected by fix_all.py) -->
  <script>
  (function(){
    // ── iOS / Safari detection ──────────────────────────────────────────────
    var isIos = /iphone|ipad|ipod/i.test(navigator.userAgent);
    var isInStandalone = window.matchMedia('(display-mode: standalone)').matches
                      || window.navigator.standalone === true;

    // ── Chrome / Android ────────────────────────────────────────────────────
    var _deferred = null;
    window.addEventListener('beforeinstallprompt', function(e){
      e.preventDefault();
      _deferred = e;
      showBtn();
    });

    function showBtn(){
      var btn = document.getElementById('pwa-install-btn');
      if(btn) btn.style.display = '';
    }

    window.pwaInstall = async function(){
      if(_deferred){
        _deferred.prompt();
        var r = await _deferred.userChoice;
        if(r.outcome === 'accepted') _deferred = null;
      } else if(isIos && !isInStandalone){
        alert('To install: tap the Share button \\u2197 then \\"Add to Home Screen\\"');
      } else {
        alert('To install: open the browser menu and select \\"Install app\\" or \\"Add to Home Screen\\"');
      }
    };

    // Show button on iOS too (since beforeinstallprompt never fires)
    if(isIos && !isInStandalone) showBtn();

    // Detect if already installed
    if(isInStandalone){
      var btn = document.getElementById('pwa-install-btn');
      if(btn) btn.style.display = 'none';
    }
  })();
  </script>
"""


def fix_base_html():
    p = APP_DIR / "templates" / "base.html"
    if not p.exists():
        print(f"\n[4] base.html not found — skipping"); return
    print(f"\n[4] Patching {p} …")
    backup(p)
    src = p.read_text()

    # Remove old beforeinstallprompt block
    new = re.sub(
        r'<script>\s*(?:(?:let|var|const)\s+deferredPrompt|window\.addEventListener\([\'"]beforeinstallprompt).*?</script>',
        '',
        src,
        flags=re.DOTALL,
    )

    if "pwaInstall" in new:
        print("  [~] PWA script already updated — skipping")
        return

    # Inject before </body>
    if "</body>" in new:
        new = new.replace("</body>", PWA_SCRIPT + "\n</body>", 1)
    else:
        new += PWA_SCRIPT

    p.write_text(new)
    print("  [✓] PWA install script updated (iOS + Chrome support)")


# ══════════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("═" * 56)
    print("  ZivoPay VPS — apply all frontend patches")
    print("═" * 56)

    if not APP_DIR.exists():
        print(f"\n[✗] App directory not found: {APP_DIR}")
        sys.exit(1)

    fix_app_py()
    fix_router_tools()
    fix_mikrotik_html()
    fix_base_html()

    print("\n" + "═" * 56)
    print("  Restarting zivopay.service …")
    import subprocess
    r = subprocess.run(["systemctl", "restart", "zivopay.service"])
    import time; time.sleep(2)
    r2 = subprocess.run(["systemctl", "is-active", "zivopay.service"],
                        capture_output=True, text=True)
    status = r2.stdout.strip()
    if status == "active":
        print("  [✓] Service running")
    else:
        print(f"  [✗] Service status: {status}")
        print("      Check: journalctl -u zivopay.service -n 40")
    print("═" * 56)


if __name__ == "__main__":
    main()
