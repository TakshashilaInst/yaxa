"""Save Yaxa's outgoing-mail settings (run on the server, as the yaxa user).

Asks for the Google Workspace app password without echoing it and writes
<DEEPTUTOR_HOME>/secrets/yaxa-mail.json (mode 600). Nothing is printed or logged.

    sudo -u yaxa /home/yaxa/yaxa/.venv/bin/python /home/yaxa/yaxa/scripts/yaxa/set_mail.py
"""

import getpass
import json
import os
from pathlib import Path

home = Path(os.environ.get("DEEPTUTOR_HOME", "/home/yaxa/yaxa-home"))
address = input("Send from [gcpadmin@takshashila.org.in]: ").strip() or "gcpadmin@takshashila.org.in"
password = getpass.getpass(f"App password for {address} (16 letters; spaces are fine): ").replace(" ", "")
if not password:
    raise SystemExit("No password given; nothing saved.")
path = home / "secrets" / "yaxa-mail.json"
os.umask(0o077)
path.write_text(json.dumps({"host": "smtp.gmail.com", "port": 587, "username": address, "password": password,
                            "from": f"Takshashila Yaxa <{address}>"}))
os.chmod(path, 0o600)
print(f"Saved. Yaxa will send email from {address}.")
