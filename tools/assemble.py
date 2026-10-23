"""Validate normal submissions and export independent AT/FB agent folders."""

import argparse
import itertools
import json
import tempfile
from pathlib import Path

from agent_layout import ROOT, assemble_pair, check_name, validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--at")
    parser.add_argument("--fb")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--check", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.check:
        if args.at or args.fb or args.all or args.output:
            parser.error("--check cannot be combined with export arguments")
        if args.check.parent.name not in {"at", "fb"}:
            parser.error("--check expects submissions/at/<team> or submissions/fb/<team>")
        validate(args.check, args.check.parent.name)
        print("OK:", args.check)
        return
    if (
        not args.output
        or (args.all and (args.at or args.fb))
        or (not args.all and not (args.at and args.fb))
    ):
        parser.error("specify --at TEAM --fb TEAM, or --all, and --output")
    output = args.output.resolve()
    manifest = output.with_name(output.name + ".manifest.json")
    if output.exists() or manifest.exists():
        raise ValueError("output or manifest already exists")
    if args.all:
        teams = {
            role: sorted(p for p in (ROOT / "submissions" / role).glob("*") if p.is_dir())
            for role in ("at", "fb")
        }
        if not all(teams.values()):
            raise ValueError("need at least one AT and one FB")
        names = [p.name for paths in teams.values() for p in paths]
        if len(names) != len(set(names)):
            raise ValueError("duplicate team/package names")
        for role, paths in teams.items():
            for path in paths:
                validate(path, role)
        pairs = list(itertools.product(teams["at"], teams["fb"]))
    else:
        for name in (args.at, args.fb):
            check_name(name)
        pairs = [(ROOT / "submissions/at" / args.at, ROOT / "submissions/fb" / args.fb)]
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".export-", dir=output.parent) as tmp:
        staged = Path(tmp) / output.name
        records = []
        if args.all:
            staged.mkdir()
        for at, fb in pairs:
            dest = staged / f"at_{at.name}__fb_{fb.name}" if args.all else staged
            records.append(assemble_pair(at, fb, dest))
        staged.rename(output)
    manifest.write_text(json.dumps({"agents": records}, ensure_ascii=False, indent=2) + "\n")
    print(f"Exported {len(records)} agent folder(s) to {output}")
    print(f"Manifest: {manifest}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        raise SystemExit(f"error: {exc}") from exc
