"""
whatsapp_client.py
──────────────────
Sends messages and PDFs via the local Node.js Baileys server.
"""

import requests, json, base64, logging
from pathlib import Path

from phone_utils import normalize_phone

CONFIG_PATH = Path(__file__).parent.parent / "config" / "config.json"

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

CFG     = load_config()
BASE    = f"http://{CFG['nodejs_server']['host']}:{CFG['nodejs_server']['port']}"
HEADERS = {"x-api-key": CFG["nodejs_server"]["api_key"], "Content-Type": "application/json"}

logging.basicConfig(
    filename=str(Path(__file__).parent.parent / "logs" / "whatsapp.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

def is_server_online():
    try:
        r = requests.get(f"{BASE}/status", timeout=5)
        data = r.json()
        return data.get("connected", False)
    except Exception:
        return False

def format_message(template_key, **kwargs):
    """Fill message template from config with provided variables."""
    template = CFG["messages"].get(template_key, "")
    template = template.replace("{company_name}", CFG["marg"]["company_name"])
    for k, v in kwargs.items():
        template = template.replace(f"{{{k}}}", str(v))
    return template

def send_text(phone, message):
    """Send a plain text WhatsApp message."""
    phone = normalize_phone(phone)
    if len(phone) < 12:
        logging.error(f"TEXT SKIPPED — invalid phone after normalize: {phone}")
        return False
    try:
        r = requests.post(f"{BASE}/send-text", headers=HEADERS,
                          json={"phone": phone, "message": message}, timeout=30)
        result = r.json()
        if r.status_code == 200:
            jid = result.get("jid", phone)
            logging.info(f"TEXT SENT → {phone} (jid: {jid})")
            return True
        else:
            logging.error(f"TEXT FAILED → {phone}: {result}")
            return False
    except Exception as e:
        logging.error(f"TEXT EXCEPTION → {phone}: {e}")
        return False

def send_pdf(phone, pdf_path, filename=None, caption=""):
    """Send a PDF file as a WhatsApp document."""
    phone = normalize_phone(phone)
    if len(phone) < 12:
        logging.error(f"PDF SKIPPED — invalid phone after normalize: {phone}")
        return False
    try:
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            logging.error(f"PDF NOT FOUND: {pdf_path}")
            return False
        with open(pdf_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        fname = filename or pdf_path.name
        r = requests.post(f"{BASE}/send-pdf", headers=HEADERS,
                          json={"phone": phone, "pdf_base64": b64,
                                "filename": fname, "caption": caption}, timeout=60)
        result = r.json()
        if r.status_code == 200:
            jid = result.get("jid", phone)
            logging.info(f"PDF SENT → {phone} (jid: {jid}) | {fname}")
            return True
        else:
            logging.error(f"PDF FAILED → {phone}: {result}")
            return False
    except Exception as e:
        logging.error(f"PDF EXCEPTION → {phone}: {e}")
        return False

def send_bulk_texts(message_list):
    """
    Send bulk messages with auto-delay to avoid ban.
    message_list = [{"phone": "...", "message": "..."}, ...]
    """
    try:
        r = requests.post(f"{BASE}/send-bulk-text", headers=HEADERS,
                          json={"messages": message_list}, timeout=300)
        result = r.json()
        logging.info(f"BULK SENT: {len(message_list)} messages")
        return result.get("results", [])
    except Exception as e:
        logging.error(f"BULK EXCEPTION: {e}")
        return []
