"""
hook_listener.py
────────────────
Marg ERP Hook Listener — triggered on every bill save via Self-Programming Hook.

Marg passes bill data via:
  1. Pipe file: bill_no|party_code|party_name|amount|phone|bill_date|send_yes
  2. CLI args: bill_no party_code amount phone [party_name]

send_mode in config.json:
  always   — send on every bill save (ignore Yes/No)
  yes_only — send only when send_yes is Y (integrate with Marg prompt)
"""

import sys, json, logging, time
from pathlib import Path
from datetime import datetime

LOG_PATH = Path(__file__).parent.parent / "logs" / "hooks.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(LOG_PATH), level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    force=True,
)

sys.path.insert(0, str(Path(__file__).parent))

from whatsapp_client import send_pdf, send_text, is_server_online, format_message
from pdf_generator   import get_marg_pdf_path, generate_simple_invoice_pdf
from phone_utils     import normalize_phone

CONFIG_PATH = Path(__file__).parent.parent / "config" / "config.json"

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def get_hook_data_path():
    cfg = load_config()
    primary = Path(cfg["marg"].get("hook_data_file", "D:/MARGERP/HOOK_DATA/bill_hook.txt"))
    if primary.exists():
        return primary
    fallback = Path(__file__).parent.parent / "hook_data" / "bill_hook.txt"
    if fallback.exists():
        return fallback
    return primary

def read_pipe_hook_file(filepath):
    """bill_no|party_code|party_name|amount|phone|bill_date|send_yes"""
    try:
        line = filepath.read_text(encoding="utf-8-sig").strip()
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 7:
            return {
                "bill_no":    parts[0],
                "party_code": parts[1],
                "party_name": parts[2],
                "amount":     parts[3],
                "phone":      parts[4],
                "bill_date":  parts[5],
                "send_yes":   parts[6],
            }
        if len(parts) >= 6:
            return {
                "bill_no":    parts[0],
                "party_code": parts[1],
                "party_name": parts[2],
                "amount":     parts[3],
                "phone":      parts[4],
                "bill_date":  parts[5],
            }
        if len(parts) >= 5:
            return {
                "bill_no":    parts[0],
                "party_code": parts[1],
                "party_name": parts[2],
                "amount":     parts[3],
                "bill_date":  parts[4],
            }
        if len(parts) >= 3:
            return {
                "bill_no":    parts[0],
                "party_code": parts[1],
                "amount":     parts[2],
                "bill_date":  datetime.now().strftime("%d/%m/%Y"),
            }
    except Exception as e:
        logging.error(f"Hook pipe read error: {e}")
    return None

def _parse_send_yes(val):
    v = str(val or "").strip().upper()
    return v in ("Y", "YES", "1", "S", "TRUE", "T")

def read_send_yes_flag(pipe_data=None):
    """
    True if the operator answered Yes to the popup in Marg's FOOTER hook.

    The answer rides in the last field of the pipe file, so anything that
    reaches here without one is treated as No rather than guessed at.
    """
    return bool(pipe_data) and _parse_send_yes(pipe_data.get("send_yes"))

def should_send_whatsapp(cfg, pipe_data=None):
    mode = str(cfg["marg"].get("send_mode", "yes_only")).strip().lower()
    if mode == "always":
        return True
    return read_send_yes_flag(pipe_data)

