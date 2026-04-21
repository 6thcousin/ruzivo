"""
ZivoPay Desktop — main.py
Entry point. Starts Flask in background thread, opens PyWebView window.
Falls back to browser if pywebview not installed.
"""

import threading
import time
import sys
import os

# ── Add app directory to path ─────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, PORT

def start_flask():
    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)

def main():
    # Start Flask in background
    t = threading.Thread(target=start_flask)
    t.daemon = True
    t.start()

    # Wait for Flask to boot
    time.sleep(1.2)

    url = f"http://127.0.0.1:{PORT}"

    try:
        import webview
        window = webview.create_window(
            title   = "ZivoPay AutoConfig",
            url     = url,
            width   = 1280,
            height  = 820,
            min_size= (960, 640),
            resizable    = True,
            frameless    = False,
            easy_drag    = False,
        )
        webview.start(debug=False)
    except ImportError:
        # PyWebView not installed — open in default browser
        import webbrowser
        webbrowser.open(url)
        print(f"\n  ZivoPay AutoConfig → {url}")
        print("  (Install pywebview for native window: pip install pywebview)\n")
        # Keep alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

if __name__ == "__main__":
    main()
