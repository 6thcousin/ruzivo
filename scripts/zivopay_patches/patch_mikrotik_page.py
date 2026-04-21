#!/usr/bin/env python3
"""
patch_mikrotik_page.py
──────────────────────
Run on the VPS as root to update admin_mikrotik.html:
  - Remove the "Setup Guide" and "Speed Profiles" right-column cards
  - Collapse the two-column grid to single-column
  - Inject a "Live Router Stats" card below REST API Connection

Usage:
  python3 patch_mikrotik_page.py
"""

import re
import shutil
from datetime import datetime
from pathlib import Path

TEMPLATE = Path("/opt/zivopay/app/templates/admin_mikrotik.html")

# ── helpers ───────────────────────────────────────────────────────────────────

def remove_card_containing(html: str, phrase: str) -> str:
    """
    Remove the *outermost* Bootstrap card (or column wrapper) that contains
    the given phrase anywhere in its text. Works by counting <div>/<\/div> tags.
    """
    idx = html.find(phrase)
    if idx == -1:
        print(f"  [!] phrase not found: {phrase!r}  — skipping")
        return html

    # Walk backwards to find the opening <div of the card (or its col- wrapper)
    open_pos = html.rfind("<div", 0, idx)

    # Walk backwards further to find a col- wrapper, if present
    prev_open = html.rfind("<div", 0, open_pos)
    snippet = html[prev_open : open_pos]
    if re.search(r'class="[^"]*col[^"]*"', snippet) or re.search(r"class='[^']*col[^']*'", snippet):
        open_pos = prev_open

    # Now find the matching closing </div> by counting nesting depth
    depth = 0
    pos = open_pos
    end_pos = -1
    while pos < len(html):
        open_tag = html.find("<div", pos)
        close_tag = html.find("</div>", pos)
        if open_tag == -1 and close_tag == -1:
            break
        if open_tag != -1 and (close_tag == -1 or open_tag < close_tag):
            depth += 1
            pos = open_tag + 4
        else:
            depth -= 1
            pos = close_tag + 6
            if depth == 0:
                end_pos = pos
                break

    if end_pos == -1:
        print(f"  [!] Could not find closing div for: {phrase!r}")
        return html

    removed = html[open_pos:end_pos]
    print(f"  [✓] Removed block containing {phrase!r} ({len(removed)} chars)")
    return html[:open_pos] + html[end_pos:]


def widen_rest_api_column(html: str) -> str:
    """Replace col-md-6 / col-lg-6 that wraps the REST API form with col-12."""
    # Look for the column div that immediately precedes the REST API card
    pattern = re.compile(
        r'(<div\s+class=")(col-(?:md|lg|sm)-\d+)("[^>]*>)(\s*<div\s[^>]*class="[^"]*card[^"]*")',
        re.DOTALL,
    )
    count = [0]

    def replacer(m):
        inner = m.group(4)
        if "REST API" in html[html.find(inner): html.find(inner) + 600]:
            count[0] += 1
            return m.group(1) + "col-12" + m.group(3) + m.group(4)
        return m.group(0)

    result = pattern.sub(replacer, html)
    if count[0]:
        print(f"  [✓] Widened REST API column to col-12")
    else:
        # Fallback: replace first col-md-6 or col-lg-6
        result = re.sub(r'\bcol-(md|lg|sm)-6\b', 'col-12', html, count=1)
        print("  [~] Widened first column wrapper to col-12 (fallback)")
    return result


