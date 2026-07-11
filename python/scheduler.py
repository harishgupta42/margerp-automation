"""
scheduler.py
────────────
Daily scheduler for:
  1. Outstanding payment reminders (every morning at 9 AM)
  2. Reorder nudge reminders (every morning at 10 AM)

Run this script on startup via Windows Task Scheduler or as a service.
Command: python scheduler.py
"""

import schedule, time, logging, json
from pathlib import Path
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent))

from whatsapp_client import send_bulk_texts, is_server_online, format_message
from marg_db          import get_outstanding_parties, get_reorder_parties

CONFIG_PATH = Path(__file__).parent.parent / "config" / "config.json"
LOG_PATH    = Path(__file__).parent.parent / "logs" / "scheduler.log"

logging.basicConfig(
    filename=str(LOG_PATH), level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_PATH)),
        logging.StreamHandler()
    ]
)

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

# ── Outstanding Reminder Job ──────────────────────────────────
def send_outstanding_reminders():
    logging.info("=== OUTSTANDING REMINDER JOB STARTED ===")
    CFG = load_config()

    if not is_server_online():
        logging.error("WhatsApp server offline — skipping outstanding job")
        return

    parties = get_outstanding_parties(due_days=CFG["scheduler"]["outstanding_due_days"])
    logging.info(f"Found {len(parties)} parties with outstanding dues")

    if not parties:
        logging.info("No outstanding reminders to send today")
        return

    messages = []
    for p in parties:
        msg = format_message(
            "outstanding_message",
            party_name = p["party_name"],
            bill_no    = p["bill_no"],
            bill_date  = p["bill_date"],
            amount     = p["amount"],
            due_days   = p["due_days"],
        )
        messages.append({"phone": p["phone"], "message": msg})

    results = send_bulk_texts(messages)
    sent    = sum(1 for r in results if r.get("status") == "sent")
    failed  = len(results) - sent
    logging.info(f"Outstanding reminders: {sent} sent, {failed} failed")
    print(f"[{datetime.now():%H:%M}] Outstanding: {sent}/{len(parties)} sent")

# ── Reorder Reminder Job ──────────────────────────────────────
def send_reorder_reminders():
    logging.info("=== REORDER REMINDER JOB STARTED ===")
    CFG = load_config()

    if not is_server_online():
        logging.error("WhatsApp server offline — skipping reorder job")
        return

    parties = get_reorder_parties(days=CFG["scheduler"]["reorder_check_days"])
    logging.info(f"Found {len(parties)} parties due for reorder nudge")

    if not parties:
        logging.info("No reorder reminders to send today")
        return

    messages = []
    for p in parties:
        msg = format_message(
            "reorder_message",
            party_name  = p["party_name"],
            days_since  = p["days_since"],
            last_order  = p["last_order"],
        )
        messages.append({"phone": p["phone"], "message": msg})

    results = send_bulk_texts(messages)
    sent    = sum(1 for r in results if r.get("status") == "sent")
    failed  = len(results) - sent
    logging.info(f"Reorder reminders: {sent} sent, {failed} failed")
    print(f"[{datetime.now():%H:%M}] Reorder: {sent}/{len(parties)} sent")

# ── Manual trigger functions (call from CLI) ──────────────────
def run_outstanding_now():
    """python scheduler.py outstanding"""
    send_outstanding_reminders()

def run_reorder_now():
    """python scheduler.py reorder"""
    send_reorder_reminders()

# ── Scheduler setup ───────────────────────────────────────────
def start_scheduler():
    CFG = load_config()
    outstanding_time = CFG["scheduler"]["outstanding_reminder_time"]
    reorder_time     = CFG["scheduler"]["reorder_reminder_time"]

    schedule.every().day.at(outstanding_time).do(send_outstanding_reminders)
    schedule.every().day.at(reorder_time).do(send_reorder_reminders)

    logging.info(f"Scheduler started")
    logging.info(f"  Outstanding reminders at {outstanding_time} daily")
    logging.info(f"  Reorder reminders at {reorder_time} daily")
    print(f"✅ Scheduler running — Outstanding @ {outstanding_time} | Reorder @ {reorder_time}")
    print("   Press Ctrl+C to stop\n")

    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "outstanding":
            run_outstanding_now()
        elif cmd == "reorder":
            run_reorder_now()
        elif cmd == "test":
            print("Testing WhatsApp server connection...")
            print("Connected:", is_server_online())
        else:
            print(f"Unknown command: {cmd}")
            print("Usage: python scheduler.py [outstanding|reorder|test]")
    else:
        start_scheduler()
