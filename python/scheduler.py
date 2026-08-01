"""
scheduler.py
────────────
Daily scheduler for:
  1. Outstanding payment reminders (every morning at 9 AM)
  2. Reorder nudge reminders (every morning at 10 AM)
  3. Clearing old invoices out of Marg's message queue (late evening)

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
from pdf_generator    import expand_folder

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

# ── Message Queue Cleanup Job ─────────────────────────────────
# Marg queues an invoice and a CSV per bill for its own WhatsApp service and
# never clears them, so the folder grows by about 82 KB per bill. Only that
# pair is removed: the same folder holds Marg's own data backups, which have no
# file extension and are deliberately left out of these patterns.
QUEUE_PATTERNS = ("invoice*.pdf", "*.csv")


def clean_message_queue():
    logging.info("=== MESSAGE QUEUE CLEANUP STARTED ===")
    CFG = load_config()

    folders = []
    for pattern in CFG["marg"].get("message_queue_folders", []):
        folders.extend(expand_folder(pattern))
    if not folders:
        logging.info("No marg.message_queue_folders configured — nothing to clean")
        return

    keep_days = float(CFG["scheduler"].get("queue_keep_days", 7))
    # Anything younger than this could still belong to a bill being saved now.
    cutoff = time.time() - keep_days * 86400
    removed, freed, failed = 0, 0, 0

    for folder in folders:
        if not folder.is_dir():
            logging.warning(f"Queue folder missing: {folder}")
            continue
        for pattern in QUEUE_PATTERNS:
            for path in folder.glob(pattern):
                try:
                    stat = path.stat()
                    if stat.st_mtime >= cutoff:
                        continue
                    size = stat.st_size
                    path.unlink()
                except OSError as e:
                    failed += 1
                    logging.warning(f"Could not delete {path}: {e}")
                    continue
                removed += 1
                freed += size

    logging.info(
        f"Queue cleanup: removed {removed} file(s) older than {keep_days:g} days, "
        f"freed {freed / 1048576:.1f} MB, {failed} could not be deleted"
    )
    print(f"[{datetime.now():%H:%M}] Queue cleanup: {removed} files, "
          f"{freed / 1048576:.1f} MB freed")


# ── Manual trigger functions (call from CLI) ──────────────────
def run_outstanding_now():
    """python scheduler.py outstanding"""
    send_outstanding_reminders()

def run_reorder_now():
    """python scheduler.py reorder"""
    send_reorder_reminders()

def run_cleanup_now():
    """python scheduler.py cleanup"""
    clean_message_queue()

# ── Scheduler setup ───────────────────────────────────────────
def start_scheduler():
    CFG = load_config()
    outstanding_time = CFG["scheduler"]["outstanding_reminder_time"]
    reorder_time     = CFG["scheduler"]["reorder_reminder_time"]
    cleanup_time     = CFG["scheduler"].get("queue_cleanup_time", "23:30")

    schedule.every().day.at(outstanding_time).do(send_outstanding_reminders)
    schedule.every().day.at(reorder_time).do(send_reorder_reminders)
    schedule.every().day.at(cleanup_time).do(clean_message_queue)

    logging.info(f"Scheduler started")
    logging.info(f"  Outstanding reminders at {outstanding_time} daily")
    logging.info(f"  Reorder reminders at {reorder_time} daily")
    logging.info(f"  Message queue cleanup at {cleanup_time} daily")
    print(f"✅ Scheduler running — Outstanding @ {outstanding_time} | "
          f"Reorder @ {reorder_time} | Cleanup @ {cleanup_time}")
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
        elif cmd == "cleanup":
            run_cleanup_now()
        elif cmd == "test":
            print("Testing WhatsApp server connection...")
            print("Connected:", is_server_online())
        else:
            print(f"Unknown command: {cmd}")
            print("Usage: python scheduler.py [outstanding|reorder|cleanup|test]")
    else:
        start_scheduler()
