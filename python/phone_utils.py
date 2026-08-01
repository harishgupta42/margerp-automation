"""Phone helpers for Marg hook integration."""

import re


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
