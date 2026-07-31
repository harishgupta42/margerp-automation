"""
Verify Marg WhatsApp automation prerequisites.

Usage:
    python setup_check.py                 (uses the last saved bill)
    python setup_check.py WAD             (test a specific party code)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from marg_db import load_config
from party_mobile_export import lookup_party_mobile, _load_export
from whatsapp_client import is_server_online


def read_last_bill(hook_file):
    """bill_no|party_code|party_name|amount|phone|bill_date|send_yes"""
    if not hook_file.exists():
        return None
    parts = [p.strip() for p in hook_file.read_text(encoding="utf-8-sig").strip().split("|")]
    if len(parts) < 5:
        return None
    return {"bill_no": parts[0], "party_code": parts[1],
            "party_name": parts[2], "phone": parts[4]}


def main():
    cfg = load_config()
    marg = cfg["marg"]
    issues, ok, notes = [], [], []

    config_path = Path(__file__).parent.parent / "config" / "config.json"
    if config_path.exists():
        ok.append("config.json found")
    else:
        issues.append("config.json missing - copy config.example.json")

    if is_server_online():
        ok.append("WhatsApp server online")
    else:
        issues.append("WhatsApp server offline - run START_SERVER.bat and keep it open")

    pdf_folder = Path(marg.get("bill_export_folder", "D:/MARGERP/EXPORT/BILLS/"))
    if pdf_folder.is_dir():
        ok.append(f"PDF folder exists ({len(list(pdf_folder.glob('*.pdf')))} files): {pdf_folder}")
    else:
        issues.append(f"PDF folder missing: {pdf_folder}")

    # The FOOTER hook puts the mobile straight into the bill line - the path
    # that actually matters. Everything below it is only a fallback.
    hook_file = Path(marg.get("hook_data_file", "D:/MARGERP/HOOK_DATA/bill_hook.txt"))
    last_bill = read_last_bill(hook_file)
    if not last_bill:
        issues.append(f"bill_hook.txt not found or empty: {hook_file}")
    else:
        label = f"{last_bill['bill_no']} ({last_bill['party_code']} / {last_bill['party_name']})"
        if len(last_bill["phone"]) >= 10:
            ok.append(f"Last bill carried a mobile: {label} -> {last_bill['phone']}")
        else:
            issues.append(f"Last bill had no mobile: {label}")
            issues.append("  -> check the FOOTER END hook, or the party has no "
                          "number in PHONE1..PHONE4")

    phone_txt = Path("D:/MARGERP/HOOK_DATA/phone.txt")
    if phone_txt.exists() and len(phone_txt.read_text(encoding="utf-8-sig").strip()) >= 10:
        notes.append(f"HEADER hook active, phone.txt = {phone_txt.read_text(encoding='utf-8-sig').strip()}")
    else:
        notes.append("HEADER hook not installed (optional - FOOTER handles the lookup)")

    export_csv = Path(marg.get("party_mobile_export", "D:/MARGERP/HOOK_DATA/party_mobile.csv"))
    data = _load_export(export_csv) if export_csv.exists() else {"by_code": {}, "by_name": {}}
    if data["by_code"] or data["by_name"]:
        ok.append(f"Ledger export loaded: {len(data['by_code'])} codes, "
                  f"{len(data['by_name'])} names ({export_csv.name})")
        test_code = sys.argv[1] if len(sys.argv) > 1 else (last_bill or {}).get("party_code", "WAD")
        test_name = None if len(sys.argv) > 1 else (last_bill or {}).get("party_name")
        hit = lookup_party_mobile(test_code, test_name)
        label = test_code + (f" / {test_name}" if test_name else "")
        notes.append(f"Export lookup {label} -> {hit['phone'] if hit else 'no match'}")
    else:
        notes.append("No ledger export - only needed for reorder reminders, not for bills")
        notes.append("  Books > All Ledgers > Alt+P > Contact-Y/Address = Yes > Excel,"
                     " save as CSV with Code/Name + Mobile columns")

    print("=== Marg WhatsApp Setup Check ===\n")
    for line in ok:
        print(f"OK    {line}")
    for line in issues:
        print(f"FAIL  {line}")
    for line in notes:
        print(f"info  {line}")

    print()
    if issues:
        print(f"Fix {len(issues)} issue(s) above, then save a test bill and answer Y.")
        sys.exit(1)
    print("All checks passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
