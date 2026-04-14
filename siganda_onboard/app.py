"""
Siganda Secondary School — Staff WiFi Onboarding Form
======================================================
Run:  python app.py
Open: http://localhost:5002

Configure the three variables below before deploying.
"""

import os
import httpx
from flask import Flask, render_template_string, request, redirect, url_for, flash

# ── CONFIG ────────────────────────────────────────────────────────────────────
ADMIN_WHATSAPP_NUMBER = os.environ.get("ADMIN_WA_NUMBER", "263771234567")  # E.164, no +
WHATSAPP_TOKEN        = os.environ.get("WA_TOKEN",        "your_meta_token_here")
WHATSAPP_PHONE_ID     = os.environ.get("WA_PHONE_ID",     "your_phone_number_id")  # from Meta dashboard
SECRET_KEY            = os.environ.get("SECRET_KEY",      "siganda-wifi-2026")
PORT                  = int(os.environ.get("PORT",         5002))
# ─────────────────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = SECRET_KEY

DEPARTMENTS = [
    "Administration",
    "Science",
    "Mathematics",
    "English",
    "Shona / Ndebele",
    "Social Studies / History",
    "Geography",
    "Commerce / Accounts",
    "Agriculture",
    "Technical & Vocational",
    "Physical Education",
    "Art & Design",
    "ICT",
    "Library",
    "Support Staff",
    "Other",
]

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Siganda Secondary — Staff WiFi</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css" rel="stylesheet">
  <style>
    :root { --school-green: #1a6b3c; --school-gold: #d4a017; }
    body  { background: #f0f4f0; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 1rem; }
    .card { border: none; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,.10); max-width: 480px; width: 100%; }
    .school-header {
      background: var(--school-green);
      border-radius: 16px 16px 0 0;
      padding: 1.75rem 1.5rem 1.5rem;
      text-align: center;
      color: #fff;
    }
    .school-header .badge-pill {
      background: var(--school-gold);
      color: #1a1a1a;
      border-radius: 20px;
      padding: .3rem .9rem;
      font-size: .7rem;
      font-weight: 700;
      letter-spacing: .06em;
      text-transform: uppercase;
    }
    .school-header h4 { font-weight: 700; margin: .6rem 0 .2rem; }
    .school-header p  { font-size: .82rem; color: rgba(255,255,255,.75); margin: 0; }
    .wifi-icon { font-size: 2.4rem; color: var(--school-gold); }
    .form-label { font-weight: 600; font-size: .87rem; }
    .form-control, .form-select {
      border-radius: 8px;
      border: 1px solid #d1d5db;
      font-size: .9rem;
    }
    .form-control:focus, .form-select:focus {
      border-color: var(--school-green);
      box-shadow: 0 0 0 .2rem rgba(26,107,60,.15);
    }
    .btn-submit {
      background: var(--school-green);
      border: none;
      border-radius: 10px;
      font-weight: 700;
      font-size: .95rem;
      padding: .7rem;
      letter-spacing: .02em;
    }
    .btn-submit:hover { background: #155230; }
    .footer-note { font-size: .72rem; color: #6b7280; text-align: center; padding: .75rem 1rem 1.25rem; }
    .step-indicator { display: flex; justify-content: center; gap: .4rem; margin-bottom: 1.2rem; }
    .step-dot { width: 8px; height: 8px; border-radius: 50%; background: rgba(255,255,255,.3); }
    .step-dot.active { background: var(--school-gold); }
  </style>
</head>
<body>

<div class="card">
  <div class="school-header">
    <div class="wifi-icon"><i class="bi bi-wifi"></i></div>
    <span class="badge-pill">Staff WiFi Access</span>
    <h4>Siganda Secondary School</h4>
    <p>Complete the form below to register for staff WiFi.</p>
  </div>

  <div class="card-body px-4 py-4">

    {% with msgs = get_flashed_messages(with_categories=true) %}
      {% for cat, msg in msgs %}
      <div class="alert alert-{{ cat }} alert-dismissible rounded-3 mb-3 d-flex align-items-center gap-2" role="alert">
        <i class="bi bi-{{ 'check-circle-fill' if cat == 'success' else 'exclamation-triangle-fill' }}"></i>
        <span>{{ msg }}</span>
        <button type="button" class="btn-close ms-auto" data-bs-dismiss="alert"></button>
      </div>
      {% endfor %}
    {% endwith %}

    {% if not submitted %}
    <form method="POST" action="{{ url_for('register') }}" id="onboard-form" novalidate>

      <div class="mb-3">
        <label class="form-label"><i class="bi bi-person-fill me-1 text-success"></i>Full Name <span class="text-danger">*</span></label>
        <input name="full_name" class="form-control" required placeholder="e.g. Tendai Moyo"
               value="{{ form_data.full_name if form_data else '' }}" autocomplete="name">
      </div>

      <div class="mb-3">
        <label class="form-label"><i class="bi bi-building me-1 text-success"></i>Department <span class="text-danger">*</span></label>
        <select name="department" class="form-select" required>
          <option value="" disabled {% if not form_data %}selected{% endif %}>— Select department —</option>
          {% for dept in departments %}
          <option value="{{ dept }}" {% if form_data and form_data.department == dept %}selected{% endif %}>{{ dept }}</option>
          {% endfor %}
        </select>
      </div>

      <div class="mb-3">
        <label class="form-label"><i class="bi bi-phone-fill me-1 text-success"></i>Phone Number <span class="text-danger">*</span></label>
        <input name="phone" class="form-control" required type="tel"
               placeholder="e.g. 0771234567"
               value="{{ form_data.phone if form_data else '' }}" autocomplete="tel">
        <div class="form-text">Enter your active mobile number.</div>
      </div>

      <div class="mb-4">
        <label class="form-label"><i class="bi bi-laptop me-1 text-success"></i>Number of Gadgets <span class="text-danger">*</span></label>
        <select name="num_gadgets" class="form-select" required>
          <option value="" disabled {% if not form_data %}selected{% endif %}>— How many devices? —</option>
          {% for n in range(1, 7) %}
          <option value="{{ n }}" {% if form_data and form_data.num_gadgets == n|string %}selected{% endif %}>{{ n }} device{% if n > 1 %}s{% endif %}</option>
          {% endfor %}
          <option value="7+" {% if form_data and form_data.num_gadgets == '7+' %}selected{% endif %}>7 or more</option>
        </select>
      </div>

      <div class="d-grid">
        <button type="submit" class="btn btn-submit text-white">
          <i class="bi bi-send-fill me-2"></i>Submit Registration
        </button>
      </div>

    </form>
    {% else %}
    <div class="text-center py-3">
      <div style="font-size:3.5rem; color:var(--school-green)"><i class="bi bi-check-circle-fill"></i></div>
      <h5 class="mt-3 fw-bold">Registration Sent!</h5>
      <p class="text-muted small">Your details have been forwarded to the ICT administrator. You will be contacted with your WiFi credentials.</p>
      <a href="{{ url_for('index') }}" class="btn btn-outline-success btn-sm rounded-pill px-4 mt-1">
        <i class="bi bi-arrow-left me-1"></i>Register Another
      </a>
    </div>
    {% endif %}

  </div>
  <div class="footer-note">
    <i class="bi bi-lock-fill me-1"></i>Your information is only shared with the school ICT administrator.
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script>
// Client-side validation highlight
document.getElementById('onboard-form')?.addEventListener('submit', function(e) {
  let ok = true;
  this.querySelectorAll('[required]').forEach(el => {
    if (!el.value.trim()) {
      el.classList.add('is-invalid'); ok = false;
    } else {
      el.classList.remove('is-invalid');
    }
  });
  if (!ok) e.preventDefault();
});
</script>
</body>
</html>
"""


def send_whatsapp(full_name, department, phone, num_gadgets):
    """Send staff registration details to admin WhatsApp via Meta Cloud API."""
    message = (
        f"*Siganda Secondary — WiFi Registration*\n\n"
        f"*Name:*     {full_name}\n"
        f"*Dept:*     {department}\n"
        f"*Phone:*    {phone}\n"
        f"*Gadgets:*  {num_gadgets}"
    )
    payload = {
        "messaging_product": "whatsapp",
        "to": ADMIN_WHATSAPP_NUMBER,
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
    return resp.json()


@app.route("/", methods=["GET"])
def index():
    return render_template_string(
        TEMPLATE,
        departments=DEPARTMENTS,
        submitted=False,
        form_data=None,
    )


@app.route("/register", methods=["POST"])
def register():
    full_name   = request.form.get("full_name",   "").strip()
    department  = request.form.get("department",  "").strip()
    phone       = request.form.get("phone",       "").strip()
    num_gadgets = request.form.get("num_gadgets", "").strip()

    # Basic server-side validation
    if not all([full_name, department, phone, num_gadgets]):
        flash("All fields are required. Please fill in the form completely.", "danger")
        return render_template_string(
            TEMPLATE,
            departments=DEPARTMENTS,
            submitted=False,
            form_data=request.form,
        )

    try:
        send_whatsapp(full_name, department, phone, num_gadgets)
    except httpx.HTTPStatusError as exc:
        app.logger.error("WhatsApp API error: %s — %s", exc.response.status_code, exc.response.text)
        flash("Submission received but WhatsApp notification failed. Please contact ICT directly.", "warning")
        return render_template_string(
            TEMPLATE,
            departments=DEPARTMENTS,
            submitted=True,
            form_data=None,
        )
    except Exception as exc:
        app.logger.error("WhatsApp send failed: %s", exc)
        flash("Could not reach the notification service. Your registration was noted locally.", "warning")
        return render_template_string(
            TEMPLATE,
            departments=DEPARTMENTS,
            submitted=True,
            form_data=None,
        )

    return render_template_string(
        TEMPLATE,
        departments=DEPARTMENTS,
        submitted=True,
        form_data=None,
    )


if __name__ == "__main__":
    print(f"  Siganda Staff WiFi Onboarding  →  http://localhost:{PORT}")
    print(f"  Admin WhatsApp: {ADMIN_WHATSAPP_NUMBER}")
    print(f"  Token set: {'YES' if WHATSAPP_TOKEN != 'your_meta_token_here' else 'NO — set WA_TOKEN env var'}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
