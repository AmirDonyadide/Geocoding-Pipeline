"""Bounded task-specific raw transfer of already verified synthetic originals.

SSH serves exact immutable files without Python, hashing, unpacking or data
transformation on the login node. Source FD identity inside that tunnel is
unobserved: parent original identity/full-hash checks before READY and after
receipt enclose this transfer. This adds no native or scientific acceptance.
"""

from __future__ import annotations
import argparse
import hashlib
import os
from pathlib import Path
import selectors
import shlex
import signal
import subprocess
import sys
import time
import stage12_ra_g1_terminal_collect as tc
import stage12_ra_g1_terminal_parent as pair

CHUNK = 65536
MAX_STDERR = 65536
HOST = "goethe"


def need(value, code="RETENTION"):
    if not value:
        raise tc.Stop(code)


def remote_argv(host, path):
    need(host == HOST, "PATH")
    path = tc.absolute(str(path))
    # Fixed raw transfer only. Never interpolate a path without shell quoting.
    command = (
        "exec dd if=" + shlex.quote(str(path)) + " iflag=nofollow bs=65536 status=none"
    )
    return [
        "ssh",
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
        host,
        command,
    ]


def copy_process(argv, target, expected, control):
    """One exact framed artifact, no retry and no unbounded stdout/stderr list."""
    need(
        type(expected) is dict
        and type(expected["bytes"]) is int
        and expected["bytes"] >= 0
    )
    target = tc.absolute(str(target))
    tc.ancestors(target, links=False)
    tc.private(target.parent.lstat(), "DIR", os.geteuid())
    chain = tc.ancestors(target, links=False)
    root_identity = tc.ident(target.parent.lstat())[:5]
    control.check()
    need(control.creations < 128, "CREATIONS")
    control.creations += 1
    end = min(
        control.end, time.monotonic_ns() + max(0, control.epoch_end - time.time_ns())
    )
    kill_at = end - 2_000_000_000
    need(time.monotonic_ns() < kill_at, "DEADLINE")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    proc = None
    selector = None
    primary = None
    cleanup = False
    digest = hashlib.sha256()
    count = 0
    reserved = 0
    stderr_bytes = 0
    streams = set()
    joined = False
    try:
        control.check()
        origin = time.monotonic_ns()
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        need(proc.stdout is not None and proc.stderr is not None, "CHILD_LIFECYCLE")
        selector = selectors.DefaultSelector()
        for label, stream in (("stdout", proc.stdout), ("stderr", proc.stderr)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, label)
            streams.add(label)
        while streams or proc.poll() is None:
            control.check()
            need(time.monotonic_ns() < kill_at, "DEADLINE")
            for key, _ in selector.select(
                timeout=min(0.05, max(0, (kill_at - time.monotonic_ns()) / 1e9))
            ):
                n = (
                    min(CHUNK, expected["bytes"] - count + 1)
                    if key.data == "stdout"
                    else CHUNK
                )
                raw = control.read(key.fileobj.fileno(), max(1, n))
                if not raw:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                    streams.remove(key.data)
                    continue
                if key.data == "stderr":
                    stderr_bytes += len(raw)
                    need(stderr_bytes <= MAX_STDERR, "STDERR")
                    continue
                need(count + len(raw) <= expected["bytes"], "WRITE_BYTES")
                reserved += len(raw)
                need(reserved <= expected["bytes"], "WRITE_BYTES")
                digest.update(raw)
                count += len(raw)
                view = memoryview(raw)
                while view:
                    control.check()
                    wrote = os.write(fd, view)
                    need(wrote > 0, "WRITE_BYTES")
                    view = view[wrote:]
        code = proc.wait(timeout=0)
        joined = True
        control.check()
        need(
            code == 0
            and count == expected["bytes"]
            and digest.hexdigest() == expected["sha256"],
            "RETENTION",
        )
        os.fsync(fd)
        info = os.fstat(fd)
        tc.private(info, "FILE", os.geteuid())
        need(
            info.st_size == count and tc.ident(target.lstat()) == tc.ident(info),
            "SOURCE_CHANGED",
        )
        tc.check_ancestors(chain)
        need(tc.ident(target.parent.lstat())[:5] == root_identity, "SOURCE_CHANGED")
        dfd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(dfd)
        finally:
            tc.close_owned(control, (dfd,))
        control.check()
        return dict(
            bytes=count,
            sha256=digest.hexdigest(),
            exit_code=code,
            observed_joined=True,
            start_mono_ns=origin,
            end_mono_ns=time.monotonic_ns(),
            stderr_bytes=stderr_bytes,
            stderr_contents_retained=False,
            opaque_remote_fd_identity="UNOBSERVED",
        )
    except BaseException as error:
        primary = error
        raise
    finally:
        if proc is not None and proc.poll() is None:
            try:
                proc.send_signal(signal.SIGTERM)
                proc.wait(timeout=max(0, min(0.5, (end - time.monotonic_ns()) / 1e9)))
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(
                        timeout=max(0, min(0.5, (end - time.monotonic_ns()) / 1e9))
                    )
                except BaseException:
                    cleanup = True
            except BaseException:
                cleanup = True
        if proc is not None:
            joined = proc.poll() is not None
            for stream in (proc.stdout, proc.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except BaseException:
                        cleanup = True
        if selector is not None:
            try:
                selector.close()
            except BaseException:
                cleanup = True
        try:
            os.close(fd)
        except BaseException:
            cleanup = True
        if cleanup or (proc is not None and not joined):
            control.cleanup_uncertain = True
            if primary is None:
                raise tc.Stop("CLOSE_UNCERTAIN")
        if primary is None:
            control.check()


def fetch_ready(
    ready,
    ready_sha,
    local_root,
    control_root,
    *,
    host=HOST,
    testing_command_factory=None,
    testing_batch_command_factory=None,
    control=None,
):
    entered = time.monotonic_ns()
    epoch = time.time_ns()
    pair.validate_ready(ready)
    need(pair.digest(tc.canonical(ready)) == ready_sha)
    if testing_command_factory is not None or testing_batch_command_factory is not None:
        need(ready["scope"] == pair.TEST, "SCOPE")
    else:
        need(ready["scope"] == pair.NATIVE and host == HOST, "SCOPE")
    if control is None:
        control = pair.Control(
            entered, ready["context"]["parent_deadline_epoch_ns"], 900
        )
    else:
        control.epoch_end = min(
            control.epoch_end, ready["context"]["parent_deadline_epoch_ns"]
        )
        control.check()
    local_root = tc.absolute(str(local_root))
    control_root = tc.absolute(str(control_root))
    need(
        local_root != control_root
        and not tc.contained(local_root, control_root)
        and not tc.contained(control_root, local_root),
        "PATH",
    )
    for directory in (local_root, control_root):
        tc.ancestors(directory)
        tc.private(directory.lstat(), "DIR", os.geteuid())
    with os.scandir(local_root) as entries:
        need(next(entries, None) is None, "OUTPUT")
    need(
        sum(row["bytes"] for row in ready["artifacts"])
        <= ready["local_retention_byte_limit"],
        "WRITE_BYTES",
    )
    evidence = None
    if ready["version"] == pair.SUCCESSOR_READY_VERSION:
        need(testing_command_factory is None, "SCOPE")
        test_argv = testing_batch_command_factory(ready["artifacts"]) if testing_batch_command_factory is not None else None
        evidence, _ = fetch_batch(ready["artifacts"], local_root, control,
                                  expected_uid=ready["context"]["collection_uid"], testing_argv=test_argv, nonce="1"*32 if test_argv is not None else None)
        reports = evidence["files"]
    else:
        reports = []
        for row in ready["artifacts"]:
            control.check()
            argv = (
                testing_command_factory(row)
                if testing_command_factory is not None
                else remote_argv(host, row["path"])
            )
            reports.append(
                dict(
                    label=row["label"],
                    **copy_process(
                        argv, local_root / (row["label"] + ".original"), row, control
                    ),
                )
            )
    receipt_path = local_root / "RETENTION_RECEIPT.record"
    receipt = pair.verify_retention(
        ready, ready_sha, local_root, receipt_path, entered, epoch, control=control, transport_evidence=evidence
    )
    control.check()
    result = dict(
        version="stage12_terminal_bounded_transport_v1",
        status="LOCAL_STREAMS_HASHED_AWAITING_NATIVE_ACK",
        ready_sha256=ready_sha,
        receipt_sha256=pair.digest(tc.canonical(receipt)),
        original_job_id=ready["context"]["original_job_id"],
        collection_job_id=ready["context"]["collection_job_id"],
        actual_read_bytes=control.read_bytes,
        actual_read_calls=control.read_calls,
        artifacts=reports,
        fetch_entered_mono_ns=entered,
        completed_mono_ns=time.monotonic_ns(),
        native_or_scientific_acceptance=False,
    )
    if evidence is not None:
        result["version"] = "stage12_terminal_same_domain_bounded_transport_v2"
        result["transport_evidence"] = evidence
    control.record(control_root / "LOCAL_TRANSPORT_RESULT.record", result)
    return receipt, result


# Successor transport. Legacy raw-dd API above remains readable.
import datetime as _dt
import stat as _stat
import secrets as _secrets

BATCH_VERSION = "stage12_same_session_transfer_v2"
PRESENCE_WIRE = b"S12B3"
MAX_NAMED_STAT_LINE = 8192 + 512 + 2
MAX_METADATA = 262144


def batch_paths(rows, metadata_paths=()):
    need(type(rows) is list and 1 <= len(rows) <= 16, "FRAME")
    paths, labels = [], set()
    for row in rows:
        need(type(row) is dict and set(row) <= {"label", "path", "bytes", "sha256", "maximum", "local_name", "identity"}, "FRAME")
        path = tc.absolute(row["path"])
        need(type(row["label"]) is str and tc.LABEL.fullmatch(row["label"]) and row["label"] not in labels and path not in paths, "FRAME")
        need(len(os.fsencode(path)) <= 8192 and len(path.parts) <= 81 and "\n" not in str(path) and "|" not in str(path), "PATH")
        labels.add(row["label"])
        paths.append(path)
        maximum = row.get("bytes", row.get("maximum"))
        tc.uint(maximum)
        need(maximum <= 3 * 2**30, "LIMITS")
        if "sha256" in row:
            pair.hash_string(row["sha256"])
    extra = [tc.absolute(str(p)) for p in metadata_paths]
    need(len(extra) <= 16 and len(set(extra)) == len(extra) and not set(paths) & set(extra), "FRAME")
    for path in extra:
        need(len(os.fsencode(path)) <= 8192 and len(path.parts) <= 81 and "\n" not in str(path) and "|" not in str(path), "PATH")
    ancestors = sorted({p for path in paths + extra for p in path.parents}, key=str)
    need(len(ancestors) <= 1280, "ANCESTOR")
    return paths, extra, ancestors


def _selected_pending_directory(rows, paths, extras, ancestors, selected):
    """One exact task-selected final directory; never an arbitrary missing ancestor."""
    need(type(selected) is str and len(selected)<=1024
         and __import__("re").fullmatch(r"[A-Za-z0-9_./-]+",selected), "PATH")
    directory=tc.absolute(selected)
    expected={"ready":"TRANSPORT_READY.record","incomplete":"PAIR_INCOMPLETE.record","provisional":"PAIR_PROVISIONAL_COMPLETE.record"}
    need(str(directory)==selected and directory!=directory.parent and not extras
         and len(rows)==3 and {r["label"] for r in rows}==set(expected)
         and all(p.parent==directory and p.name==expected[r["label"]]
                 and r.get("bytes",r.get("maximum"))<=65536
                 for r,p in zip(rows,paths,strict=True))
         and directory in ancestors and directory.parent in ancestors, "SCOPE")
    return directory


def batch_remote_argv(rows, nonce, *, expected_uid, expected_gid=None, host=HOST, metadata_paths=(), publication=None, terminal_log_labels=(), pending_final_directory=None):
    need(host == HOST and type(nonce) is str and __import__("re").fullmatch("[0-9a-f]{32}", nonce), "DOMAIN")
    paths, extra, ancestors = batch_paths(rows, metadata_paths)
    directory=None
    if pending_final_directory is not None:
        need(publication is None and not terminal_log_labels,"SCOPE")
        directory=_selected_pending_directory(rows,paths,extra,ancestors,pending_final_directory)
    tc.uint(expected_uid)
    if expected_gid is not None:
        tc.uint(expected_gid)
    snapshot = paths + extra + ancestors
    quoted = " ".join(shlex.quote(str(p)) for p in snapshot)
    # Tagged metadata is bounded before launching the remote process.  A failed
    # multi-argument stat still emits its successful named originals.  Capturing
    # its status inside an if prevents errexit from discarding that evidence.
    need(sum(len(os.fsencode(p)) + 513 for p in snapshot) <= MAX_METADATA, "LIMITS")
    def snapshot_lines(stage, variable):
        return [
            f"{variable}_status=0",
            "if " + variable + "=$(stat --printf='%n|%d|%i|%f|%u|%g|%h|%s|%y|%z|%F\\n' -- " + quoted + "); then :; else " + variable + "_status=$?; fi",
            "printf '" + stage + "_STATUS|%s\\n' \"$" + variable + "_status\"",
            "if [[ -n \"$" + variable + "\" ]]; then printf '%s\\n' \"$" + variable + "\"; fi",
            "printf 'END_" + stage + "\\n'",
        ]
    # Same-session metadata/content/readback; two stat and two readlink
    # processes remain.  All new framing and array work uses Bash builtins.
    lines = [
        "set -euo pipefail", "umask 077", "export LC_ALL=C TZ=UTC",
        "payload_pid=",
        "cleanup(){ code=$?; trap - EXIT HUP INT TERM; if [[ -n \"$payload_pid\" ]]; then kill -TERM \"$payload_pid\" 2>/dev/null || :; wait \"$payload_pid\" 2>/dev/null || :; fi; exit \"$code\"; }",
        "trap cleanup EXIT", "trap 'exit 2' HUP INT TERM",
        "domain(){ IFS= read -r host </proc/sys/kernel/hostname; IFS= read -r boot </proc/sys/kernel/random/boot_id; mount=$(readlink -- /proc/$$/ns/mnt); printf 'DOMAIN|%s|%s|%s|%s|%s\\n' \"$host\" \"$boot\" \"$mount\" " + shlex.quote(nonce) + " \"$$\"; }",
        "printf 'S12B3|" + nonce + "|" + str(len(paths)) + "|" + str(len(extra)) + "|" + str(len(ancestors)) + "\\n'",
        "domain",
    ] + snapshot_lines("BEFORE", "before") + [
        # Build the fixed ordinal array without dropping absent slots.  A name
        # may intentionally occupy both an extra-metadata and ancestor slot.
        "meta=(" + " ".join("''" for _ in snapshot) + ")",
        "if [[ -n \"$before\" ]]; then",
        "while IFS='|' read -r named info; do",
        "case \"$named\" in",
    ]
    for path in dict.fromkeys(snapshot):
        assignments = "; ".join("meta[" + str(i) + "]=\"$info\""
                                for i, expected in enumerate(snapshot) if expected == path)
        lines.append(shlex.quote(str(path)) + ") " + assignments + ";;")
    lines += ["*) exit 2;;", "esac", "done <<<\"$before\"", "fi"]
    # Reject unsupported metadata before any DD opens a source. All predicates
    # use Bash builtins over this session's own captured lstat snapshot.
    lines.append("[[ ${#meta[@]} -eq " + str(len(snapshot)) + " ]]")
    for i in range(len(paths)+len(extra),len(snapshot)):
        if directory is not None and snapshot[i]==directory:
            lines.append("if [[ -n \"${meta["+str(i)+"]}\" ]]; then")
        lines += [
            "IFS='|' read -r dev ino mode owner group links size mt ct kind <<<\"${meta[" + str(i) + "]}\"",
            "[[ \"$mode\" =~ ^[0-9a-f]+$ ]]",
            "(( (16#$mode & 0170000) == 0040000 ))",
        ]
        if directory is not None and snapshot[i]==directory:
            lines.append("fi")
    if directory is not None:
        higher=snapshot.index(directory.parent)
        lines += ["IFS='|' read -r dev ino mode owner group links size mt ct kind <<<\"${meta["+str(higher)+"]}\"",
                  "[[ \"$owner\" == "+str(expected_uid)+" ]]",
                  "(( (16#$mode & 0177777) == 0040700 ))"]
        if expected_gid is not None:lines.append("[[ \"$group\" == "+str(expected_gid)+" ]]")
        final=snapshot.index(directory)
        lines.append("if [[ -z \"${meta["+str(final)+"]}\" ]]; then")
        lines += ["[[ -z \"${meta["+str(i)+"]}\" ]]" for i in range(len(paths))]
        lines.append("fi")
    for i,row in enumerate(rows):
        maximum=row.get("bytes",row.get("maximum"))
        parent=ancestors.index(paths[i].parent)+len(paths)+len(extra)
        if directory is not None:lines.append("if [[ -n \"${meta["+str(parent)+"]}\" ]]; then")
        lines += [
            "IFS='|' read -r dev ino mode owner group links size mt ct kind <<<\"${meta[" + str(parent) + "]}\"",
            "[[ \"$owner\" == " + str(expected_uid) + " ]]",
            "(( (16#$mode & 0177777) == 0040700 ))",
        ]
        if expected_gid is not None:
            lines.append("[[ \"$group\" == " + str(expected_gid) + " ]]")
        if directory is not None:lines.append("fi")
        lines.append("if [[ -n \"${meta[" + str(i) + "]}\" ]]; then")
        lines += [
            "IFS='|' read -r dev ino mode owner group links size mt ct kind <<<\"${meta[" + str(i) + "]}\"",
            "[[ \"$mode\" =~ ^[0-9a-f]+$ && \"$size\" =~ ^[0-9]+$ && \"$owner\" == " + str(expected_uid) + " && \"$links\" == 1 ]]",
            "(( (16#$mode & 0177777) == 0100600 ))",
            "(( size <= " + str(maximum) + " ))",
        ]
        if "bytes" in row:
            lines.append("(( size == " + str(row["bytes"]) + " ))")
        if expected_gid is not None:
            lines.append("[[ \"$group\" == " + str(expected_gid) + " ]]")
        lines.append("fi")
    if terminal_log_labels:
        positions=[i for i,row in enumerate(rows) if row["label"] in terminal_log_labels]
        lines.append("log_total=0")
        for i in positions:
            lines += ["if [[ -n \"${meta[" + str(i) + "]}\" ]]; then",
                      "IFS='|' read -r dev ino mode owner group links size mt ct kind <<<\"${meta[" + str(i) + "]}\"",
                      "(( log_total += size )) || [[ \"$log_total\" == 0 ]]", "fi"]
        lines.append("(( log_total <= 16777216 ))")
    for i, path in enumerate(paths):
        lines += [
            "if [[ -n \"${meta[" + str(i) + "]}\" ]]; then",
            "IFS='|' read -r dev ino mode owner group links size mt ct kind <<<\"${meta[" + str(i) + "]}\"",
            "[[ \"$size\" =~ ^[0-9]+$ ]]",
            "printf 'DATA|" + str(i) + "|%s\\n' \"$size\"",
            "dd if=" + shlex.quote(str(path)) + " iflag=nofollow,nonblock bs=65536 status=none &",
            "payload_pid=$!", "wait \"$payload_pid\"", "payload_pid=",
            "printf '\\nEND_DATA|" + str(i) + "\\n'",
            "else", "printf 'ABSENT_DATA|" + str(i) + "\\n'", "fi",
        ]
    lines += snapshot_lines("AFTER", "after") + [
        "domain", "printf 'END|" + nonce + "\\n'",
    ]
    if publication is not None:
        pair.fields(publication,"target job_id deadline_epoch_ns bytes","RETENTION")
        need(len(rows)==1 and rows[0]["path"]==publication["target"] and rows[0]["bytes"]==publication["bytes"],"RETENTION")
        target=tc.absolute(publication["target"])
        need(target.name=="RETENTION_RECEIPT.record","PATH")
        tc.uint(publication["job_id"],True)
        tc.uint(publication["deadline_epoch_ns"],True)
        need(0 < publication["bytes"] <= 65536,"LIMITS")
        quoted_target=shlex.quote(str(target))
        parent=shlex.quote(str(target.parent))
        prefix=[
            "set -euo pipefail", "umask 077", "export LC_ALL=C TZ=UTC",
            "target="+quoted_target,
            "[[ ! -e \"$target\" && ! -L \"$target\" ]]",
            "[[ \"$(stat -c '%a:%u' -- "+parent+")\" == \"700:$UID\" ]]",
            "[[ $(date +%s%N) -lt "+str(publication["deadline_epoch_ns"])+" ]]",
            "[[ \"$(squeue -h -j "+str(publication["job_id"])+" -o '%T')\" == RUNNING ]]",
            "set -C; : > \"$target.upload-reservation\"; set +C",
            "dd of=\"$target.upload-pending\" oflag=excl bs=65536 status=none",
            "sync -f -- \"$target.upload-pending\"",
            "[[ ! -e \"$target\" && ! -L \"$target\" ]]",
            "mv -T -n -- \"$target.upload-pending\" \"$target\"",
            "[[ ! -e \"$target.upload-pending\" ]]",
            "sync -f -- "+parent,
            "[[ $(date +%s%N) -lt "+str(publication["deadline_epoch_ns"])+" ]]",
        ]
        lines=prefix+lines
    # Bash 3.2 does not apply errexit to every arithmetic command. Explicit
    # exits make every metadata predicate fail closed on both supported shells.
    lines=[line+" || exit 2" if line.startswith(("[[ ","((")) else line for line in lines]
    command = "exec bash -c " + shlex.quote("\n".join(lines))
    return ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", host, command]


def _stat_line(raw):
    need(type(raw) is bytes and len(raw) <= 512 and raw.endswith(b"\n"), "FRAME")
    try:
        parts = raw[:-1].decode("ascii").split("|")
        need(len(parts) == 10, "FRAME")
        def ns(text):
            match = __import__("re").fullmatch(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\.(\d{9}) \+0000", text)
            need(match is not None, "FRAME")
            stamp = _dt.datetime.strptime(match[1], "%Y-%m-%d %H:%M:%S").replace(tzinfo=_dt.timezone.utc)
            delta = stamp - _dt.datetime(1970,1,1,tzinfo=_dt.timezone.utc)
            return (delta.days*86400+delta.seconds)*10**9+int(match[2])
        value = [int(parts[0]), int(parts[1]), int(parts[2],16), int(parts[3]), int(parts[4]), int(parts[5]), int(parts[6]), ns(parts[7]), ns(parts[8])]
        for n in value:
            tc.uint(n)
        need(parts[9] in ("regular file", "regular empty file", "directory", "fifo"), "FRAME")
        need((_stat.S_ISREG(value[2]) and parts[9] in ("regular file", "regular empty file"))
             or (_stat.S_ISDIR(value[2]) and parts[9] == "directory")
             or (_stat.S_ISFIFO(value[2]) and parts[9] == "fifo"), "FRAME")
        need(parts[9] != "regular empty file" or value[6] == 0, "FRAME")
        return value
    except (UnicodeError, ValueError, OverflowError):
        raise tc.Stop("FRAME") from None


def _named_stat_block(reader, stage, snapshot, values, states):
    """Read every selected name before content; generic failures stay unknown."""
    raw = reader.line()
    prefix = (stage + "_STATUS|").encode()
    need(raw.startswith(prefix) and raw.endswith(b"\n"), "FRAME")
    status_raw = raw[len(prefix):-1]
    need(status_raw.isdigit() and len(status_raw) <= 3, "FRAME")
    status = int(status_raw)
    need(0 <= status <= 255, "FRAME")
    seen = set()
    total = 0
    while True:
        raw = reader.line(MAX_NAMED_STAT_LINE)
        if raw == ("END_" + stage + "\n").encode():
            break
        total += len(raw)
        need(total <= MAX_METADATA and len(seen) < len(snapshot), "LIMITS")
        named, separator, info = raw.partition(b"|")
        need(separator == b"|", "FRAME")
        try:
            path = os.fsdecode(named)
        except (ValueError, UnicodeError):
            raise tc.Stop("FRAME") from None
        # metadata_paths may also be an ancestor. Preserve its explicitly
        # repeated slot rather than conflating equal pathnames.
        index = next((i for i, expected in enumerate(snapshot)
                      if str(expected) == path and i not in seen), None)
        need(index is not None, "FRAME")
        values[index] = _stat_line(info)
        states[index] = "PRESENT"
        seen.add(index)
    for index in range(len(snapshot)):
        if index not in seen:
            states[index] = "UNAVAILABLE"
    need((status == 0) == (len(seen) == len(snapshot)), "FRAME")
    return status


class _PipeReader:
    def __init__(self, proc, control, kill_at, input_bytes=None, retain_stderr=False):
        self.stderr_capture = bytearray() if retain_stderr else None
        self.input_view = memoryview(input_bytes) if input_bytes is not None else None
        self.proc, self.control, self.kill_at = proc, control, kill_at
        self.selector = selectors.DefaultSelector()
        self.buffer = bytearray()
        self.streams = {"stdout", "stderr"}
        self.stderr_bytes = self.stdout_bytes = 0
        try:
            for label, stream in (("stdout",proc.stdout),("stderr",proc.stderr)):
                os.set_blocking(stream.fileno(),False)
                self.selector.register(stream,selectors.EVENT_READ,label)
            if input_bytes is not None:
                os.set_blocking(proc.stdin.fileno(),False)
                self.selector.register(proc.stdin,selectors.EVENT_WRITE,"stdin")
        except BaseException:
            self.selector.close()
            raise

    def pump(self, wait_timeout=0.05):
        need(type(wait_timeout) in (int,float) and 0 <= wait_timeout <= .05, "LIMITS")
        self.control.check()
        need(time.monotonic_ns() < self.kill_at, "DEADLINE")
        for key,_ in self.selector.select(wait_timeout):
            if key.data == "stdin":
                try:
                    n=os.write(key.fileobj.fileno(),self.input_view[:CHUNK])
                except BrokenPipeError:
                    raise tc.Stop("RETENTION") from None
                need(n>0,"WRITE_BYTES")
                self.input_view=self.input_view[n:]
                if not self.input_view:
                    self.selector.unregister(key.fileobj)
                    key.fileobj.close()
                continue
            raw = self.control.read(key.fileobj.fileno(), CHUNK)
            if not raw:
                self.selector.unregister(key.fileobj)
                self.streams.remove(key.data)
                continue
            if key.data == "stderr":
                self.stderr_bytes += len(raw)
                need(self.stderr_bytes <= MAX_STDERR, "STDERR")
                if self.stderr_capture is not None:
                    self.stderr_capture.extend(raw)
            else:
                self.stdout_bytes += len(raw)
                need(self.stdout_bytes <= 3*2**30 + 2*128*2**20 + 2**20 + 2*MAX_METADATA, "READ_BYTES")
                self.buffer.extend(raw)

    def read(self, n):
        need(0 <= n <= CHUNK, "READ_BYTES")
        while len(self.buffer) < n and "stdout" in self.streams:
            self.pump()
        raw = bytes(self.buffer[:n])
        del self.buffer[:len(raw)]
        return raw

    def line(self, limit=512):
        while True:
            pos = self.buffer.find(b"\n")
            if pos >= 0:
                need(pos+1 <= limit, "FRAME")
                raw = bytes(self.buffer[:pos+1])
                del self.buffer[:pos+1]
                return raw
            need(len(self.buffer) <= limit and "stdout" in self.streams, "TRUNCATED")
            self.pump()

    def finish(self):
        while self.streams or self.proc.poll() is None:
            self.pump()
            need(not self.buffer, "FRAME")
        need(not self.buffer and not self.input_view and self.proc.wait(timeout=0) == 0, "CHILD_EXIT")


def fetch_batch(rows, target_root, control, *, expected_uid, expected_gid=None,
                metadata_paths=(), testing_argv=None, nonce=None, publication=None, input_bytes=None, terminal_log_labels=(), pending_labels=(), keep_stdin_open=False, pending_final_directory=None):
    """One same-domain before/content/after sequence, preserving failed prefixes."""
    paths, extras, ancestors = batch_paths(rows, metadata_paths)
    need(type(keep_stdin_open) is bool and type(pending_labels) is tuple, "SCOPE")
    if pending_labels:
        expected_names = {"ready":"TRANSPORT_READY.record", "incomplete":"PAIR_INCOMPLETE.record", "provisional":"PAIR_PROVISIONAL_COMPLETE.record"}
        need(len(rows)==3 and len(pending_labels)==3 and set(pending_labels)==set(expected_names)
             and {r["label"] for r in rows}==set(expected_names) and not metadata_paths
             and publication is None and not terminal_log_labels, "SCOPE")
        need(all(r.get("bytes",r.get("maximum")) <= 65536 for r in rows), "LIMITS")
        need(len({p.parent for p in paths})==1 and all(p.name==expected_names[r["label"]]
             and len(str(p))<=1024 and __import__("re").fullmatch(r"[A-Za-z0-9_./-]+",str(p))
             for r,p in zip(rows,paths,strict=True)), "PATH")
    directory=None
    if pending_final_directory is not None:
        need(bool(pending_labels) and publication is None and not terminal_log_labels,"SCOPE")
        directory=_selected_pending_directory(rows,paths,extras,ancestors,pending_final_directory)
    need((publication is None) == (input_bytes is None), "RETENTION")
    if input_bytes is not None:
        need(type(input_bytes) is bytes and len(input_bytes) <= 65536 and len(input_bytes) == publication["bytes"], "RETENTION")
        control.claim(len(input_bytes))
    need(type(terminal_log_labels) in (list,tuple) and len(set(terminal_log_labels)) == len(terminal_log_labels) and set(terminal_log_labels) <= {r["label"] for r in rows}, "FRAME")
    nonce = _secrets.token_hex(16) if nonce is None else nonce
    need(type(nonce) is str and __import__("re").fullmatch("[0-9a-f]{32}", nonce), "DOMAIN")
    if testing_argv is not None:
        need(os.environ.get("SAFE_STAGE12_INVENTED_TRANSPORT") == "1", "SCOPE")
    target_root = tc.absolute(str(target_root))
    tc.private(target_root.lstat(), "DIR", os.geteuid())
    local_chain = tc.ancestors(target_root)
    local_identity = tc.ident(target_root.lstat())[:5]
    end = min(control.end, time.monotonic_ns()+max(0,control.epoch_end-time.time_ns()))
    kill_at = end - 2*10**9
    control.check()
    need(time.monotonic_ns() < kill_at, "DEADLINE")
    proc = reader = None
    fd = None
    first = None
    phase = "START"
    before = after = []
    presence_before = presence_after = None
    before_stat_status = after_stat_status = None
    domain_before = domain_after = None
    file_reports = []
    file_report_indices = []
    cleanup_uncertain = False
    remote_complete = False
    try:
        proc = subprocess.Popen(testing_argv if testing_argv is not None else batch_remote_argv(rows, nonce, expected_uid=expected_uid, expected_gid=expected_gid, metadata_paths=metadata_paths, publication=publication, terminal_log_labels=terminal_log_labels, pending_final_directory=pending_final_directory),
                                stdin=subprocess.PIPE if input_bytes is not None or keep_stdin_open else subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        reader = _PipeReader(proc,control,kill_at,input_bytes,bool(pending_labels))
        header = reader.line()
        suffix = f"|{nonce}|{len(paths)}|{len(extras)}|{len(ancestors)}\n".encode()
        need(header in (b"S12B2" + suffix, PRESENCE_WIRE + suffix), "FRAME")
        named_wire = header.startswith(PRESENCE_WIRE + b"|")
        def domain():
            try:
                parts = reader.line().decode("ascii").rstrip("\n").split("|")
            except UnicodeError:
                raise tc.Stop("DOMAIN") from None
            need(len(parts) == 6 and parts[0] == "DOMAIN" and parts[4] == nonce, "DOMAIN")
            value = dict(host=parts[1],boot_id=parts[2],mount_namespace=parts[3],session_nonce=parts[4],session_pid=int(parts[5]) if parts[5].isascii() and parts[5].isdecimal() else 0)
            pair.validate_transport_domain(value)
            return value
        phase = "BEFORE"
        domain_before = domain()
        snapshot = paths + extras + ancestors
        if named_wire:
            before = [None] * len(snapshot)
            presence_before = ["UNOBSERVED"] * len(snapshot)
            before_stat_status = _named_stat_block(reader, "BEFORE", snapshot, before, presence_before)
        else:
            need(reader.line() == b"BEFORE\n", "FRAME")
            before = []
            for _ in snapshot:
                before.append(_stat_line(reader.line()))
        need(sum(before[i][6] for i,r in enumerate(rows) if r["label"] in terminal_log_labels and before[i] is not None) <= 16*2**20, "WRITE_BYTES")
        selected_index=(len(paths)+len(extras)+ancestors.index(directory)) if directory is not None else None
        selected_absent=selected_index is not None and before[selected_index] is None
        for i,info in enumerate(before[len(paths)+len(extras):],len(paths)+len(extras)):
            if selected_absent and i==selected_index:continue
            need(info is not None and _stat.S_ISDIR(info[2]), "ANCESTOR")
        if directory is not None:
            higher=before[len(paths)+len(extras)+ancestors.index(directory.parent)]
            need(higher is not None and _stat.S_ISDIR(higher[2]) and _stat.S_IMODE(higher[2])==0o700
                 and higher[3]==expected_uid and (expected_gid is None or higher[4]==expected_gid),"PRIVATE")
        if selected_absent:need(named_wire and all(v is None for v in before[:len(paths)]),"SOURCE_CHANGED")
        else:
            for path in paths:
                parent = ancestors.index(path.parent)+len(paths)+len(extras)
                info=before[parent]
                need(info is not None and _stat.S_ISDIR(info[2]) and _stat.S_IMODE(info[2]) == 0o700 and info[3] == expected_uid and (expected_gid is None or info[4] == expected_gid), "PRIVATE")
        for i,(row,path) in enumerate(zip(rows,paths,strict=True)):
            phase = "CONTENT"
            info = before[i]
            if info is None:
                need(named_wire and reader.line() == f"ABSENT_DATA|{i}\n".encode(), "FRAME")
                continue
            need(_stat.S_ISREG(info[2]) and _stat.S_IMODE(info[2]) == 0o600 and info[3] == expected_uid
                 and (expected_gid is None or info[4] == expected_gid) and info[5] == 1, "PRIVATE")
            maximum = row.get("bytes",row.get("maximum"))
            need(info[6] <= maximum and ("bytes" not in row or info[6] == row["bytes"]), "READ_BYTES")
            need(reader.line() == f"DATA|{i}|{info[6]}\n".encode(), "FRAME")
            name = row.get("local_name", row["label"]+".original")
            need(type(name) is str and "/" not in name and name not in ("",".",".."), "PATH")
            target = target_root / name
            control.claim(0,True)
            fd = os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            sha=hashlib.sha256()
            left=info[6]
            while left:
                raw=reader.read(min(CHUNK,left))
                need(raw,"TRUNCATED")
                sha.update(raw)
                left-=len(raw)
                view=memoryview(raw)
                while view:
                    control.check()
                    wrote=os.write(fd,view)
                    need(wrote>0,"WRITE_BYTES")
                    view=view[wrote:]
            need(reader.line() == b"\n" and reader.line() == f"END_DATA|{i}\n".encode(), "FRAME")
            if "sha256" in row:
                need(sha.hexdigest()==row["sha256"],"PAYLOAD_HASH")
            os.fsync(fd)
            local=os.fstat(fd)
            tc.private(local,"FILE",os.geteuid())
            need(tc.ident(local)==tc.ident(target.lstat()) and local.st_size==info[6],"SOURCE_CHANGED")
            tc.close_owned(control,(fd,))
            fd=None
            file_reports.append(dict(label=row["label"],path=str(path),before=info,after=None,bytes=info[6],sha256=sha.hexdigest()))
            file_report_indices.append(i)
        phase="AFTER"
        if named_wire:
            after = [None] * len(snapshot)
            presence_after = ["UNOBSERVED"] * len(snapshot)
            after_stat_status = _named_stat_block(reader, "AFTER", snapshot, after, presence_after)
        else:
            need(reader.line()==b"AFTER\n","FRAME")
            after=[]
            for _ in snapshot:
                after.append(_stat_line(reader.line()))
        domain_after=domain()
        need(domain_after==domain_before,"DOMAIN")
        for i, row in zip(file_report_indices, file_reports, strict=True):
            row["after"]=after[i]
        if not named_wire:
            need(before[:len(paths)+len(extras)]==after[:len(paths)+len(extras)],"SOURCE_CHANGED")
            need([v[:6] for v in before[len(paths)+len(extras):]]==[v[:6] for v in after[len(paths)+len(extras):]],"ANCESTOR_CHANGED")
        need(reader.line()==f"END|{nonce}\n".encode(),"FRAME")
        phase="JOIN"
        reader.finish()
        remote_complete = True
        if named_wire:
            need(before[:len(paths)+len(extras)]==after[:len(paths)+len(extras)],"SOURCE_CHANGED")
            if directory is None:
                need(all(value is not None for value in after[len(paths)+len(extras):])
                     and [v[:6] for v in before[len(paths)+len(extras):]]==[v[:6] for v in after[len(paths)+len(extras):]],"ANCESTOR_CHANGED")
            else:
                for i in range(len(paths)+len(extras),len(before)):
                    if selected_absent and i==selected_index:need(after[i] is None,"SOURCE_CHANGED")
                    else:need(before[i] is not None and after[i] is not None and before[i][:6]==after[i][:6],"ANCESTOR_CHANGED")
        tc.check_ancestors(local_chain)
        need(tc.ident(target_root.lstat())[:5]==local_identity,"SOURCE_CHANGED")
        dfd=os.open(target_root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            os.fsync(dfd)
        finally:
            tc.close_owned(control,(dfd,))
        if named_wire and (before_stat_status or after_stat_status):
            phase = "BEFORE"
            raise tc.Stop("RETENTION")
        evidence=dict(version=BATCH_VERSION,domain_before=domain_before,domain_after=domain_after,
                      ancestors=[dict(path=str(path),before=before[len(paths)+len(extras)+i],after=after[len(paths)+len(extras)+i]) for i,path in enumerate(ancestors)],
                      files=file_reports,exit_code=0,observed_joined=True)
        pair.validate_transport_evidence(evidence)
        control.check()
    except BaseException as error:
        first=error
        # No exception text, arbitrary path or stderr is retained.
        diagnostic=dict(version=BATCH_VERSION,status="INCOMPLETE",first_phase=phase,
                        first_mono_ns=time.monotonic_ns(),first_epoch_ns=time.time_ns(),
                        code=pair.safe_code(error),domain_before=domain_before,domain_after=domain_after,
                        metadata_before=before,metadata_after=after,cleanup_uncertain=False)
        if presence_before is not None:
            diagnostic["retained_files"] = file_reports
        if presence_before is not None:
            diagnostic["presence"] = dict(
                version="stage12_named_control_presence_v1",
                before_stat_exit=before_stat_status, after_stat_exit=after_stat_status,
                entries=[dict(index=i, label=rows[i]["label"] if i < len(rows) else None,
                              kind="CONTROL" if i < len(paths) else "METADATA" if i < len(paths)+len(extras) else "ANCESTOR",
                              before=presence_before[i], after=presence_after[i] if presence_after is not None else "UNOBSERVED")
                         for i in range(len(snapshot))],
            )
    finally:
        if fd is not None:
            try:
                tc.close_owned(control,(fd,))
            except BaseException:
                cleanup_uncertain=True
        # A failed task probe still drains both pipes and observes the owned
        # child's real exit. This never repairs incomplete protocol evidence.
        if pending_labels and first is not None and proc is not None and reader is not None:
            join_end = min(kill_at, time.monotonic_ns()+250_000_000)
            while time.monotonic_ns() < join_end and (reader.streams or proc.poll() is None):
                try:
                    if reader.streams:
                        reader.pump(min(.05,max(0,(join_end-time.monotonic_ns())/1e9)))
                    else:
                        proc.wait(timeout=max(0,(join_end-time.monotonic_ns())/1e9))
                except subprocess.TimeoutExpired:
                    break
                except BaseException:
                    cleanup_uncertain = True
                    break
            if proc.poll() is not None:
                proc.wait(timeout=0)
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(proc.pid,signal.SIGTERM)
                proc.wait(timeout=max(0,min(.5,(end-time.monotonic_ns())/1e9)))
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid,signal.SIGKILL)
                    proc.wait(timeout=max(0,min(.5,(end-time.monotonic_ns())/1e9)))
                except BaseException:
                    cleanup_uncertain=True
            except BaseException:
                cleanup_uncertain=True
        if proc is not None:
            cleanup_uncertain |= proc.poll() is None
            for stream in (proc.stdin,proc.stdout,proc.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except BaseException:
                        cleanup_uncertain=True
        if reader is not None:
            try:
                reader.selector.close()
            except BaseException:
                cleanup_uncertain=True
        cleanup_uncertain |= control.cleanup_uncertain or not remote_complete
        control.cleanup_uncertain |= cleanup_uncertain
    if first is not None:
        diagnostic["cleanup_uncertain"]=cleanup_uncertain
        diagnostic["remote_cleanup_status"]="JOINED_NATIVE_EXIT_ZERO" if remote_complete else "UNKNOWN"
        diagnostic["cleanup_completed_mono_ns"]=time.monotonic_ns()
        if pending_labels:
            captured = bytes(reader.stderr_capture) if reader is not None and reader.stderr_capture is not None else b""
            missing = [r["label"] for i,r in enumerate(rows)
                       if i < len(before) and i < len(after) and before[i] is None and after[i] is None]
            missing_paths = [str(paths[i]) for i,r in enumerate(rows) if r["label"] in missing]
            missing_directory=None
            if directory is not None:
                di=len(paths)+len(extras)+ancestors.index(directory)
                if di<len(before) and di<len(after) and before[di] is None and after[di] is None:
                    missing_directory=str(directory)
                    missing_paths.append(missing_directory)
            expected_errors = b"".join(("stat: cannot statx '"+p+"': No such file or directory\n").encode("ascii") for p in missing_paths) * 2
            verified = None
            if (type(first) is tc.Stop and first.args == ("RETENTION",) and phase == "BEFORE"
                and remote_complete and not cleanup_uncertain and missing
                and before_stat_status == after_stat_status == 1 and domain_before == domain_after
                and presence_before == presence_after and captured == expected_errors):
                verified = missing
            diagnostic["pending_check"] = dict(
                version="stage12_task_named_control_absence_v1" if directory is None else "stage12_task_selected_pair_absence_v2",
                verified_missing_errno_labels=verified,
                child_pid=proc.pid if proc is not None else None,
                child_exit=proc.poll() if proc is not None else None,
                observed_joined=proc is not None and proc.poll() is not None,
                stdout_eof=reader is not None and "stdout" not in reader.streams,
                stderr_eof=reader is not None and "stderr" not in reader.streams,
                stderr_bytes=len(captured), stderr_sha256=hashlib.sha256(captured).hexdigest(),
                stdout_bytes=reader.stdout_bytes if reader is not None else 0,
                keep_stdin_open=keep_stdin_open,
                native_errno_interface="EXACT_GNU_STAT_C_LOCALE_ENOENT_ONLY_OTHER_MESSAGES_UNVERIFIED")
            if directory is not None:
                diagnostic["pending_check"].update(selected_final_directory=str(directory),
                    verified_missing_final_directory=missing_directory if verified is not None else None)
        first.transport_diagnostic=diagnostic
        raise first
    need(not cleanup_uncertain,"CLOSE_UNCERTAIN")
    return evidence, {str(path):before[len(paths)+i] for i,path in enumerate(extras)}


def main(argv=None):
    entered = time.monotonic_ns()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ready", type=Path, required=True)
    parser.add_argument("--ready-sha256", required=True)
    parser.add_argument("--local-root", type=Path, required=True)
    parser.add_argument("--control-root", type=Path, required=True)
    parser.add_argument("--same-domain-successor", action="store_true")
    args = parser.parse_args(argv)
    os.umask(0o077)
    bootstrap = pair.Control(entered, pair.family_end({"version":pair.SUCCESSOR_VERSION}) if args.same_domain_successor else pair.WINDOW_END_NS, 900)
    try:
        ready = pair.load_control(args.ready, args.ready_sha256, bootstrap)
        need(args.same_domain_successor == (ready.get("version") == pair.SUCCESSOR_READY_VERSION), "SCOPE")
        _, result = fetch_ready(
            ready,
            args.ready_sha256,
            args.local_root,
            args.control_root,
            control=bootstrap,
        )
        sys.stdout.write(tc.canonical(result).decode())
        return 0
    except BaseException as error:
        sys.stderr.write(
            tc.canonical(
                dict(
                    version="stage12_terminal_bounded_transport_v1",
                    status="INCOMPLETE",
                    code=pair.safe_code(error),
                    cleanup_uncertain=bootstrap.cleanup_uncertain,
                    first_safe_error=getattr(error, "transport_diagnostic", None),
                    native_or_scientific_acceptance=False,
                )
            ).decode()
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
