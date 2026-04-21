"""core/logo.py — Logo upload, background removal, resizing"""
import os
from PIL import Image
import io

LOGO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "logos")
os.makedirs(LOGO_DIR, exist_ok=True)


def process_logo(file_bytes, filename, remove_bg=True):
    """
    Process uploaded logo:
    - Remove background (if rembg installed)
    - Resize to max 512x512
    - Save as PNG
    Returns (success, saved_path, message)
    """
    try:
        img = Image.open(io.BytesIO(file_bytes))

        # Remove background
        if remove_bg:
            try:
                from rembg import remove as rembg_remove
                img_bytes = io.BytesIO()
                img.save(img_bytes, format="PNG")
                removed  = rembg_remove(img_bytes.getvalue())
                img      = Image.open(io.BytesIO(removed)).convert("RGBA")
            except ImportError:
                # rembg not installed — skip bg removal
                img = img.convert("RGBA")
        else:
            img = img.convert("RGBA")

        # Resize: max 512x512 keeping aspect ratio
        img.thumbnail((512, 512), Image.LANCZOS)

        # Save
        safe_name = os.path.splitext(filename)[0]
        safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in safe_name)
        out_path  = os.path.join(LOGO_DIR, f"{safe_name}.png")
        img.save(out_path, "PNG")

        return True, out_path, "Logo processed"

    except Exception as e:
        return False, "", str(e)


def get_logo_url(logo_path):
    """Convert absolute path to Flask static URL."""
    if not logo_path or not os.path.exists(logo_path):
        return None
    filename = os.path.basename(logo_path)
    return f"/static/logos/{filename}"
