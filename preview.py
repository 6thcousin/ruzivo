"""
PDF Invoice Live Preview Server
--------------------------------
Watches pdf_generator.py for saves, regenerates the PDF with sample data,
renders page 1 to a PNG (via PyMuPDF), and serves it as a plain <img> tag
so the browser refreshes in under a second.

Usage:
    python preview.py

Then open: http://localhost:9000
"""

import os
import sys
import time
import json
import shutil
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── Project root on path ───────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.services.pdf_generator import generate_pdf

# ── PyMuPDF (fast PDF → PNG) ──────────────────────────────────────────────────
try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False
    print("[PREVIEW] PyMuPDF not found — run: pip install pymupdf")
    print("[PREVIEW] Falling back to slower PDF iframe mode.")

# ── Sample data ────────────────────────────────────────────────────────────────
SAMPLE_DATA = {
    "doc_type":        "Quotation",
    "company_name":    "Zivopay Digital Services Pvt Ltd",
    "company_email":   "wekwamarufu@gmail.com",
    "company_phone":   "+263 77 123 4567",
    "company_website": "admin.zivopay.online",
    "client_name":     "Freedom Installations",
    "client_company":  "Freedom Installations (Pvt) Ltd",
    "client_address":  "14 Samora Machel Ave, Harare, Zimbabwe",
    "client_phone":    "+263 78 987 6543",
    "client_email":    "info@freedominstalls.co.zw",
    "currency":        "USD",
    "tax_rate":        15,
    "payment_terms":   "Due on Receipt",
    "po_number":       "PO-2026-0042",
    "lead_time":       "5-7 Business Days",
    "notes":           (
        "Prices are valid for 30 days from the date of this quotation.\n"
        "Delivery charges may apply depending on location.\n"
        "Please reference the Quotation No. on all correspondence."
    ),
    "banking_details": (
        "Bank: National Building Society (NBS)\n"
        "Account Name: Freedom Installations Pvt Ltd\n"
        "USD Account No: 123456789\n"
        "ZiG Account No: 321654654\n"
        "Vendor No: 2582589\n"
        "Branch Code: XVCGF7845"
    ),
    "items": [
        {"description": "Mikrotik hEX RB750Gr3 Router",        "qty": 2.0, "unit_price": 89.00,  "total": 178.00},
        {"description": "CAT6 Ethernet Cable (305m Box)",       "qty": 1.0, "unit_price": 55.00,  "total": 55.00},
        {"description": "Network Installation & Configuration", "qty": 1.0, "unit_price": 120.00, "total": 120.00},
        {"description": "Ubiquiti UniFi Access Point AC-Pro",   "qty": 3.0, "unit_price": 149.00, "total": 447.00},
        {"description": "Power over Ethernet (PoE) Injector",  "qty": 3.0, "unit_price": 18.00,  "total": 54.00},
    ],
}

# ── Shared state ───────────────────────────────────────────────────────────────
_state = {
    "version":   0,
    "pdf_path":  None,
    "img_path":  None,
    "lock":      threading.Lock(),
}

OUT_DIR    = os.path.join(ROOT, "generated")
PREVIEW_PDF = os.path.join(OUT_DIR, "_preview.pdf")
PREVIEW_IMG = os.path.join(OUT_DIR, "_preview.png")
WATCH_FILE  = os.path.join(ROOT, "app", "services", "pdf_generator.py")


def _pdf_to_png(pdf_path: str, out_path: str, dpi: int = 150):
    """Render page 1 of PDF to PNG using PyMuPDF."""
    doc  = fitz.open(pdf_path)
    page = doc[0]
    mat  = fitz.Matrix(dpi / 72, dpi / 72)
    pix  = page.get_pixmap(matrix=mat, alpha=False)
    pix.save(out_path)
    doc.close()


def _regenerate():
    """Generate PDF → convert to PNG → bump version."""
    try:
        # Reload pdf_generator so edits are picked up without restarting
        import importlib
        import app.services.pdf_generator as _mod
        importlib.reload(_mod)
        from app.services.pdf_generator import generate_pdf as _gen

        os.makedirs(OUT_DIR, exist_ok=True)
        path = _gen(SAMPLE_DATA)
        shutil.copy2(path, PREVIEW_PDF)

        if HAS_FITZ:
            _pdf_to_png(PREVIEW_PDF, PREVIEW_IMG)

        with _state["lock"]:
            _state["version"] += 1
            _state["pdf_path"] = PREVIEW_PDF
            _state["img_path"] = PREVIEW_IMG if HAS_FITZ else None

        print(f"[PREVIEW] Ready — version {_state['version']}")

    except Exception as e:
        print(f"[PREVIEW] Error: {e}")


