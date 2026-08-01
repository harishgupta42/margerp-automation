"""
marg_db.py
──────────
Party and outstanding lookups for the scheduler.

Marg's own data files (D:/MARGERP/Data/order.aXX) are encrypted — verified by
reading the header, which holds no DBF signature or field names. Python can
never read them. Live bill data therefore arrives from the Marg hooks, and
anything else comes from a Marg export.

Requires: pip install dbfread fpdf2 requests schedule
"""

import json, logging
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

# Only plain exported DBFs are readable; the live Marg files are encrypted.
BILL_DBF        = DB_PATH / "PEND.DBF"
PENDINGS_DBF    = DB_PATH / "PENDINGS.DBF"


def read_dbf(filepath):
    """Read a plain exported .DBF; returns [] for encrypted Marg data files."""
    if not DBF_AVAILABLE:
        raise ImportError("Run: pip install dbfread")
    filepath = Path(filepath)
    if not filepath.exists():
        return []
    try:
        return [dict(record) for record in DBF(str(filepath), load=True, encoding="cp1252")]
    except Exception as e:
        logging.debug(f"DBF read skipped {filepath}: {e}")
        return []

def get_party_phone(party_code, party_name=None):
    """
    Fetch a party mobile outside the bill hook (used by the scheduler).

    The bill flow does not come here — the Marg hook already puts the mobile
    straight into bill_hook.txt. Marg's own data files (order.aXX) are
    encrypted, which leaves the party_mobile.csv ledger export as the only
    source, matched on party code or name.
    """
    if not party_code and not party_name:
        return None

    try:
        from party_mobile_export import lookup_party_mobile
        hit = lookup_party_mobile(party_code, party_name)
        if hit and hit.get("phone"):
            logging.info(f"Party mobile from export ({party_code or party_name}): {hit['phone']}")
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