def read_hook_data():
    hook_data = get_hook_data_path()
    data = None

    if hook_data.exists():
        if hook_data.suffix.lower() == ".json":
            try:
                with open(hook_data, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                logging.error(f"Hook JSON read error: {e}")
        else:
            data = read_pipe_hook_file(hook_data)
            if data:
                logging.info(f"Hook data from Marg: bill={data.get('bill_no')} phone={data.get('phone','')}")

    if not data and len(sys.argv) >= 5:
        data = {
            "bill_no":    sys.argv[1],
            "party_code": sys.argv[2],
            "amount":     sys.argv[3],
            "phone":      sys.argv[4],
            "party_name": sys.argv[5] if len(sys.argv) > 5 else "Customer",
            "bill_date":  datetime.now().strftime("%d/%m/%Y"),
        }
    elif not data and len(sys.argv) >= 3:
        data = {
            "bill_no":    sys.argv[1],
            "party_code": sys.argv[2],
            "amount":     sys.argv[3] if len(sys.argv) > 3 else "0",
            "bill_date":  datetime.now().strftime("%d/%m/%Y"),
        }

    if not data or not str(data.get("bill_no", "")).strip() or str(data.get("bill_no", "")).strip() in ("0", "X"):
        return None

    phone = str(data.get("phone", "")).strip()
    if (not phone or len(phone) < 10) and (data.get("party_code") or data.get("party_name")):
        try:
            from marg_db import get_party_phone
            info = get_party_phone(data.get("party_code"), data.get("party_name"))
            if info and info.get("phone"):
                data["phone"] = info["phone"]
                logging.info(
                    f"Phone from ledger export "
                    f"({data.get('party_code') or data.get('party_name')}): {info['phone']}"
                )
        except Exception as e:
            logging.warning(f"Party mobile lookup failed for {data.get('party_code')}: {e}")

    phone = str(data.get("phone", "")).strip()
    if not phone or len(phone) < 10:
        export_path = Path(load_config()["marg"].get(
            "party_mobile_export", "D:/MARGERP/HOOK_DATA/party_mobile.csv"))
        logging.warning(
            f"No phone for party {data.get('party_code')} / {data.get('party_name')} — "
            f"party has no number in ledger PHONE1..PHONE4, or export mobiles "
            f"with code+name to {export_path}"
        )

    return data

def process_new_bill(bill_data):
    bill_no    = bill_data.get("bill_no", "")
    party_code = bill_data.get("party_code", "")
    amount     = bill_data.get("amount", "0")
    bill_date  = bill_data.get("bill_date", datetime.now().strftime("%d/%m/%Y"))

    if not bill_no or not str(bill_no).strip() or str(bill_no).strip() == "0":
        logging.warning("Bill number empty in Marg hook — use trim(invo) for bill no")
        return False

    logging.info(f"Hook triggered: Bill {bill_no}, Party {party_code}")

    phone      = normalize_phone(bill_data.get("phone", ""))
    party_name = str(bill_data.get("party_name", "") or "Customer")

    if not phone or len(phone) < 12:
        logging.warning("No phone in Marg hook — add the party's mobile in the ledger master")
        return False

    if not is_server_online():
        logging.error("WhatsApp server offline — message not sent")
        return False

    cfg = load_config()
    pdf_wait = float(cfg["marg"].get("pdf_wait_seconds", 0) or 0)
    # Marg's export keeps one fixed file name, so only a PDF written after the
    # bill was saved can belong to this bill. Marg writes it a few seconds
    # after this hook fires, so the slack only covers clock skew — keeping it
    # short stops a quick re-save from matching the previous version.
    try:
        pdf_path = get_marg_pdf_path(bill_no, wait_sec=pdf_wait,
                                     since_ts=time.time() - 10, amount=amount)
    except Exception as e:
        logging.exception(f"Marg PDF lookup failed for {bill_no}: {e}")
        pdf_path = None

    caption  = format_message("bill_message",
                              party_name=party_name, bill_no=bill_no,
                              bill_date=bill_date, amount=amount)
    filename = f"Invoice-{bill_no}.pdf"

    if pdf_path:
        if send_pdf(phone, pdf_path, filename=filename, caption=caption):
            return True
        # Marg can still hold the file open when the hook reaches it, so a
        # failed send here is worth one attempt with an invoice of our own
        # rather than leaving the customer with nothing.
        logging.warning(f"Could not send Marg's PDF for {bill_no} — "
                        f"falling back to a generated invoice")
    else:
        logging.info(f"Marg PDF not found for {bill_no}, generating fallback PDF")

    try:
        pdf_path = generate_simple_invoice_pdf({
            "bill_no":    bill_no,
            "bill_date":  bill_date,
            "party_name": party_name,
            "party_code": party_code,
            "items":      bill_data.get("items", []),
            "total":      amount,
            "gst_amount": bill_data.get("gst_amount", "0"),
            "net_amount": amount,
        })
    except Exception as e:
        logging.error(f"PDF generation failed: {e}")
        return send_text(phone, caption)

    return send_pdf(phone, pdf_path, filename=filename, caption=caption)

if __name__ == "__main__":
    cfg = load_config()
    delay = float(cfg["marg"].get("hook_delay_seconds", 0) or 0)
    if delay > 0:
        logging.info(f"Hook delay {delay}s (wait for Marg Send Message prompt)")
        time.sleep(delay)

    if len(sys.argv) > 1:
        logging.info(f"Hook argv: {sys.argv[1:]}")

    bill_data = read_hook_data()
    if bill_data:
        send_yes = bill_data.get("send_yes", "")
        if should_send_whatsapp(cfg, bill_data):
            logging.info(f"Send approved (send_yes={send_yes or 'file'})")
            success = process_new_bill(bill_data)
            logging.info(f"Hook result: {'SUCCESS' if success else 'FAILED'}")
        else:
            logging.info(f"Send skipped — operator chose No (send_yes={send_yes or 'N'})")
    else:
        logging.warning("Hook called but no bill data found")
    sys.exit(0)