# ── Auto-refresh timer (polls file mtime every 2s as guaranteed fallback) ─────

def _start_auto_refresh(interval: float = 2.0):
    """Re-generate whenever pdf_generator.py mtime changes, checked every `interval` seconds."""
    last_mtime = [0.0]

    def _loop():
        while True:
            try:
                mtime = os.path.getmtime(WATCH_FILE)
                if mtime != last_mtime[0]:
                    last_mtime[0] = mtime
                    if _state["version"] > 0:   # skip very first tick (already generated)
                        print("[PREVIEW] File changed — regenerating...")
                    _regenerate()
            except Exception:
                pass
            time.sleep(interval)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    print(f"[PREVIEW] Auto-refresh every {interval}s")


# ── File watcher ───────────────────────────────────────────────────────────────

def _start_watcher():
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class _Handler(FileSystemEventHandler):
            def __init__(self):
                self._last = 0

            def on_modified(self, event):
                if os.path.abspath(event.src_path) != os.path.abspath(WATCH_FILE):
                    return
                now = time.time()
                if now - self._last < 1.2:   # debounce — ignore rapid duplicate events
                    return
                self._last = now
                print("[PREVIEW] Change detected — regenerating...")
                _regenerate()

        observer = Observer()
        observer.schedule(_Handler(), path=os.path.dirname(WATCH_FILE), recursive=False)
        observer.daemon = True
        observer.start()
        print(f"[PREVIEW] Watching: {os.path.relpath(WATCH_FILE, ROOT)}")

    except ImportError:
        print("[PREVIEW] watchdog not installed — run: pip install watchdog")


# ── HTML page ──────────────────────────────────────────────────────────────────

_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>PDF Preview — ZivoPay</title>
  <style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ background:#111827; font-family:system-ui,sans-serif;
            display:flex; flex-direction:column; height:100vh; overflow:hidden; }}

    #bar {{ background:#1f2937; padding:10px 20px; display:flex;
            align-items:center; gap:12px; flex-shrink:0;
            border-bottom:1px solid #374151; }}
    #bar h1 {{ font-size:13px; font-weight:600; color:#93c5fd; letter-spacing:.3px; }}
    #badge {{ margin-left:auto; font-size:11px; padding:3px 10px;
              border-radius:99px; background:#064e3b; color:#6ee7b7;
              border:1px solid #065f46; }}
    #badge.updating {{ background:#78350f; color:#fcd34d; border-color:#92400e; }}

    #scroll {{ flex:1; overflow-y:auto; display:flex;
               justify-content:center; padding:24px 16px; }}
    #scroll img {{ max-width:900px; width:100%; border-radius:4px;
                   box-shadow:0 8px 32px rgba(0,0,0,.6);
                   transition:opacity .15s ease; }}
    #scroll img.fading {{ opacity:0.4; }}

    #fallback {{ flex:1; border:none; background:#fff; }}
  </style>
</head>
<body>
  <div id="bar">
    <h1>ZivoPay — PDF Live Preview</h1>
    <span id="badge">v{version} &nbsp;Live</span>
  </div>

  {'<div id="scroll"><img id="preview" src="/img?v={version}"/></div>' if use_img else
   '<iframe id="fallback" src="/pdf?v={version}"></iframe>'}

  <script>
    let current = {version};
    const badge = document.getElementById('badge');
    {'const img = document.getElementById("preview");' if use_img else ''}

    async function poll() {{
      try {{
        const r = await fetch('/version');
        const d = await r.json();
        if (d.version !== current) {{
          current = d.version;
          badge.className = 'updating';
          badge.textContent = 'Updating...';
          {'img.classList.add("fading"); img.src = "/img?v=" + current;' if use_img else
           'document.getElementById("fallback").src = "/pdf?v=" + current;'}
        }}
      }} catch(e) {{}}
      setTimeout(poll, 600);
    }}

    {'img.onload = function() { img.classList.remove("fading"); badge.className=""; badge.textContent = "v" + current + " \\u00a0Live"; };' if use_img else ''}

    poll();
  </script>
