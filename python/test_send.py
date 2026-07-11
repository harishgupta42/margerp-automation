"""Send a test WhatsApp message to verify real delivery. Usage: python test_send.py 9876543210"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from phone_utils import normalize_phone
from whatsapp_client import is_server_online, send_text

def main():
    if len(sys.argv) < 2:
        print("Usage: python test_send.py <10-digit mobile>")
        print("Example: python test_send.py 9876543210")
        sys.exit(1)

    phone = normalize_phone(sys.argv[1])
    print(f"Normalized phone: {phone}")

    if not is_server_online():
        print("ERROR: WhatsApp server offline. Run START_SERVER.bat first.")
        sys.exit(1)

    msg = "Test from Marg WhatsApp automation. If you see this, sending works."
    ok = send_text(phone, msg)
    if ok:
        print(f"OK — check WhatsApp on {phone} (must be a real registered number)")
    else:
        print("FAILED — see logs/whatsapp.log for details")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
