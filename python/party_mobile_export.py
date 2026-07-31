"""
Party mobile lookup from a Marg ledger export.

Marg data files (order.aXX) are encrypted, so Python cannot read the party master
directly. Export the ledger list once and this module resolves a mobile number
from either the party CODE or the party NAME that the bill hook sends.

Export in Marg:
    Books > All Ledgers > Alt+P > Contact-Y/Address = Yes > Excel
    Save as CSV to: D:/MARGERP/HOOK_DATA/party_mobile.csv

The file reloads automatically when its timestamp changes.
"""

import csv
import re
import logging
from pathlib import Path

_CACHE = None

_CODE_KEYS = (
    "code", "party code", "partycode", "ledger code", "a_code", "ac code", "a/c code",
    "invo", "ac_code", "pcod", "short name", "acode",
)
_PHONE_KEYS = (
    "mobile", "mob", "phone", "phone2", "mobileno", "mobile no", "mobile no.",
    "cell", "sms", "telephone", "tel", "contact", "whatsapp",
)
_NAME_KEYS = ("name", "party", "ledger", "particular", "account")

# Columns present in "Export My Database Mobile No" (mobiles only, unusable for lookup)
_MOBILE_ONLY_COLUMNS = {"mobile", "state", "area", "network", "repeate", ""}


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "").strip().upper())


def _norm_name(s):
    """Normalise a party name for fuzzy matching: drop punctuation and extra spaces."""
    text = _norm(s)
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _phone_digits(val):
    d = re.sub(r"\D", "", str(val or ""))
    if len(d) > 10 and d.startswith("91"):
        d = d[2:]
    return d if len(d) >= 10 else ""


def _read_rows(path):
    suffix = path.suffix.lower()

    if suffix == ".csv":
        with open(path, newline="", encoding="utf-8-sig", errors="ignore") as f:
            return list(csv.reader(f))

    if suffix in (".txt", ".dat", ".tsv"):
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
        return [
            line.split("\t") if "\t" in line else line.split(",")
            for line in text.splitlines() if line.strip()
        ]

    if suffix == ".dbf":
        try:
            from dbfread import DBF
        except ImportError:
            logging.error("Reading .dbf export needs dbfread — run: pip install dbfread")
            return []
        table = DBF(str(path), load=True, encoding="cp1252", ignore_missing_memofile=True)
        rows = [list(table.field_names)]
        rows.extend([list(rec.values()) for rec in table])
        return rows

    if suffix in (".xls", ".xlsx"):
        logging.error(
            f"{path.name} is an Excel file — open it in Excel and use "
            "'Save As > CSV (Comma delimited)' with the same name."
        )
        return []

    logging.error(f"Unsupported party mobile export format: {path.name}")
    return []


def _find_columns(header):
    code_idx = phone_idx = name_idx = None
    for i, raw in enumerate(header):
        h = raw.lower()
        if code_idx is None and any(k in h for k in _CODE_KEYS):
            code_idx = i
        if phone_idx is None and any(k in h for k in _PHONE_KEYS):
            phone_idx = i
        if name_idx is None and any(k in h for k in _NAME_KEYS):
            name_idx = i
    return code_idx, phone_idx, name_idx


def _load_export(path):
    """Return {"by_code": {...}, "by_name": {...}} built from the export file."""
    global _CACHE
    path = Path(path)
    empty = {"by_code": {}, "by_name": {}}

    if not path.exists():
        logging.warning(f"Party mobile export not found: {path}")
        return empty

    mtime = path.stat().st_mtime
    if _CACHE and _CACHE.get("path") == str(path) and _CACHE.get("mtime") == mtime:
        return _CACHE["data"]

    rows = _read_rows(path)
    if not rows:
        return empty

    header = [_norm(c) for c in rows[0]]
    code_idx, phone_idx, name_idx = _find_columns(header)

    if phone_idx is None:
        logging.warning(f"{path.name} has no mobile/phone column — check the export.")
        return empty

    if code_idx is None and name_idx is None:
        if all(h.lower() in _MOBILE_ONLY_COLUMNS for h in header):
            logging.warning(
                f"{path.name} lists mobile numbers only, with no party code or name. "
                "Re-export: Books > All Ledgers > Alt+P > Contact-Y/Address = Yes > Excel, "
                "then save as CSV."
            )
        else:
            logging.warning(f"{path.name} has no party code or name column — cannot match parties.")
        return empty

    by_code, by_name = {}, {}
    for row in rows[1:]:
        if not row or len(row) <= phone_idx:
            continue
        phone = _phone_digits(row[phone_idx])
        if not phone:
            continue

        name = str(row[name_idx]).strip() if name_idx is not None and len(row) > name_idx else ""
        code = _norm(row[code_idx]) if code_idx is not None and len(row) > code_idx else ""
        entry = {"phone": phone, "name": name, "code": code}

        if code:
            by_code.setdefault(code, entry)
            by_code.setdefault(code.replace(" ", ""), entry)
        if name:
            key = _norm_name(name)
            if key:
                by_name.setdefault(key, entry)

    data = {"by_code": by_code, "by_name": by_name}
    _CACHE = {"path": str(path), "mtime": mtime, "data": data}
    logging.info(
        f"Loaded party mobiles from {path.name}: "
        f"{len(by_code)} code keys, {len(by_name)} name keys"
    )
    return data


def _match_by_name(by_name, party_name):
    """Exact match first, then containment, then first-two-words match."""
    target = _norm_name(party_name)
    if not target or not by_name:
        return None

    if target in by_name:
        return by_name[target]

    for key, entry in by_name.items():
        if key == target:
            return entry

    candidates = [e for k, e in by_name.items() if target in k or k in target]
    if len(candidates) == 1:
        return candidates[0]

    words = target.split()
    if len(words) >= 2:
        prefix = " ".join(words[:2])
        candidates = [e for k, e in by_name.items() if k.startswith(prefix)]
        if len(candidates) == 1:
            return candidates[0]

    return None


def lookup_party_mobile(party_code, party_name=None, export_path=None):
    """Resolve a party mobile from the export by code, falling back to name."""
    if not party_code and not party_name:
        return None

    if export_path is None:
        from marg_db import load_config
        export_path = load_config()["marg"].get(
            "party_mobile_export", "D:/MARGERP/HOOK_DATA/party_mobile.csv"
        )

    data = _load_export(export_path)
    by_code, by_name = data["by_code"], data["by_name"]
    if not by_code and not by_name:
        return None

    if party_code:
        target = _norm(party_code)
        for key in (target, target.replace(" ", "")):
            if key in by_code:
                return by_code[key]

    if party_name:
        hit = _match_by_name(by_name, party_name)
        if hit:
            logging.info(f"Party matched by name '{party_name}' -> {hit['phone']}")
            return hit

    return None
