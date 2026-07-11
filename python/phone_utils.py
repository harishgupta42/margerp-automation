"""Phone helpers for Marg hook integration."""

import re
from pathlib import Path


def read_saved_phone(hook_data_dir="D:/MARGERP/HOOK_DATA"):
    """Read phone.txt written by Marg HEADER END hook."""
    phone_file = Path(hook_data_dir) / "phone.txt"
    if not phone_file.exists():
        return ""
    phone = phone_file.read_text(encoding="utf-8-sig").strip()
    if phone and phone.upper() != "X" and len(phone) >= 10:
        return phone
    return ""


def normalize_phone(phone, default_country="91"):
    """
    9876543210  -> 919876543210
    919876543210 -> 919876543210
    +91 98765... -> 919876543210
    """
    digits = re.sub(r"\D", "", str(phone or ""))
    if not digits:
        return ""
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) == 10 and digits[0] in "6789":
        digits = default_country + digits
    return digits
