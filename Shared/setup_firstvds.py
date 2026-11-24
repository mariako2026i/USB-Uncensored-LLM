"""Set up a separate SSH key limited to Mira's diagnostic commands."""

import base64
import ipaddress
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from personal_actions import REMOTE_COMMANDS


def setup_script(public_key):
    key = public_key.split()
    if len(key) < 2 or key[0] != "ssh-ed25519" or not re.fullmatch(r"[A-Za-z0-9+/=]+", key[1]):
        raise ValueError("Unexpected public key format")
    pattern = "|".join(shlex.quote(command) for command in sorted(REMOTE_COMMANDS))
    options = 'restrict,command="sh ~/.ssh/mira-firstvds-diagnostics-v1"'
    entry = f"{options} {key[0]} {key[1]} mira-firstvds"
    return f"""set -eu
umask 077
mkdir -p "$HOME/.ssh"
helper="$HOME/.ssh/mira-firstvds-diagnostics-v1"
keys="$HOME/.ssh/authorized_keys"
if [ -L "$HOME/.ssh" ] || [ -L "$helper" ] || [ -L "$keys" ]; then
    echo 'SSH paths contain a symbolic link; setup stopped.' >&2
    exit 1
fi
create_helper() {{
    cat <<'MIRA_HELPER'
#!/bin/sh
case "${{SSH_ORIGINAL_COMMAND-}}" in
    {pattern}) exec /bin/sh -c "$SSH_ORIGINAL_COMMAND";;
    *) echo 'This key only permits Mira diagnostics.' >&2; exit 126;;
esac
MIRA_HELPER
}}
if [ -e "$helper" ]; then
    if ! create_helper | cmp -s - "$helper"; then
        echo 'Existing Mira helper differs; setup stopped.' >&2
        exit 1
    fi
else
    (set -C; create_helper > "$helper")
fi
key_line={shlex.quote(entry)}
if ! grep -Fqx -- "$key_line" "$keys" 2>/dev/null; then
    if [ -e "$keys" ] && grep -Fq -- {shlex.quote(key[1])} "$keys"; then
        echo 'This key is already present with different restrictions; setup stopped.' >&2
        exit 1
    fi
    printf '\\n%s\\n' "$key_line" >> "$keys"
fi
"""


def main():
    host = str(ipaddress.IPv4Address(input("FirstVDS IPv4 address: ").strip()))
    user = input("SSH user [root]: ").strip() or "root"
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", user):
        raise ValueError("Unexpected SSH username")
    if input(f"Set up diagnostic access for {user}@{host}? [y/N] ").strip().lower() != "y":
        return 0
    folder = Path.home() / ".ssh"
    folder.mkdir(exist_ok=True)
    key = folder / "mira_firstvds_ed25519"
    pub = key.with_suffix(".pub")
    config = folder / "mira-firstvds.conf"
    settings = (
        f"Host firstvds\n  HostName {host}\n  User {user}\n"
        "  IdentityFile ~/.ssh/mira_firstvds_ed25519\n  IdentitiesOnly yes\n"
        "  BatchMode yes\n  StrictHostKeyChecking yes\n"
    )
    if config.exists() and config.read_text(encoding="ascii") != settings:
        raise ValueError("An existing Mira profile points elsewhere. Use your existing profile or move it first.")
    ssh_dir = Path(os.environ["SystemRoot"]) / "System32" / "OpenSSH"
    ssh = str(ssh_dir / "ssh.exe")
    if not key.exists() and not pub.exists():
        subprocess.run([str(ssh_dir / "ssh-keygen.exe"), "-q", "-t", "ed25519",
                        "-N", "", "-C", "mira-firstvds-diagnostics", "-f", str(key)], check=True)
    if not key.is_file() or not pub.is_file():
        raise ValueError("The Mira key pair is incomplete.")
    payload = base64.b64encode(setup_script(pub.read_text(encoding="ascii")).encode()).decode("ascii")
    print("Enter the FirstVDS SSH password if requested. Input is hidden.", flush=True)
    subprocess.run([ssh, "-T", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10",
                    "--", f"{user}@{host}", f"printf %s {payload} | base64 -d | bash"], check=True)
    if not config.exists():
        config.write_text(settings, encoding="ascii", newline="\n")
    subprocess.run([ssh, "-F", str(config), "--", "firstvds", "whoami"], check=True)
    print("Mira SSH is ready. Start Windows\\start-crm-codex.bat and send /ssh docker compose version.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as error:
        print(f"FirstVDS setup stopped (exit {error.returncode}). See the output above.", file=sys.stderr)
        sys.exit(1)
    except (ValueError, OSError) as error:
        print(f"FirstVDS setup stopped: {error}", file=sys.stderr)
        sys.exit(1)
