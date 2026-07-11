"""
Party mobile lookup from Marg ledger export (fallback when Marg data files are encrypted).

Export: Reports > Management Report > Utilities > Copy > Export My Database Mobile No
Save to: D:/MARGERP/HOOK_DATA/party_mobile.csv

Re-export when you add/change party mobiles in Ledger Master. Python auto-reloads
the file when its timestamp changes — no app restart needed.

Prefer live read: Marg HEADER END hook -> phone.txt (Marg reads ledger internally).
"""

import csv
import re
import logging
from pathlib import Path

_CACHE = None
_CODE_KEYS = ("code", "party code", "partycode", "ledger code", "a_code", "invo", "party", "ac code")
_PHONE_KEYS = ("mobile", "mob", "phone", "phone2", "mobileno", "mobile no", "mobile no.", "cell")


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "").strip().upper())


def _phone_digits(val):
    d = re.sub(r"\D", "", str(val or ""))
    return d if len(d) >= 10 else ""


def _load_export(path):
    global _CACHE
    path = Path(path)
    if not path.exists():
        return {}
    mtime = path.stat().st_mtime
    if _CACHE and _CACHE.get("path") == str(path) and _CACHE.get("mtime") == mtime:
        return _CACHE["data"]

    data = {}
    suffix = path.suffix.lower()
    rows = []

    if suffix == ".csv":
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
    elif suffix in (".txt", ".dat"):
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
        rows = [line.split("\t") if "\t" in line else line.split(",") for line in text.splitlines() if line.strip()]
    else:
        logging.debug(f"Party mobile export unsupported format: {path}")
        return {}

    if not rows:
        return {}

    header = [_norm(c) for c in rows[0]]
    code_idx = phone_idx = name_idx = None
    for i, h in enumerate(header):
        if any(k in h for k in _CODE_KEYS):
            code_idx = i
        if any(k in h for k in _PHONE_KEYS):
            phone_idx = i
        if "name" in h and name_idx is None:
            name_idx = i

    start = 1 if code_idx is not None or phone_idx is not None else 0
    if code_idx is None:
        code_idx = 0
    if phone_idx is None:
        phone_idx = 1 if len(header) > 1 else 0

    for row in rows[start:]:
        if not row or len(row) <= max(code_idx, phone_idx):
            continue
        code = _norm(row[code_idx])
        phone = _phone_digits(row[phone_idx])
        if not code or not phone:
            continue
        name = row[name_idx].strip() if name_idx is not None and len(row) > name_idx else ""
        data[code] = {"phone": phone, "name": name}
        data[code.replace(" ", "")] = {"phone": phone, "name": name}

    _CACHE = {"path": str(path), "mtime": mtime, "data": data}
    logging.info(f"Loaded {len(data)} party mobiles from {path.name}")
    return data


def lookup_party_mobile(party_code, export_path=None):
    if not party_code:
        return None
    if export_path is None:
        from marg_db import load_config
        export_path = load_config()["marg"].get(
            "party_mobile_export", "D:/MARGERP/HOOK_DATA/party_mobile.csv"
        )
    data = _load_export(export_path)
    if not data:
        return None

    targets = {_norm(party_code), _norm(party_code).replace(" ", "")}
    for t in targets:
        if t in data:
            return data[t]
    for code, info in data.items():
        if t in code or code in t:
            return info
    return None
