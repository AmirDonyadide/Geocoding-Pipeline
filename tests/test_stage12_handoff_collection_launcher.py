"""TEST_ONLY shell/interface fixtures; no scheduler, native job or workload."""
from pathlib import Path
import os
import subprocess
import sys
import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "cluster/goethe_nhr/stage12_ra_g1_terminal_collection.sbatch"

@pytest.mark.parametrize("same,handoff,expected_exit,expected_flags", [
    pytest.param("", "", 0, [], marks=pytest.mark.skipif(sys.platform == "darwin", reason="Actual Mac /bin/bash3.2 unselected legacy empty-array+nounset limitation; production unchanged")),
    ("1", "", 0, ["--same-domain-successor"]),
    ("1", "1", 0, ["--same-domain-successor", "--handoff-window-successor"]),
    ("", "1", 2, None),
    ("1", "unknown", 2, None),
])
def test_actual_collection_launcher_window_arguments(tmp_path, same, handoff, expected_exit, expected_flags):
    """Only Git identity and final interpreter are TEST_ONLY command fixtures."""
    tmp_path.chmod(0o700)
    source=tmp_path/"source";source.mkdir(mode=0o700)
    tools=tmp_path/"tools";tools.mkdir(mode=0o700)
    git=tools/"git"
    git.write_text('#!/bin/sh\ncase "$1" in\nrev-parse) printf "%s\\n" "'+"a"*40+'";;\nstatus) :;;\n*) exit 9;;\nesac\n')
    git.chmod(0o700)
    interpreter=tools/"selected-interpreter"
    interpreter.write_text('#!/bin/sh\nprintf "TEST_ONLY_INTERPRETER_ARGV\\n"\nprintf "%s\\n" "$@"\n')
    interpreter.chmod(0o700)
    env=dict(os.environ,PATH=str(tools),STAGE12_TC_SOURCE=str(source),
             STAGE12_TC_SHA="a"*40,STAGE12_TC_PYTHON=str(interpreter),
             STAGE12_TC_BINDING=str(source/"binding.record"),STAGE12_TC_BINDING_SHA="b"*64,
             STAGE12_TC_AUTHORITY=str(source/"authority.record"),STAGE12_TC_AUTHORITY_SHA="c"*64,
             STAGE12_TC_SAME_DOMAIN_SUCCESSOR=same,STAGE12_TC_HANDOFF_WINDOW_SUCCESSOR=handoff)
    actual=subprocess.run(["/bin/bash",str(SCRIPT)],cwd=source,env=env,
                          stdin=subprocess.DEVNULL,capture_output=True,timeout=3,check=False)
    assert actual.returncode==expected_exit
    assert actual.stderr==b""
    if expected_flags is None:
        assert actual.stdout==b""
    else:
        args=actual.stdout.decode().splitlines()
        assert args[:3]==["TEST_ONLY_INTERPRETER_ARGV","-B","scripts/stage12_ra_g1_terminal_parent.py"]
        assert args[3:]==["run-pair","--binding",str(source/"binding.record"),
            "--binding-sha256","b"*64,"--authority",str(source/"authority.record"),
            "--authority-sha256","c"*64,*expected_flags]
