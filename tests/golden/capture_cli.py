"""Capture the Java command-line clients' output (stdlib only; needs Java 25+).

Usage, from this repository's root, with the Java project built (``./mvnw package``):

    python -I tests/golden/capture_cli.py /path/to/SimpleMCPCalculator

Runs each client jar from the Java project's root (where its default server-jar paths resolve)
with every argument list below, and writes ``tests/golden/cli.json``: the client, its arguments,
stdout, stderr and exit code.
"""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent

# Number spellings where Java's Double.parseDouble and Python's float() disagree.
ODD_NUMBERS = [
    "1d",
    "2.5f",
    "0x1p3",
    "1_000",
    " 7",
    "+5",
    ".5",
    "5.",
    "1e400",
    "NaN",
    "Infinity",
    "-0",
]

SCIENTIFIC_CLIENT = (
    "ScientificCalculatorMCP/scientific-calculator-mcp-client/target/"
    "scientific-calculator-mcp-client.jar"
)

CASES: dict[str, list[list[str]]] = {
    "calculator-mcp-client/target/calculator-mcp-client.jar": [
        [],
        ["add", "7", "5"],
        ["subtract", "7", "5"],
        ["multiply", "6", "7"],
        ["divide", "10", "4"],
        ["remainder", "10", "3"],
        ["exponent", "2", "10"],
        ["divide", "1", "0"],
        ["factorial", "5"],
        ["isPrime", "97"],
        ["parity", "42"],
        ["parity", "7.5"],
        ["factorial", "2.5"],
        ["exponent", "10", "400"],
        ["remainder", "1e400", "2"],
        ["cube_root", "8", "1"],
        ["cube_root", "8"],
        ["add", "1"],
        ["add"],
        ["add", "1", "2", "3"],
        ["add", "1", "abc"],
        ["add", "abc"],
        *[["add", n, "1"] for n in ODD_NUMBERS],
        *[["parity", n] for n in ODD_NUMBERS],
        ["add", "7", "5", "--"],
        ["add", "--", "7", "5"],
        ["--=x", "add", "1", "2"],
        ["add", "0x1p2000", "1"],
    ],
    SCIENTIFIC_CLIENT: [
        [],
        ["sqrt", "144"],
        ["sqrt", "2"],
        ["ln", "10"],
        ["log10", "1000"],
        ["log", "1024", "2"],
        ["log", "1000", "10"],
        ["sqrt", "-4"],
        ["ln", "0"],
        ["log", "8", "1"],
        ["log", "8"],
        ["sqrt", "4", "2"],
        ["sqrt"],
        ["cube_root", "8"],
        ["sqrt", "abc"],
        *[["sqrt", n] for n in ODD_NUMBERS],
        ["sqrt", "4", "--"],
        ["log", "--", "8", "2"],
        ["sqrt", "0x1p2000"],
    ],
    "calculator-router-client/target/calculator-router-client.jar": [
        [],
        ["add", "7", "5"],
        ["exponent", "2", "10"],
        ["factorial", "5"],
        ["isPrime", "97"],
        ["parity", "42"],
        ["sqrt", "144"],
        ["ln", "10"],
        ["log10", "1000"],
        ["log", "1024", "2"],
        ["divide", "1", "0"],
        ["sqrt", "-4"],
        ["factorial", "2.5"],
        ["log", "8"],
        ["sqrt", "4", "2"],
        ["cube_root", "8"],
        ["add"],
        ["add", "1", "abc"],
        *[["sqrt", n] for n in ODD_NUMBERS],
        ["log", "--", "1024", "2"],
        ["--", "log", "1024", "2"],
        ["--=x", "sqrt", "4"],
    ],
}

# The scientific client resolves its server jar relative to its own project directory.
CWD = {
    SCIENTIFIC_CLIENT: "ScientificCalculatorMCP",
}


RUN_TIMEOUT = 120
"""Under load a Java client can time out initializing, return from main without System.exit,
and hang on its non-daemon transport threads; a run that takes this long is killed and retried."""


def _run_once(java_root: Path, jar: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    cwd = java_root / CWD.get(jar, "")
    # Own process group, so a timeout kills the client and the server JVMs it started (which
    # would otherwise keep the output pipes open).
    proc = subprocess.Popen(  # noqa: S603 - fixed command
        ["java", "-jar", str(java_root / jar), *args],  # noqa: S607
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=RUN_TIMEOUT)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise
    return subprocess.CompletedProcess(proc.args, proc.returncode, stdout, stderr)


def run(java_root: Path, jar: str, args: list[str]) -> dict[str, object]:
    for attempt in range(2):
        try:
            done = _run_once(java_root, jar, args)
            break
        except subprocess.TimeoutExpired:
            print(f"timed out (attempt {attempt + 1}): {Path(jar).stem} {args}", file=sys.stderr)
    else:
        return {"client": Path(jar).stem, "args": args, "hung": True}
    return {
        "client": Path(jar).stem,
        "args": args,
        "stdout": done.stdout,
        "stderr": done.stderr,
        "exit": done.returncode,
    }


if __name__ == "__main__":
    root = Path(sys.argv[1])
    results = [run(root, jar, args) for jar, cases in CASES.items() for args in cases]
    (HERE / "cli.json").write_text(json.dumps(results, indent=1) + "\n")
    print(f"{len(results)} runs captured")
