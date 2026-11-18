"""Install requirements.txt into the current Python (the project .venv), one group at a time.

Used by run_oasis.bat / run_oasis.sh. Groups are marked in requirements.txt with
"# [group: name]". The groups "web" and "bert" are required; "forecast" is optional.
Binary wheels are preferred (--prefer-binary), so nothing is compiled from source.
A failing optional group does not stop the others. A failing required group stops
with the real pip error printed in red and exit code 2.
Each group's full pip output is kept in .venv/pip_install_<group>.log.

    python install_requirements.py                       all groups (first run)
    python install_requirements.py --groups simulator,tests   only these groups (added for the Decision Lab)
"""
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REQ = HERE / "requirements.txt"
LOGDIR = Path(sys.prefix)
REQUIRED = {"web", "bert"}

os.system("")  # enables ANSI colours in the Windows console
RED, YEL, GRN, OFF = "\033[91m", "\033[93m", "\033[92m", "\033[0m"


def parse(path):
    options, groups, current = [], {}, None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        m = re.match(r"#\s*\[group:\s*([\w-]+)\]", line)
        if m:
            current = m.group(1)
            groups.setdefault(current, [])
            continue
        if not line or line.startswith("#"):
            continue
        if line.startswith("--"):
            options += line.split(None, 1)
            continue
        groups.setdefault(current or "web", []).append(line)
    return options, groups


def pip(args, log):
    cmd = [sys.executable, "-m", "pip"] + args
    print("   $ " + " ".join(cmd[2:]), flush=True)
    lines = []
    with open(log, "w", encoding="utf-8", errors="replace") as f:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        for line in p.stdout:
            f.write(line)
            lines.append(line.rstrip())
            print("     " + line.rstrip(), flush=True)
        return p.wait(), lines


def main():
    v = sys.version_info
    if not ((3, 10) <= (v.major, v.minor) <= (3, 13)):
        print(f"{RED}[ERROR] This is Python {v.major}.{v.minor}. Use Python 3.10-3.13 (torch, pyyaml and tokenizers have no wheels for newer versions).{OFF}")
        return 2
    options, groups = parse(REQ)
    only = None
    if "--groups" in sys.argv[1:]:
        only = [g.strip() for g in sys.argv[sys.argv.index("--groups") + 1].split(",") if g.strip()]
        unknown = [g for g in only if g not in groups]
        if unknown:
            print(f"{RED}[ERROR] unknown group(s) {unknown}; requirements.txt has {list(groups)}{OFF}")
            return 2
        groups = {g: groups[g] for g in only}
    print(f"   Python {sys.version.split()[0]} at {sys.executable}")
    if only is None:
        code, _ = pip(["install", "--upgrade", "pip"], LOGDIR / "pip_install_pip.log")
        if code:
            print(f"{YEL}   [WARNING] could not upgrade pip; continuing with the installed pip.{OFF}")
    failed_required, failed_optional = [], []
    for name, pkgs in groups.items():
        if not pkgs:
            continue
        print(f"\n   --- group '{name}' ({'required' if name in REQUIRED else 'optional'}): {' '.join(pkgs)}", flush=True)
        log = LOGDIR / f"pip_install_{name}.log"
        code, lines = pip(["install", "--prefer-binary"] + options + pkgs, log)
        if code:
            err = [l for l in lines if re.search(r"error|failed|could not|no matching", l, re.I)] or lines[-25:]
            colour = RED if name in REQUIRED else YEL
            print(f"\n{colour}   [{'ERROR' if name in REQUIRED else 'WARNING'}] pip failed for group '{name}' (exit code {code}). The real error:{OFF}")
            for l in err[-25:]:
                print(f"{colour}     {l}{OFF}")
            print(f"{colour}   Full log: {log}{OFF}")
            (failed_required if name in REQUIRED else failed_optional).append(name)
    if failed_required:
        print(f"\n{RED}[ERROR] Required packages failed to install: {', '.join(failed_required)}. BERT cannot load. Stopping.{OFF}")
        return 2
    if only is not None:
        if failed_optional:
            print(f"{YEL}   Not installed: {', '.join(failed_optional)}.{OFF}")
            return 1
        print(f"{GRN}   Installed: {', '.join(only)}{OFF}")
        return 0
    check = subprocess.run([sys.executable, "-c", "import torch, transformers, safetensors, yaml, flask; print(torch.__version__, transformers.__version__)"],
                           capture_output=True, text=True)
    if check.returncode:
        print(f"{RED}[ERROR] Installed, but the import check failed:{OFF}\n{RED}{check.stderr.strip()[-1500:]}{OFF}")
        return 3
    print(f"\n{GRN}   Import check OK: torch {check.stdout.split()[0]}, transformers {check.stdout.split()[1]}{OFF}")
    if failed_optional:
        print(f"{YEL}   Optional groups not installed: {', '.join(failed_optional)} (the server and BERT do not need them).{OFF}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