</body>
</html>
"""


def _html() -> bytes:
    use_img = HAS_FITZ
    with _state["lock"]:
        v = _state["version"]

    if use_img:
        body_tag  = '<div id="scroll"><img id="preview" src="/img?v={v}"/></div>'.format(v=v)
        img_js    = 'const img = document.getElementById("preview");'
        upd_js    = 'img.classList.add("fading"); img.src = "/img?v=" + current;'
        onload_js = 'img.onload = function() {{ img.classList.remove("fading"); badge.className=""; badge.textContent = "v" + current + " \\u00a0Live"; }};'
    else:
        body_tag  = '<iframe id="fallback" src="/pdf?v={v}" style="flex:1;border:none;background:#fff;"></iframe>'.format(v=v)
        img_js    = ""
        upd_js    = 'document.getElementById("fallback").src = "/pdf?v=" + current;'
        onload_js = ""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>PDF Preview — ZivoPay</title>
  <style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ background:#111827; font-family:system-ui,sans-serif;
            display:flex; flex-direction:column; height:100vh; overflow:hidden; }}
    #bar {{ background:#1f2937; padding:10px 20px; display:flex;
            align-items:center; gap:12px; flex-shrink:0;
            border-bottom:1px solid #374151; }}
    #bar h1 {{ font-size:13px; font-weight:600; color:#93c5fd; }}
    #badge {{ margin-left:auto; font-size:11px; padding:3px 10px;
              border-radius:99px; background:#064e3b; color:#6ee7b7;
              border:1px solid #065f46; }}
    #badge.updating {{ background:#78350f; color:#fcd34d; border-color:#92400e; }}
    #scroll {{ flex:1; overflow-y:auto; display:flex;
               justify-content:center; padding:24px 16px; }}
    #scroll img {{ max-width:860px; width:100%; border-radius:4px;
                   box-shadow:0 8px 32px rgba(0,0,0,.6);
                   transition:opacity .15s; }}
    #scroll img.fading {{ opacity:0.35; }}
  </style>
</head>
<body>
  <div id="bar">
    <h1>ZivoPay — PDF Live Preview</h1>
    <span id="badge">v{v} &nbsp;Live</span>
  </div>
  {body_tag}
  <script>
    let current = {v};
    const badge = document.getElementById('badge');
    {img_js}
    async function poll() {{
      try {{
        const r = await fetch('/version');
        const d = await r.json();
        if (d.version !== current) {{
          current = d.version;
          badge.className = 'updating';
          badge.textContent = 'Updating...';
          {upd_js}
        }}
      }} catch(e) {{}}
      setTimeout(poll, 600);
    }}
    {onload_js}
    poll();
  </script>
</body>
</html>"""
    return html.encode()


# ── HTTP handler ───────────────────────────────────────────────────────────────

class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        p = self.path.split("?")[0]

        if p == "/":
            self._send(200, "text/html", _html())

        elif p == "/version":
            with _state["lock"]:
                v = _state["version"]
            self._send(200, "application/json", json.dumps({"version": v}).encode())

        elif p == "/img" and HAS_FITZ:
            img = _state.get("img_path")
            if img and os.path.exists(img):
                with open(img, "rb") as f:
                    self._send(200, "image/png", f.read())
            else:
                self._send(404, "text/plain", b"Image not ready")

        elif p == "/pdf":
            pdf = _state.get("pdf_path")
            if pdf and os.path.exists(pdf):
                with open(pdf, "rb") as f:
                    self._send(200, "application/pdf", f.read())
            else:
                self._send(404, "text/plain", b"PDF not ready")

        else:
            self._send(404, "text/plain", b"Not found")

    def _send(self, code, ct, body):
        try:
            self.send_response(code)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
            pass   # browser closed the connection early — safe to ignore


# ── Entry point ────────────────────────────────────────────────────────────────

PORT = 9000

if __name__ == "__main__":
    print("=" * 52)
    print("  ZivoPay PDF Live Preview")
    print("=" * 52)

    print("[PREVIEW] Generating initial PDF...")
    _regenerate()

    _start_auto_refresh(interval=2.0)
    _start_watcher()

    server = HTTPServer(("127.0.0.1", PORT), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    url = f"http://localhost:{PORT}"
    print(f"[PREVIEW] Open: {url}")
    print("[PREVIEW] Save pdf_generator.py to refresh.")
    print("[PREVIEW] Ctrl+C to stop.\n")
    webbrowser.open(url)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[PREVIEW] Stopped.")
        server.shutdown()
