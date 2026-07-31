"""
Analyse the table dump written by the Marg discovery hook (marg_tables.txt)
and generate the FoxPro lookup code for the party mobile field.

Run after saving one bill with the discovery hook in HEADER END:
    python analyze_marg_tables.py
"""

import sys
import re
from pathlib import Path

DUMP_PATH = Path("D:/MARGERP/HOOK_DATA/marg_tables.txt")

# SCODE / PARNAM are the real Marg ledger field names (ORDER.A20)
CODE_FIELDS = ("SCODE", "CODE", "A_CODE", "AC_CODE", "PCOD", "ACODE", "LCODE", "MARGCODE")
PHONE_FIELDS = ("MOBILE", "MOB", "MOBILENO", "SMS", "SMSNO", "SMSMOB",
                "PHONE4", "PHONE3", "PHONE2", "PHONE1", "PHONE",
                "CELL", "WHATSAPP", "TELE", "TEL")
NAME_FIELDS = ("PARNAM", "NAME", "A_NAME", "PARTY_NAME", "CHEMI_NAME", "LNAME")


def parse_dump(path):
    """Each line: workarea|alias|reccount|dbfpath|FIELD1,FIELD2,..."""
    tables = []
    for line in path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        parts = line.split("|")
        if len(parts) < 5 or parts[0].strip().upper() == "WORKAREA":
            continue
        fields = [f.strip().upper() for f in parts[4].split(",") if f.strip()]
        if not fields:
            continue
        try:
            reccount = int(re.sub(r"\D", "", parts[2]) or 0)
        except ValueError:
            reccount = 0
        tables.append({
            "workarea": parts[0].strip(),
            "alias": parts[1].strip(),
            "reccount": reccount,
            "dbf": parts[3].strip(),
            "fields": fields,
        })
    return tables


def phone_fields_of(fields):
    """All phone-like fields, most likely mobile slot first."""
    found = [f for f in PHONE_FIELDS if f in fields]
    # PHONE1..PHONE4: Marg usually keeps the SMS mobile in a later slot
    numbered = sorted(
        (f for f in fields if re.fullmatch(r"PHONE\d", f)),
        key=lambda f: -int(f[-1]),
    )
    ordered = []
    for f in found + numbered:
        if f not in ordered:
            ordered.append(f)
    return ordered


def score_table(table):
    """Higher score = more likely to be the party/ledger master."""
    fields = set(table["fields"])
    code_hit = next((f for f in CODE_FIELDS if f in fields), None)
    phones = phone_fields_of(fields)
    name_hit = next((f for f in NAME_FIELDS if f in fields), None)

    if not phones:
        return 0, code_hit, phones, name_hit

    score = 10
    if code_hit:
        score += 20
    if name_hit:
        score += 10
    if table["reccount"] > 50:
        score += 5
    if "ORDER" in table["alias"].upper() or "LEDG" in table["alias"].upper():
        score += 10
    return score, code_hit, phones, name_hit


