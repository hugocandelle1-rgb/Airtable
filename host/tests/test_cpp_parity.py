"""Parité du parseur de commandes C++ (firmware) et de son miroir Python (hôte)."""
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from host.airtable_host import protocol as P
from host.tests.test_protocol import INVALID, VALID

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "firmware" / "lib" / "atcore" / "src"


@pytest.fixture(scope="module")
def harness(tmp_path_factory):
    if shutil.which("g++") is None:
        pytest.skip("g++ indisponible")
    exe = tmp_path_factory.mktemp("harness") / "parse"
    cmd = ["g++", "-std=c++17", "-O1", f"-I{CORE}", str(Path(__file__).with_name("cpp_parse_harness.cpp")),
           str(CORE / "atcore" / "commands.cpp"), "-o", str(exe)]
    subprocess.run(cmd, check=True, capture_output=True)
    return exe


def run_cpp(exe, lines):
    out = subprocess.run([str(exe)], input="\n".join(lines) + "\n", capture_output=True, text=True, check=True)
    return out.stdout.splitlines()


def py_result(line):
    try:
        c = P.parse_command(line)
    except P.ParseError as e:
        return f"ERR {e.code}"
    return f"OK {c.type} {c.f[0]:.6g} {c.f[1]:.6g} {c.axis} {int(c.flag)}"


def test_corpus_connu(harness):
    lines = [l for l, _ in VALID] + [l for l, _ in INVALID if l != ""]
    got = run_cpp(harness, lines)
    assert len(got) == len(lines)
    for line, g in zip(lines, got):
        assert g == py_result(line), f"divergence sur {line[:40]!r}"


def test_fuzz_jetons(harness):
    rnd = random.Random(42)
    words = ["SET", "P", "MASS", "DUTY", "GET", "STATUS", "LEVEL", "MOVE", "JOG", "X", "Y", "A", "B", "AUTO", "ON",
             "OFF", "TARGET", "CAL", "TILT", "BIAS", "ROT", "CLEAR", "TABLE", "ADD", "H", "STREAM", "FAN", "GAINS",
             "NOZZLE", "RAMP", "WDT", "DEADBAND", "ZERO", "HOME", "STOP", "PZERO", "SAFE", "PING", "SAVE", "FOO"]
    nums = ["0", "1", "-1", "5", "12.5", "-3.25", "100", "400", "999", "1e2", "1e9", "-1e9", "nan", "inf", "abc",
            "0x10", "1_0", "0.05", "0.01", "5000", "5001", "-5000", "3600", "3601", "1.2", "1.21", "0.1", "0.09"]
    lines = []
    for _ in range(1500):
        n = rnd.randint(1, 5)
        toks = []
        for i in range(n):
            toks.append(rnd.choice(words) if (i == 0 or rnd.random() < 0.55) else rnd.choice(nums))
        lines.append(" ".join(toks))
    got = run_cpp(harness, lines)
    assert len(got) == len(lines)
    bad = [(l, g, py_result(l)) for l, g in zip(lines, got) if g != py_result(l)]
    assert not bad, f"{len(bad)} divergences, ex. {bad[:3]}"
