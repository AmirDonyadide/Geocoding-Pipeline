"""One bounded actual audit/storage test process; contains no credential/provider.

Run as a child from the external evidence runner. On Darwin this establishes
actual Python audit/fsync behavior, not Linux kernel/M2 qualification.
"""

import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io

source = Path(__file__).resolve().parents[1]
root = Path(sys.argv[1]).resolve(strict=True)
assert root.stat().st_mode & 0o777 == 0o700
output, payload, proof = root / "output", root / "input.json", root / "proof"
payload.write_text("{}\n")
proof.mkdir(mode=0o700)
secret_dummy = root / ".env"
secret_dummy.write_bytes(b"INVENTED_TEST_CANARY_ONLY")
inherited = os.open(secret_dummy, os.O_RDONLY)
spec = importlib.util.spec_from_file_location(
    "actual_guard_test", source / "scripts/stage12_wf_ap2_diagnostic.py"
)
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
state = d.install_denials(source, output, payload, proof)
state[3][0] = 256
io.reserve(output)  # Includes actual readonly parent directory handle + fsync.
io.write(output / "retained.json", b"{}\n")
assert io.read(output / "retained.json") == b"{}\n"
denied = []
for tag, action in (
    ("credentials", lambda: secret_dummy.read_bytes()),
    ("inherited_fd", lambda: os.fdopen(inherited, "rb", closefd=False)),
    ("proc_fd", lambda: open(f"/proc/self/fd/{inherited}", "rb")),
    ("dns", lambda: socket.getaddrinfo("must-not-resolve.invalid", 443)),
    ("process", lambda: subprocess.run(["must-not-start"])),
    ("parent_enumeration", lambda: list(root.iterdir())),
):
    try:
        action()
    except (PermissionError, RuntimeError):
        denied.append(tag)
    else:
        raise AssertionError("GUARD_NEAR_MISS_ACCEPTED:" + tag)
fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
try:
    try:
        list(os.scandir(fd))
    except PermissionError:
        denied.append("parent_fd_enumeration")
    else:
        raise AssertionError("PARENT_HANDLE_NOT_SCOPED_TO_FSYNC")
finally:
    os.close(fd)
    os.close(inherited)
result = {
    "result": "PASS",
    "platform": sys.platform,
    "actual_audit_installed": True,
    "actual_storage_reserve_parent_fsync": True,
    "denied": denied,
    "actual_linux_execution": sys.platform == "linux",
    "M2_or_Goethe_qualified": False,
    "creations_charged": state[2][0],
}
io.write(output / "RESULT.json", d.canonical(result))
print(json.dumps(result))
