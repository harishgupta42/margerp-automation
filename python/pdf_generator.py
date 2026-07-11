"""
pdf_generator.py
────────────────
Generates a bill PDF from Marg bill data.
Uses fpdf2 — pip install fpdf2
For actual Marg bills: reads from Marg's own exported PDF folder.
"""

import os, base64, json
from pathlib import Path
from datetime import datetime

try:
    from fpdf import FPDF
    FPDF_AVAILABLE = True
except ImportError:
    FPDF_AVAILABLE = False

CONFIG_PATH = Path(__file__).parent.parent / "config" / "config.json"

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

CFG = load_config()

def get_marg_pdf_path(bill_no, wait_sec=0):
    """
    Marg can auto-save PDFs to a folder when printing.
    wait_sec: retry for PDF written slightly after bill save.
    """
    import time
    export_folder = Path(CFG["marg"]["bill_export_folder"])
    candidates = [
        export_folder / f"{bill_no}.pdf",
        export_folder / f"{bill_no.replace('/', '-')}.pdf",
        export_folder / f"INV{bill_no}.pdf",
    ]
    deadline = time.time() + max(0, float(wait_sec or 0))
    while True:
        for p in candidates:
            if p.exists():
                return p
        if time.time() >= deadline:
            break
        time.sleep(0.5)
    return None

def pdf_to_base64(pdf_path):
    """Convert a PDF file to base64 string for sending via API."""
    with open(pdf_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def generate_simple_invoice_pdf(bill_data):
    """
    Fallback: generate a simple invoice PDF using fpdf2
    when Marg's PDF export folder doesn't have the file.
    bill_data = { bill_no, bill_date, party_name, items: [...], total, gst, net_amount }
    """
    if not FPDF_AVAILABLE:
        raise ImportError("Run: pip install fpdf2")

    company = CFG["marg"]["company_name"]
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_margins(15, 15, 15)

    # Header
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_fill_color(37, 99, 235)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 12, company, ln=True, fill=True, align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    # Bill info
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(95, 7, f"Bill No: {bill_data.get('bill_no', '')}", border=0)
    pdf.cell(95, 7, f"Date: {bill_data.get('bill_date', '')}", border=0, align="R", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 7, f"Party: {bill_data.get('party_name', '')}", ln=True)
    pdf.ln(4)

    # Items table header
    pdf.set_fill_color(243, 244, 246)
    pdf.set_font("Helvetica", "B", 9)
    col_widths = [70, 25, 30, 30, 25]
    headers    = ["Item Name", "Qty", "Rate", "Amount", "GST%"]
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 8, h, border=1, fill=True, align="C")
    pdf.ln()

    # Items
    pdf.set_font("Helvetica", "", 9)
    for item in bill_data.get("items", []):
        pdf.cell(col_widths[0], 7, str(item.get("name", ""))[:35], border=1)
        pdf.cell(col_widths[1], 7, str(item.get("qty", "")),        border=1, align="C")
        pdf.cell(col_widths[2], 7, f"{float(item.get('rate',0)):,.2f}", border=1, align="R")
        pdf.cell(col_widths[3], 7, f"{float(item.get('amount',0)):,.2f}", border=1, align="R")
        pdf.cell(col_widths[4], 7, str(item.get("gst", "18")),      border=1, align="C")
        pdf.ln()

    # Totals
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(155, 7, "Sub Total:", align="R")
    pdf.cell(25, 7, f"Rs. {bill_data.get('total','0')}", ln=True, align="R")
    pdf.cell(155, 7, "GST:", align="R")
    pdf.cell(25, 7, f"Rs. {bill_data.get('gst_amount','0')}", ln=True, align="R")
    pdf.set_fill_color(37, 99, 235)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(155, 9, "NET AMOUNT:", fill=True, align="R")
    pdf.cell(25, 9, f"Rs. {bill_data.get('net_amount','0')}", fill=True, ln=True, align="R")

    # Footer
    pdf.set_text_color(0, 0, 0)
    pdf.ln(5)
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(0, 5, "Thank you for your business!", align="C", ln=True)

    output_path = Path(CFG["marg"]["bill_export_folder"]) / f"{bill_data.get('bill_no','BILL')}.pdf"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(output_path))
    return output_path
