"""
marg_db.py
──────────
Reads Marg ERP data from exported CSV/DBF files or directly from
the Marg database folder. Marg stores data in FoxPro .DBF files.
Requires: pip install dbfread fpdf2 requests schedule
"""

import os, json, csv, re, logging
from pathlib import Path
from datetime import datetime, timedelta

try:
    from dbfread import DBF          # pip install dbfread
    DBF_AVAILABLE = True
except ImportError:
    DBF_AVAILABLE = False

CONFIG_PATH = Path(__file__).parent.parent / "config" / "config.json"

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

CFG = load_config()
DB_PATH = Path(CFG["marg"]["db_path"])

# Marg party master: ORDER.DBF (standalone) or order.a20 (client/server, often encrypted)
BILL_DBF        = DB_PATH / "PEND.DBF"
LEDGER_DBF      = DB_PATH / "ORDER.DBF"
PENDINGS_DBF    = DB_PATH / "PENDINGS.DBF"


def _marg_data_year_suffix():
    """Current FY data file suffix e.g. a20 — from config or newest order.a*."""
    configured = CFG["marg"].get("data_year_suffix", "").strip().lower()
    if configured:
        return configured
    if not DB_PATH.is_dir():
        return None
    candidates = sorted(DB_PATH.glob("order.a*"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0].suffix[1:].lower() if candidates else None


def _ledger_data_paths():
    paths = [LEDGER_DBF]
    year = _marg_data_year_suffix()
    if year:
        paths.append(DB_PATH / f"order.{year}")
    return paths


def _is_marg_encrypted_data(path):
    """Marg client/server files use proprietary encryption (first byte 0x19, not DBF 0x03)."""
    try:
        return path.exists() and path.read_bytes()[:1] == b"\x19"
    except OSError:
        return False


def read_dbf(filepath):
    """Read a plain .DBF / readable Marg data file; return list of dicts."""
    if not DBF_AVAILABLE:
        raise ImportError("Run: pip install dbfread")
    filepath = Path(filepath)
    records = []
    if not filepath.exists():
        return records
    if _is_marg_encrypted_data(filepath):
        logging.debug(
            f"Marg data encrypted — cannot read {filepath.name} from Python "
            f"(use HEADER END hook phone.txt or party_mobile.csv export)"
        )
        return records
    try:
        table = DBF(str(filepath), load=True, encoding="cp1252")
        for record in table:
            records.append(dict(record))
    except Exception as e:
        logging.debug(f"DBF read skipped {filepath}: {e}")
    return records

def get_party_phone(party_code):
    """
    Fetch mobile from party master.

    Priority (always live / no manual Python refresh):
      1. phone.txt from Marg HEADER END hook (Marg reads ledger internally)
      2. Plain ORDER.DBF / order.aXX if not encrypted (standalone Marg)

    Fallback (file must exist; re-export from Marg when party mobiles change):
      3. party_mobile.csv from Export My Database Mobile No
    """
    if not party_code:
        return None

    try:
        from phone_utils import read_saved_phone
        saved = read_saved_phone()
        if saved:
            logging.info(f"Party mobile from Marg hook phone.txt ({party_code}): {saved}")
            return {"phone": saved, "name": ""}
    except Exception as e:
        logging.debug(f"Marg hook phone.txt skipped: {e}")

    target = str(party_code).strip().upper()
    for ledger_path in _ledger_data_paths():
        if not ledger_path.exists():
            continue
        if _is_marg_encrypted_data(ledger_path):
            logging.debug(f"Direct read blocked: {ledger_path.name} is Marg-encrypted")
            continue
        try:
            for p in read_dbf(ledger_path):
                codes = [
                    str(p.get(k, "")).strip().upper()
                    for k in ("CODE", "A_CODE", "INVO", "INVOICE", "PARTY", "AC_CODE", "PCOD")
                ]
                if target in codes or any(target in c for c in codes if c):
                    phone = str(p.get("MOBILE", p.get("MOB", p.get("PHONE2", p.get("PHONE", p.get("MOBILENO", "")))))).strip()
                    name = str(p.get("NAME", p.get("A_NAME", ""))).strip()
                    if phone:
                        logging.info(f"Party mobile from {ledger_path.name} ({party_code}): {phone}")
                        return {"phone": phone, "name": name}
        except Exception as e:
            logging.debug(f"Ledger read skipped {ledger_path}: {e}")

    try:
        from party_mobile_export import lookup_party_mobile
        hit = lookup_party_mobile(party_code)
        if hit and hit.get("phone"):
            logging.info(f"Party mobile from export ({party_code}): {hit['phone']}")
            return hit
    except Exception as e:
        logging.debug(f"Party export lookup skipped: {e}")

    return None

def get_outstanding_parties(due_days=None):
    """
    Return list of parties with outstanding > due_days old.
    Uses PENDINGS.DBF or PEND.DBF.
    """
    due_days = due_days or CFG["scheduler"]["outstanding_due_days"]
    cutoff   = datetime.now() - timedelta(days=due_days)
    results  = []

    try:
        records = read_dbf(PENDINGS_DBF)
        for r in records:
            bill_date = r.get("DATE", r.get("B_DATE"))
            amount    = float(r.get("AMOUNT", r.get("NET", r.get("BALANCE", 0))) or 0)
            if amount <= 0:
                continue
            if bill_date and isinstance(bill_date, datetime):
                if bill_date < cutoff:
                    party_code = str(r.get("CODE", r.get("A_CODE", ""))).strip()
                    party_info = get_party_phone(party_code)
                    if party_info and party_info["phone"]:
                        due_days_count = (datetime.now() - bill_date).days
                        results.append({
                            "party_code": party_code,
                            "party_name": party_info["name"],
                            "phone":      party_info["phone"],
                            "bill_no":    str(r.get("BILLNO", r.get("B_NO", ""))).strip(),
                            "bill_date":  bill_date.strftime("%d/%m/%Y"),
                            "amount":     f"{amount:,.2f}",
                            "due_days":   due_days_count,
                        })
    except Exception as e:
        print(f"[OUTSTANDING ERROR] {e}")
    return results

def get_reorder_parties(days=None):
    """
    Return parties whose last bill was more than 'days' days ago.
    Reads from PEND.DBF and groups by party to find last sale date.
    """
    days = days or CFG["scheduler"]["reorder_check_days"]
    cutoff = datetime.now() - timedelta(days=days)
    last_order = {}

    try:
        records = read_dbf(BILL_DBF)
        for r in records:
            party_code = str(r.get("CODE", r.get("A_CODE", ""))).strip()
            bill_date  = r.get("DATE", r.get("B_DATE"))
            if bill_date and isinstance(bill_date, datetime):
                if party_code not in last_order or bill_date > last_order[party_code]["date"]:
                    last_order[party_code] = {"date": bill_date, "record": r}
    except Exception as e:
        print(f"[REORDER READ ERROR] {e}")

    results = []
    for party_code, info in last_order.items():
        if info["date"] < cutoff:
            party_info = get_party_phone(party_code)
            if party_info and party_info["phone"]:
                days_since = (datetime.now() - info["date"]).days
                results.append({
                    "party_code":  party_code,
                    "party_name":  party_info["name"],
                    "phone":       party_info["phone"],
                    "last_order":  info["date"].strftime("%d/%m/%Y"),
                    "days_since":  days_since,
                })
    return results


# ── CSV fallback (if you export from Marg manually) ───────────
def read_outstanding_from_csv(csv_path):
    """
    Fallback: read from a CSV you exported from Marg
    (Reports → Outstanding → Export to Excel/CSV).
    Expected columns: PartyName, Phone, BillNo, BillDate, Amount
    """
    results = []
    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                amount_str = re.sub(r"[^\d.]", "", str(row.get("Amount", "0")))
                amount = float(amount_str) if amount_str else 0
                if amount > 0:
                    results.append({
                        "party_name": row.get("PartyName", "").strip(),
                        "phone":      row.get("Phone", "").strip(),
                        "bill_no":    row.get("BillNo", "").strip(),
                        "bill_date":  row.get("BillDate", "").strip(),
                        "amount":     f"{amount:,.2f}",
                        "due_days":   0,
                    })
    except Exception as e:
        print(f"[CSV READ ERROR] {e}")
    return results
