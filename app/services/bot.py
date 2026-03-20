"""
ZivoPay WhatsApp Quotation & Invoice Bot
Flask webhook for Twilio WhatsApp API
"""

from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import os, re
from session_manager import SessionManager
from pdf_generator import generate_pdf

app = Flask(__name__)

TWILIO_ACCOUNT_SID     = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN      = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
session_mgr   = SessionManager()

# ── States ────────────────────────────────────────────────────────────────────
S_IDLE     = "idle"
S_TYPE     = "doc_type"
S_CNAME    = "client_name"
S_CEMAIL   = "client_email"
S_CPHONE   = "client_phone"
S_ITEMS    = "items"
S_MORE     = "add_more"
S_TERMS    = "payment_terms"
S_LEAD     = "lead_time"
S_BANKING  = "banking_details"
S_NOTES    = "notes"
S_CONFIRM  = "confirm"

MENU = (
    "👋 Welcome to *ZivoPay Billing Bot*!\n\n"
    "What would you like to create?\n"
    "1️⃣  Quotation\n"
    "2️⃣  Invoice\n\n"
    "Reply with *1* or *2*."
)


def next_response(session: dict, user_input: str) -> str:
    state = session.get("state", S_IDLE)
    inp   = user_input.strip()

    if state == S_IDLE or inp.lower() in ("hi","hello","start","menu","restart"):
        session["state"] = S_TYPE
        session["data"]  = {}
        return MENU

    # Choose doc type
    if state == S_TYPE:
        if inp == "1":   session["data"]["doc_type"] = "Quotation"
        elif inp == "2": session["data"]["doc_type"] = "Invoice"
        else: return "Please reply *1* for Quotation or *2* for Invoice."
        session["state"] = S_CNAME
        return "✅ Got it!\n\nWhat is the *client's full name or company name*?"

    # Client name
    if state == S_CNAME:
        if len(inp) < 2: return "Please enter a valid client name."
        session["data"]["client_name"] = inp.title()
        session["state"] = S_CEMAIL
        return "📧 Client's *email address*? (or type *skip*)"

    # Client email
    if state == S_CEMAIL:
        if inp.lower() != "skip":
            if not re.match(r"[^@]+@[^@]+\.[^@]+", inp):
                return "That doesn't look like a valid email. Try again or type *skip*."
            session["data"]["client_email"] = inp.lower()
        else:
            session["data"]["client_email"] = ""
        session["state"] = S_CPHONE
        return "📞 Client's *phone number*? (or type *skip*)"

    # Client phone
    if state == S_CPHONE:
        session["data"]["client_phone"] = "" if inp.lower() == "skip" else inp
        session["data"]["items"] = []
        session["state"] = S_ITEMS
        return (
            "🛒 Let's add line items.\n\n"
            "Send each item in this format:\n"
            "`Description | Qty | Unit Price`\n\n"
            "Example:\n"
            "`MikroTik Router Setup | 1 | 120.00`"
        )

    # Line items
    if state == S_ITEMS:
        parts = [p.strip() for p in inp.split("|")]
        if len(parts) != 3:
            return "⚠️ Format: `Description | Qty | Unit Price`\nExample: `WiFi Vouchers x100 | 1 | 50.00`"
        desc, qty_str, price_str = parts
        try:
            qty   = float(qty_str)
            price = float(price_str)
        except ValueError:
            return "⚠️ Qty and Unit Price must be numbers. Try again."
        item = {"description": desc, "qty": qty, "unit_price": price, "total": round(qty * price, 2)}
        session["data"]["items"].append(item)
        running = sum(i["total"] for i in session["data"]["items"])
        session["state"] = S_MORE
        return (
            f"✅ Added: *{desc}* — ${item['total']:.2f}\n"
            f"Running total: *${running:.2f}*\n\n"
            "Add another item? Reply *yes* or *no*."
        )

    # Add more
    if state == S_MORE:
        if inp.lower() in ("yes","y"):
            session["state"] = S_ITEMS
            return "Send the next item:\n`Description | Qty | Unit Price`"
        elif inp.lower() in ("no","n"):
            session["state"] = S_TERMS
            return (
                "💳 *Payment terms*?\n\n"
                "1 — Due on Receipt\n"
                "2 — Net 7 Days\n"
                "3 — Net 14 Days\n"
                "4 — Net 30 Days\n"
                "5 — Custom (type your own)"
            )
        return "Reply *yes* to add another item or *no* to continue."

    # Payment terms
    if state == S_TERMS:
        terms_map = {"1":"Due on Receipt","2":"Net 7 Days","3":"Net 14 Days","4":"Net 30 Days"}
        session["data"]["payment_terms"] = terms_map.get(inp, inp)
        session["state"] = S_LEAD
        return (
            "⏱ *Lead time / delivery time*?\n\n"
            "1 — Immediate\n"
            "2 — 3 Business Days\n"
            "3 — 5 Business Days\n"
            "4 — 7 Business Days\n"
            "5 — Custom (type your own)"
        )

    # Lead time
    if state == S_LEAD:
        lead_map = {"1":"Immediate","2":"3 Business Days","3":"5 Business Days","4":"7 Business Days"}
        session["data"]["lead_time"] = lead_map.get(inp, inp)
        session["state"] = S_BANKING
        return (
            "🏦 Enter your *banking details* to print on the document.\n\n"
            "Type them line by line, e.g.:\n"
            "Bank: ZB Bank\n"
            "Account Name: Zivopay Digital Services\n"
            "Account No: 1234567890\n"
            "EcoCash: 0771 000 000\n\n"
            "Or type *skip* to leave blank."
        )

    # Banking details
    if state == S_BANKING:
        session["data"]["banking_details"] = "" if inp.lower() == "skip" else inp
        session["state"] = S_NOTES
        return "📝 Any *notes or instructions* for the client? (or type *skip*)"

    # Notes
    if state == S_NOTES:
        session["data"]["notes"] = "" if inp.lower() == "skip" else inp
        session["state"] = S_CONFIRM

        d     = session["data"]
        items = d["items"]
        total = sum(i["total"] for i in items)
        lines = "\n".join(f"  • {i['description']} x{i['qty']} = ${i['total']:.2f}" for i in items)

        return (
            f"📄 *{d['doc_type']} Summary*\n"
            f"{'─'*30}\n"
            f"👤 Client: {d['client_name']}\n"
            f"📧 {d['client_email'] or 'No email'}\n"
            f"📞 {d['client_phone'] or 'No phone'}\n\n"
            f"🛒 Items:\n{lines}\n\n"
            f"💰 *Total: ${total:.2f} USD*\n"
            f"💳 Terms: {d['payment_terms']}\n"
            f"⏱ Lead Time: {d['lead_time']}\n"
            f"📝 Notes: {d['notes'] or 'None'}\n"
            f"{'─'*30}\n\n"
            "Reply *confirm* to generate the PDF, or *restart* to start over."
        )

    # Confirm
    if state == S_CONFIRM:
        if inp.lower() == "confirm":
            session["state"] = S_IDLE
            return "__GENERATE_PDF__"
        elif inp.lower() == "restart":
            session["state"] = S_IDLE
            session["data"]  = {}
            return MENU
        return "Reply *confirm* to generate the PDF or *restart* to start over."

    session["state"] = S_IDLE
    return MENU


@app.route("/webhook", methods=["POST"])
def webhook():
    incoming = request.form.get("Body", "").strip()
    sender   = request.form.get("From", "")
    session  = session_mgr.get(sender)
    reply    = next_response(session, incoming)
    session_mgr.save(sender, session)

    resp = MessagingResponse()
    if reply == "__GENERATE_PDF__":
        data     = session["data"]
        pdf_path = generate_pdf(data)
        pdf_url  = f"{os.environ.get('BASE_URL','http://localhost:5000')}/files/{os.path.basename(pdf_path)}"
        total    = sum(i["total"] for i in data["items"])
        resp.message(
            f"✅ Your *{data['doc_type']}* is ready!\n"
            f"Total: *${total:.2f} USD*\n\n"
            f"📥 Download: {pdf_url}\n\n"
            "Reply *hi* to create another document."
        )
    else:
        resp.message(reply)
    return str(resp)


@app.route("/files/<filename>")
def serve_file(filename):
    from flask import send_from_directory
    return send_from_directory("generated", filename)


if __name__ == "__main__":
    os.makedirs("generated", exist_ok=True)
    app.run(debug=True, port=5000)