LIVE_STATS_CARD = '''
  <!-- Live Router Stats ───────────────────────────────────────────────── -->
  <div class="card shadow-sm mt-4">
    <div class="card-header fw-semibold d-flex justify-content-between align-items-center">
      <span><i class="bi bi-activity me-2"></i>Live Router Stats</span>
      <button class="btn btn-sm btn-outline-secondary" onclick="fetchRouterStats()" id="stats-refresh-btn">
        <i class="bi bi-arrow-clockwise"></i> Refresh
      </button>
    </div>
    <div class="card-body">
      <div id="stats-loading" class="text-center py-3 text-muted">
        <div class="spinner-border spinner-border-sm me-2" role="status"></div>
        Loading stats&hellip;
      </div>
      <div id="stats-content" style="display:none">
        <div class="row g-3">
          <div class="col-6 col-md-4">
            <div class="p-3 bg-light rounded text-center">
              <div class="text-muted small mb-1">CPU Load</div>
              <div class="fs-4 fw-bold" id="stat-cpu">&mdash;</div>
            </div>
          </div>
          <div class="col-6 col-md-4">
            <div class="p-3 bg-light rounded text-center">
              <div class="text-muted small mb-1">Memory Used</div>
              <div class="fs-4 fw-bold" id="stat-memory">&mdash;</div>
            </div>
          </div>
          <div class="col-6 col-md-4">
            <div class="p-3 bg-light rounded text-center">
              <div class="text-muted small mb-1">Uptime</div>
              <div class="fs-5 fw-bold" id="stat-uptime">&mdash;</div>
            </div>
          </div>
          <div class="col-6 col-md-4">
            <div class="p-3 bg-light rounded text-center">
              <div class="text-muted small mb-1">Boot Time</div>
              <div class="fs-6 fw-bold" id="stat-boot">&mdash;</div>
            </div>
          </div>
          <div class="col-6 col-md-4">
            <div class="p-3 bg-light rounded text-center">
              <div class="text-muted small mb-1">Hotspot Sessions</div>
              <div class="fs-4 fw-bold text-success" id="stat-sessions">&mdash;</div>
            </div>
          </div>
          <div class="col-6 col-md-4">
            <div class="p-3 bg-light rounded text-center">
              <div class="text-muted small mb-1">IP Bindings</div>
              <div class="fs-4 fw-bold text-info" id="stat-bindings">&mdash;</div>
            </div>
          </div>
        </div>
        <p class="text-muted small mt-3 mb-0" id="stats-updated-at"></p>
      </div>
      <div id="stats-error" class="alert alert-warning mb-0" style="display:none"></div>
    </div>
  </div>

  <script>
  (function () {
    var _statsTimer = null;

    async function fetchRouterStats() {
      document.getElementById('stats-error').style.display = 'none';
      try {
        const res = await fetch('/admin/api/router-stats');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const d = await res.json();
        document.getElementById('stat-cpu').textContent      = d.cpu_load  ?? '—';
        document.getElementById('stat-memory').textContent   = d.memory    ?? '—';
        document.getElementById('stat-uptime').textContent   = d.uptime    ?? '—';
        document.getElementById('stat-boot').textContent     = d.boot_time ?? '—';
        document.getElementById('stat-sessions').textContent = d.sessions  ?? '—';
        document.getElementById('stat-bindings').textContent = d.bindings  ?? '—';
        document.getElementById('stats-updated-at').textContent =
          'Last updated: ' + new Date().toLocaleTimeString();
        document.getElementById('stats-loading').style.display  = 'none';
        document.getElementById('stats-content').style.display  = '';
      } catch (err) {
        document.getElementById('stats-loading').style.display  = 'none';
        const errEl = document.getElementById('stats-error');
        errEl.textContent = 'Could not load stats: ' + err.message;
        errEl.style.display = '';
      }
    }

    // expose globally for the Refresh button
    window.fetchRouterStats = fetchRouterStats;

    fetchRouterStats();
    _statsTimer = setInterval(fetchRouterStats, 30000);
  })();
  </script>
'''


def inject_stats_card(html: str) -> str:
    """Insert Live Router Stats card after the REST API Connection card block."""
    # Strategy 1: find the closing </form> of the REST API form, then find the
    # next </div> (end of card-body) and </div> (end of card), insert after that.
    rest_idx = html.find("REST API")
    if rest_idx == -1:
        rest_idx = html.find("rest-api")
    if rest_idx == -1:
        print("  [!] Could not locate REST API section — appending before </div>{% endblock %}")
        end = html.rfind("{% endblock %}")
        if end == -1:
            end = len(html)
        return html[:end] + LIVE_STATS_CARD + "\n" + html[end:]

    # Find end of the card that contains the REST API form
    # Walk forward from rest_idx, count divs
    depth = 0
    pos = rest_idx
    card_end = -1
    # First, find the opening <div of this card
    card_open = html.rfind("<div", 0, rest_idx)
    # Walk back further until we find a card div
    test = card_open
    while test > 0:
        chunk = html[test: test + 80]
        if 'card' in chunk:
            card_open = test
            break
        test = html.rfind("<div", 0, test)

    pos = card_open
    depth = 0
    while pos < len(html):
        od = html.find("<div", pos)
        cd = html.find("</div>", pos)
        if od == -1 and cd == -1:
            break
        if od != -1 and (cd == -1 or od < cd):
            depth += 1
            pos = od + 4
        else:
            depth -= 1
            pos = cd + 6
            if depth == 0:
                card_end = pos
                break

    if card_end == -1:
        print("  [!] Could not find end of REST API card — appending before {% endblock %}")
        end = html.rfind("{% endblock %}")
        return html[:end] + LIVE_STATS_CARD + "\n" + html[end:]

    print(f"  [✓] Injected Live Router Stats card after REST API section")
    return html[:card_end] + "\n" + LIVE_STATS_CARD + html[card_end:]


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    if not TEMPLATE.exists():
        print(f"[✗] Template not found: {TEMPLATE}")
        raise SystemExit(1)

    html = TEMPLATE.read_text(encoding="utf-8")
    backup = TEMPLATE.with_suffix(f".html.bak_{datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy(TEMPLATE, backup)
    print(f"[✓] Backup: {backup}")

    print("\n[1] Removing Setup Guide card …")
    html = remove_card_containing(html, "Setup Guide")

    print("\n[2] Removing Speed Profiles card …")
    html = remove_card_containing(html, "Speed Profile")

    print("\n[3] Widening REST API column …")
    html = widen_rest_api_column(html)

    print("\n[4] Injecting Live Router Stats card …")
    if "Live Router Stats" in html:
        print("  [!] Live Router Stats already present — skipping injection")
    else:
        html = inject_stats_card(html)

    TEMPLATE.write_text(html, encoding="utf-8")
    print(f"\n[✓] Done — {TEMPLATE} updated")
    print("    Restart the service:  systemctl restart zivopay.service")


if __name__ == "__main__":
    main()
