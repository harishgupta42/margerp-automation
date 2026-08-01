# Marg ERP → WhatsApp Automation

Send invoice PDFs from Marg ERP on bill save, with optional reorder/outstanding reminders.

**Status:** Bill send on save is working and delivers Marg's own invoice PDF. Scheduler reminders are planned.

## How the invoice PDF is obtained

Marg renders the real GST invoice as part of its own WhatsApp message flow and
queues it in `D:/MARGERP/emailserver` beside a CSV named after the bill. That
sidecar identifies which bill the PDF belongs to, so the right invoice is picked
up automatically with no keystrokes and no e-mail involved. Marg queues but never
delivers, so the customer is only messaged once, by us.

Leave Marg's WhatsApp bill message enabled — switching it off removes the PDF.
If no Marg PDF can be matched, a plain summary invoice is generated instead.

## Quick start

1. Copy `config/config.example.json` → `config/config.json` and edit paths, company name, API key, and sender JID.
2. Install dependencies:
   ```bat
   cd nodejs
   npm install
   cd ..\python
   pip install -r requirements.txt
   ```
3. Run `START_SERVER.bat` and scan the QR code (session stored locally in `nodejs/wa_session/` — not in git).
4. Paste Marg hooks from `MARG_HOOK_CODE.txt` (HEADER END + FOOTER END).
5. Save a bill in Marg → answer **Y** on the WhatsApp popup.

## What stays local (never committed)

| Path | Why |
|------|-----|
| `config/config.json` | API key, WhatsApp number, company name |
| `nodejs/wa_session/` | WhatsApp login session / crypto keys |
| `logs/`, `hook_data/` | Runtime logs may contain phone numbers |

## Repo visibility

Keep this repository **private** until:

- Scheduler and export workflows are stable
- You rotate the API key away from any test default
- You are comfortable publishing setup docs without business-specific paths

## Structure

```
config/           Settings (use config.example.json as template)
nodejs/           Baileys WhatsApp gateway
python/           Hook listener, scheduler, PDF helpers
MARG_HOOK_CODE.txt Marg FOOTER/HEADER hook snippets
trigger_bill.bat  Called by Marg on bill save
START_SERVER.bat  Start WhatsApp gateway
START_SCHEDULER.bat  Daily reminders (WIP) + nightly queue cleanup
```

The scheduler also clears Marg's message queue nightly, keeping 7 days. It only
ever matches `invoice*.pdf` and `*.csv`, so Marg's own extensionless data backups
in that folder are never touched. Run it on demand with
`python scheduler.py cleanup`.

## License

Private / internal use unless you choose to open-source later.
