"""
Renders the Jinja2 hotspot login template for a specific client and
saves the output to generated/hotspot/<slug>/login.html.
"""
from pathlib import Path
import re
import unicodedata

from jinja2 import Environment, FileSystemLoader

_TEMPLATE_DIR = Path(__file__).parent.parent.parent / "hotspot"
_OUTPUT_DIR   = Path(__file__).parent.parent.parent / "generated" / "hotspot"


def _slug(name: str) -> str:
    """Turn a business name into a safe directory name."""
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"[^\w\s-]", "", name).strip().lower()
    return re.sub(r"[\s_-]+", "-", name)


def generate_hotspot_page(data: dict) -> Path:
    """
    Render login_template.html with client data and write the result.

    Expected keys in `data`:
      company_name      str   — e.g. "Cafe Harare"
      company_logo_url  str   — public URL to client logo (or "")
      wifi_name         str   — e.g. "CafeHarare_Free"
      voucher_location  str   — e.g. "At the counter or WhatsApp 0771234567"
      payment_modes     list  — subset of ["ecocash", "cash"]

    Returns the Path to the written login.html.
    """
    env      = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)))
    template = env.get_template("login_template.html")

    slug    = _slug(data["company_name"])
    out_dir = _OUTPUT_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    html     = template.render(**data)
    out_file = out_dir / "login.html"
    out_file.write_text(html, encoding="utf-8")

    return out_file
