"""
Siganda Secondary School — Staff WiFi Onboarding Form
======================================================
Run:  python app.py
Open: http://localhost:5002
"""

import os
import random
import string
import httpx
from flask import Flask, render_template_string, request, flash

# ── CONFIG ────────────────────────────────────────────────────────────────────
ADMIN_NUMBERS     = ["263771478583", "263772129850"]
WHATSAPP_TOKEN    = os.environ.get("WA_TOKEN",    "your_meta_token_here")
WHATSAPP_PHONE_ID = os.environ.get("WA_PHONE_ID", "your_phone_number_id")
SECRET_KEY        = os.environ.get("SECRET_KEY",  "siganda-wifi-2026")
PORT              = int(os.environ.get("PORT",     5002))
# ─────────────────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = SECRET_KEY

DEPARTMENTS = [
    "Administration", "Science", "Mathematics", "English", "Shona / Ndebele",
    "Social Studies / History", "Geography", "Commerce / Accounts", "Agriculture",
    "Technical & Vocational", "Physical Education", "Art & Design", "ICT",
    "Library", "Support Staff", "Other",
]


def generate_user_id():
    """Generate a unique 6-character alphanumeric user ID e.g. SG-A3K7F2"""
    chars = string.ascii_uppercase + string.digits
    code = ''.join(random.choices(chars, k=6))
    return f"SG-{code}"


def send_whatsapp(to, user_id, full_name, department, phone, num_gadgets):
    """Send registration details to one WhatsApp number via Meta Cloud API."""
    message = (
        f"*Siganda Secondary — New WiFi Registration*\n\n"
        f"*User ID:*  {user_id}\n"
        f"*Name:*     {full_name}\n"
        f"*Dept:*     {department}\n"
        f"*Phone:*    {phone}\n"
        f"*Gadgets:*  {num_gadgets}"
    )
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message},
    }
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type":  "application/json",
    }
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"
    with httpx.Client(timeout=15) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()


TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Siganda Secondary — Staff WiFi</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css" rel="stylesheet">
  <style>
    :root { --green: #1a6b3c; --gold: #d4a017; }
    body  { background: #f0f4f0; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 1rem; }
    .card { border: none; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,.10); max-width: 480px; width: 100%; }
    .hdr  { background: var(--green); border-radius: 16px 16px 0 0; padding: 1.75rem 1.5rem 1.5rem; text-align: center; color: #fff; }
    .badge-pill { background: var(--gold); color: #1a1a1a; border-radius: 20px; padding: .3rem .9rem; font-size: .7rem; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }
    .hdr h4 { font-weight: 700; margin: .6rem 0 .2rem; }
    .hdr p  { font-size: .82rem; color: rgba(255,255,255,.75); margin: 0; }
    .wifi-icon { font-size: 2.4rem; color: var(--gold); }
    .form-label { font-weight: 600; font-size: .87rem; }
    .form-control, .form-select { border-radius: 8px; border: 1px solid #d1d5db; font-size: .9rem; }
    .form-control:focus, .form-select:focus { border-color: var(--green); box-shadow: 0 0 0 .2rem rgba(26,107,60,.15); }
    .btn-submit { background: var(--green); border: none; border-radius: 10px; font-weight: 700; font-size: .95rem; padding: .7rem; }
    .btn-submit:hover { background: #155230; }
    .footer-note { font-size: .72rem; color: #6b7280; text-align: center; padding: .75rem 1rem 1.25rem; }
    .uid-box { background: #f0fdf4; border: 2px dashed #86efac; border-radius: 10px; padding: .9rem 1rem; margin: 1rem 0; }
    .uid-box .uid-label { font-size: .72rem; color: #166534; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; }
    .uid-box .uid-value { font-size: 1.6rem; font-weight: 800; color: #15803d; letter-spacing: .12em; font-family: monospace; }
  </style>
</head>
<body>
<div class="card">
  <div class="hdr">
    <div class="wifi-icon"><i class="bi bi-wifi"></i></div>
    <span class="badge-pill">Staff WiFi Access</span>
    <h4>Siganda Secondary School</h4>
    <p>Complete the form below to register for staff WiFi.</p>
  </div>
  <div class="card-body px-4 py-4">

    {% with msgs = get_flashed_messages(with_categories=true) %}
      {% for cat, msg in msgs %}
      <div class="alert alert-{{ cat }} alert-dismissible rounded-3 mb-3 d-flex align-items-center gap-2">
        <i class="bi bi-{{ 'check-circle-fill' if cat == 'success' else 'exclamation-triangle-fill' }}"></i>
        <span>{{ msg }}</span>
        <button type="button" class="btn-close ms-auto" data-bs-dismiss="alert"></button>
      </div>
      {% endfor %}
    {% endwith %}

    {% if submitted %}
    <div class="text-center py-2">
      <div style="font-size:3rem;color:var(--green)"><i class="bi bi-check-circle-fill"></i></div>
      <h5 class="mt-3 fw-bold">Registration Sent!</h5>
      <p class="text-muted small mb-1">Your details have been forwarded to the ICT administrator.</p>
      {% if user_id %}
      <div class="uid-box">
        <div class="uid-label"><i class="bi bi-person-badge me-1"></i>Your User ID</div>
        <div class="uid-value">{{ user_id }}</div>
        <div class="text-muted" style="font-size:.72rem">Keep this ID — you may need it for support.</div>
      </div>
      {% endif %}
      <p class="text-muted small mt-2">You will be contacted on your phone with WiFi credentials.</p>
      <a href="/" class="btn btn-outline-success btn-sm rounded-pill px-4 mt-1">
        <i class="bi bi-arrow-left me-1"></i>Register Another
      </a>
    </div>
    {% else %}
    <form method="POST" action="/" id="f" novalidate>
      <div class="mb-3">
        <label class="form-label"><i class="bi bi-person-fill me-1 text-success"></i>Full Name <span class="text-danger">*</span></label>
        <input name="full_name" class="form-control" required placeholder="e.g. Tendai Moyo"
               value="{{ v.full_name or '' }}" autocomplete="name">
      </div>
      <div class="mb-3">
        <label class="form-label"><i class="bi bi-building me-1 text-success"></i>Department <span class="text-danger">*</span></label>
        <select name="department" class="form-select" required>
          <option value="" disabled {% if not v.department %}selected{% endif %}>— Select department —</option>
          {% for dept in departments %}
          <option {% if v.department == dept %}selected{% endif %}>{{ dept }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="mb-3">
        <label class="form-label"><i class="bi bi-phone-fill me-1 text-success"></i>Phone Number <span class="text-danger">*</span></label>
        <input name="phone" class="form-control" required type="tel"
               placeholder="e.g. 0771234567" value="{{ v.phone or '' }}" autocomplete="tel">
      </div>
      <div class="mb-4">
        <label class="form-label"><i class="bi bi-laptop me-1 text-success"></i>Number of Gadgets <span class="text-danger">*</span></label>
        <select name="num_gadgets" class="form-select" required>
          <option value="" disabled {% if not v.num_gadgets %}selected{% endif %}>— How many devices? —</option>
          {% for n in range(1, 7) %}
          <option {% if v.num_gadgets == n|string %}selected{% endif %}>{{ n }}</option>
          {% endfor %}
          <option {% if v.num_gadgets == '7+' %}selected{% endif %}>7+</option>
        </select>
      </div>
      <div class="d-grid">
        <button type="submit" class="btn btn-submit text-white">
          <i class="bi bi-send-fill me-2"></i>Submit Registration
        </button>
      </div>
    </form>
    {% endif %}

  </div>
  <div class="footer-note"><i class="bi bi-lock-fill me-1"></i>Your information is only shared with the school ICT administrator.</div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script>
document.getElementById('f')?.addEventListener('submit', function(e) {
  let ok = true;
  this.querySelectorAll('[required]').forEach(el => {
    el.classList.toggle('is-invalid', !el.value.trim());
    if (!el.value.trim()) ok = false;
  });
  if (!ok) e.preventDefault();
});
</script>
</body>
</html>"""


def render(submitted=False, user_id=None, v=None):
    return render_template_string(
        TEMPLATE,
        departments=DEPARTMENTS,
        submitted=submitted,
        user_id=user_id,
        v=v or {},
    )


@app.route("/", methods=["GET"])
def index():
    return render()


@app.route("/", methods=["POST"])
def register():
    full_name   = request.form.get("full_name",   "").strip()
    department  = request.form.get("department",  "").strip()
    phone       = request.form.get("phone",       "").strip()
    num_gadgets = request.form.get("num_gadgets", "").strip()

    if not all([full_name, department, phone, num_gadgets]):
        flash("All fields are required.", "danger")
        return render(v=request.form)

    user_id = generate_user_id()

    failed = []
    for number in ADMIN_NUMBERS:
        try:
            send_whatsapp(number, user_id, full_name, department, phone, num_gadgets)
        except Exception as exc:
            app.logger.error("WA send failed to %s: %s", number, exc)
            failed.append(number)

    if len(failed) == len(ADMIN_NUMBERS):
        flash("Notification failed — please contact ICT directly.", "warning")
    elif failed:
        flash("Registration sent, but one admin notification failed.", "warning")

    return render(submitted=True, user_id=user_id)


if __name__ == "__main__":
    print(f"  Siganda Staff WiFi Form  →  http://localhost:{PORT}")
    print(f"  Admins: {', '.join(ADMIN_NUMBERS)}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
