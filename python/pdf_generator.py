"""
Search for Marg bill PDF and generate a fallback invoice when Marg has not exported one.
"""

import json
import time
import logging
from pathlib import Path

try:
    from fpdf import FPDF
    FPDF_AVAILABLE = True
except ImportError:
    FPDF_AVAILABLE = False

CONFIG_PATH = Path(__file__).parent.parent / "config" / "config.json"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _pdf_search_folders(cfg):
    marg = cfg.get("marg", {})
    folders = []
    for key in ("bill_export_folder", "pdf_export_folder"):
        p = marg.get(key)
        if p:
            folders.append(Path(p))
    for extra in marg.get("pdf_search_folders", []):
        if extra:
            folders.append(Path(extra))
    # de-dupe while preserving order
    seen, out = set(), []
    for folder in folders:
        s = str(folder).lower()
        if s not in seen:
            seen.add(s)
            out.append(folder)
    return out


def _bill_name_variants(bill_no):
    bill_no = str(bill_no or "").strip()
    if not bill_no:
        return []
    variants = {bill_no, bill_no.replace("/", "-"), bill_no.replace("\\", "-")}
    upper = bill_no.upper()
    variants.add(upper)
    variants.add(upper.replace("/", "-"))
    return [v for v in variants if v]


def _candidate_paths(folder, bill_no):
    folder = Path(folder)
    names = _bill_name_variants(bill_no)
    candidates = []
    for name in names:
        candidates.extend([
            folder / f"{name}.pdf",
            folder / f"INV{name}.pdf",
            folder / f"{name}.PDF",
        ])
    # glob partial match inside folder
    if folder.is_dir():
        for name in names:
            for hit in folder.glob(f"*{name}*.pdf"):
                candidates.append(hit)
            for hit in folder.glob(f"*{name}*.PDF"):
                candidates.append(hit)
    return candidates


def get_marg_pdf_path(bill_no, wait_sec=0):
    """
    Find Marg-exported PDF for bill_no.
    Retries until wait_sec elapses (Marg may write PDF just after save).
    """
    cfg = load_config()
    folders = _pdf_search_folders(cfg)
    deadline = time.time() + max(0, float(wait_sec or 0))
    newest_hit = None
    newest_mtime = 0

    while True:
        for folder in folders:
            for path in _candidate_paths(folder, bill_no):
                try:
                    if path.is_file():
                        mtime = path.stat().st_mtime
                        if mtime > newest_mtime:
                            newest_mtime = mtime
                            newest_hit = path
                except OSError:
                    continue

            # newest PDF in folder whose name contains bill no (last 2 min)
            if folder.is_dir():
                bill_upper = str(bill_no).upper()
                for path in folder.rglob("*.pdf"):
                    try:
                        if bill_upper not in path.stem.upper():
                            continue
                        mtime = path.stat().st_mtime
                        if wait_sec and time.time() - mtime > max(float(wait_sec), 120):
                            continue
                        if mtime > newest_mtime:
                            newest_mtime = mtime
                            newest_hit = path
                    except OSError:
                        continue

        if newest_hit:
            logging.info(f"Marg PDF found: {newest_hit}")
            return newest_hit

        if time.time() >= deadline:
            break
        time.sleep(0.5)

    logging.warning(f"Marg PDF not found for bill {bill_no} in {[str(f) for f in folders]}")
    return None


def pdf_to_base64(pdf_path):
    import base64
    with open(pdf_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def generate_simple_invoice_pdf(bill_data):
    """Fallback PDF when Marg export folder has no file for this bill."""
    if not FPDF_AVAILABLE:
        raise ImportError("Run: pip install fpdf2")

    cfg = load_config()
    company = cfg["marg"]["company_name"]
    bill_no = bill_data.get("bill_no", "")
    party_name = bill_data.get("party_name", "Customer")
    party_code = bill_data.get("party_code", "")
    amount = bill_data.get("total", bill_data.get("net_amount", "0"))
    bill_date = bill_data.get("bill_date", "")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_margins(15, 15, 15)

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_fill_color(37, 99, 235)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 12, company, ln=True, fill=True, align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "TAX INVOICE", ln=True, align="C")
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 10)
    rows = [
        ("Bill No", bill_no),
        ("Date", bill_date),
        ("Party", party_name),
        ("Party Code", party_code),
        ("Net Amount", f"Rs. {amount}"),
    ]
    for label, value in rows:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(40, 7, label + ":", border=0)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 7, str(value), ln=True, border=0)

    items = bill_data.get("items", [])
    if items:
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 9)
        col_widths = [70, 25, 30, 30, 25]
        headers = ["Item Name", "Qty", "Rate", "Amount", "GST%"]
        for i, h in enumerate(headers):
            pdf.cell(col_widths[i], 8, h, border=1, align="C")
        pdf.ln()
        pdf.set_font("Helvetica", "", 9)
        for item in items:
            pdf.cell(col_widths[0], 7, str(item.get("name", ""))[:35], border=1)
            pdf.cell(col_widths[1], 7, str(item.get("qty", "")), border=1, align="C")
            pdf.cell(col_widths[2], 7, f"{float(item.get('rate', 0)):,.2f}", border=1, align="R")
            pdf.cell(col_widths[3], 7, f"{float(item.get('amount', 0)):,.2f}", border=1, align="R")
            pdf.cell(col_widths[4], 7, str(item.get("gst", "18")), border=1, align="C")
            pdf.ln()
    else:
        pdf.ln(6)
        pdf.set_font("Helvetica", "I", 9)
        pdf.multi_cell(0, 5, "Note: Marg bill PDF was not found in the export folder. "
                             "This is a summary invoice generated by WhatsApp automation.")

    pdf.ln(6)
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(0, 5, "Thank you for your business!", align="C", ln=True)

    export_folder = Path(cfg["marg"]["bill_export_folder"])
    export_folder.mkdir(parents=True, exist_ok=True)
    safe_name = str(bill_no).replace("/", "-").replace("\\", "-")
    output_path = export_folder / f"{safe_name}.pdf"
    pdf.output(str(output_path))
    logging.info(f"Generated fallback PDF: {output_path}")
    return output_path