def build_hook(alias, code_field, phone_fields, name_field=None, debug=False):
    """FoxPro block: find the party row, then take the first valid mobile."""
    lines = [
        f'IF LEN(ALLTRIM(myv_phone))<10 AND USED("{alias}")',
        "  myv_area=SELECT()",
        f'  myv_rec=IIF(RECCOUNT("{alias}")>0,RECNO("{alias}"),0)',
        f"  SELECT {alias}",
    ]

    if code_field:
        lines.append(
            f"  LOCATE FOR UPPER(ALLTRIM({alias}.{code_field}))==UPPER(ALLTRIM(myv_code))"
        )
    if name_field:
        indent = "  " if not code_field else "  "
        if code_field:
            lines.append("  IF !FOUND()")
            indent = "    "
        lines.append(
            f"{indent}LOCATE FOR UPPER(ALLTRIM({alias}.{name_field}))==UPPER(ALLTRIM(myv_name))"
        )
        if code_field:
            lines.append("  ENDIF")

    field_list = ",".join(phone_fields)
    lines += [
        "  IF FOUND()",
        f'    myv_flds="{field_list}"',
        '    FOR ln_p=1 TO GETWORDCOUNT(myv_flds,",")',
        f'      myv_try=CHRTRAN(ALLTRIM(TRANSFORM(EVALUATE("{alias}."'
        '+GETWORDNUM(myv_flds,ln_p,",")))),"+- ()./,","")',
        "      IF LEN(myv_try)>=10",
        "        myv_try=RIGHT(myv_try,10)",
        '        IF LEFT(myv_try,1)$"6789"',
        "          myv_phone=myv_try",
        "          EXIT",
        "        ENDIF",
        "      ENDIF",
        "    ENDFOR",
    ]

    if debug:
        lines += [
            '    myv_dbg=""',
            '    FOR ln_p=1 TO GETWORDCOUNT(myv_flds,",")',
            '      myv_dbg=myv_dbg+GETWORDNUM(myv_flds,ln_p,",")+"="'
            f'+ALLTRIM(TRANSFORM(EVALUATE("{alias}."'
            '+GETWORDNUM(myv_flds,ln_p,","))))+"|"',
            "    ENDFOR",
            '    =strtofile(myv_dbg,"D:/MARGERP/HOOK_DATA/phone_debug.txt")',
        ]

    lines += [
        "  ENDIF",
        f'  IF myv_rec>0 AND myv_rec<=RECCOUNT("{alias}")',
        f"    GOTO myv_rec IN {alias}",
        "  ENDIF",
        "  SELECT (myv_area)",
        "ENDIF",
    ]
    return "\n".join(lines)


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DUMP_PATH
    if not path.exists():
        print(f"Dump not found: {path}\n")
        print("Paste the discovery hook (APPENDIX in MARG_HOOK_CODE.txt) into")
        print("Development Hook for HEADER END, then open a sale bill and")
        print("select a party. Re-run this script afterwards.")
        sys.exit(1)

    tables = parse_dump(path)
    if not tables:
        print(f"No tables parsed from {path} — dump may be empty or malformed.")
        sys.exit(1)

    print(f"Parsed {len(tables)} open Marg tables from {path.name}\n")

    scored = []
    for t in tables:
        score, code_f, phones, name_f = score_table(t)
        if score:
            scored.append((score, t, code_f, phones, name_f))
    scored.sort(key=lambda x: -x[0])

    if not scored:
        print("No open table has a mobile/phone-like field.")
        print("Party master is probably not open at this hook point.")
        print("Use the ledger CSV export instead (STEP E option 2).")
        sys.exit(1)

    print("Candidate party tables (best first):\n")
    for score, t, code_f, phones, name_f in scored[:8]:
        print(f"  [{score:3d}] {t['alias']:<15} recs={t['reccount']:<8} "
              f"code={code_f or '-':<8} name={name_f or '-':<10} "
              f"phones={','.join(phones) or '-'}")

    _, best, code_f, phones, name_f = scored[0]
    print()

    if not code_f and not name_f:
        print(f"Best table '{best['alias']}' has phone fields ({','.join(phones)}) "
              "but no code or name field to match on.")
        print("Field list:", ", ".join(best["fields"]))
        sys.exit(1)

    print(f"Party master: {best['alias']}  ({best['reccount']} records)")
    print(f"  match on : {code_f or '-'} (code), {name_f or '-'} (name)")
    print(f"  phones   : {', '.join(phones)}")
    print()
    print("=" * 72)
    print("Paste into FOOTER END, right after the existing myv_phone lines:")
    print("=" * 72)
    print(build_hook(best["alias"], code_f, phones, name_f, debug=True))
    print("=" * 72)
    print()
    print("It writes D:/MARGERP/HOOK_DATA/phone_debug.txt showing every phone")
    print("field for the matched party, so you can confirm which slot Marg uses.")


if __name__ == "__main__":
    main()
