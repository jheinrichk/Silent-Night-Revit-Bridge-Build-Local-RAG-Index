# -*- coding: utf-8 -*-
"""Append one manual bridge experience record to the local RAG cycle log."""
from __future__ import print_function
import argparse, json, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CYCLE_LOG = ROOT / "cycles" / "bridge_cycles.jsonl"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="")
    ap.add_argument("--state", default="UNKNOWN")
    ap.add_argument("--script-file", default="")
    ap.add_argument("--rps-file", default="")
    args = ap.parse_args()
    CYCLE_LOG.parent.mkdir(parents=True, exist_ok=True)
    code = Path(args.script_file).read_text(encoding="utf-8", errors="replace") if args.script_file else ""
    rps = Path(args.rps_file).read_text(encoding="utf-8", errors="replace") if args.rps_file else ""
    rec = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "cycle_number": "manual",
        "task": args.task,
        "next_recommended_state": args.state,
        "code_preview": code[:12000],
        "rps_output_preview": rps[:16000]
    }
    with CYCLE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")
    print("Added manual cycle record to {}".format(CYCLE_LOG))

if __name__ == "__main__":
    main()
