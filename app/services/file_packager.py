import os
import zipfile


def create_invoice_zip(pdf_path: str, logo_path: str | None = None) -> str:
    """
    Package the generated PDF (and optionally the company logo) into a ZIP file.
    Returns the path to the created ZIP.
    """
    zip_path = pdf_path.replace(".pdf", ".zip")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add the PDF invoice
        zf.write(pdf_path, os.path.basename(pdf_path))

        # Add the logo if it was uploaded
        if logo_path and os.path.exists(logo_path):
            zf.write(logo_path, f"logo{os.path.splitext(logo_path)[1]}")

    print(f"[ZIP] Packaged: {zip_path}")
    return zip_path
