"""Copy a normal starter agent folder, replacing only the team name."""

import argparse

from agent_layout import create_team

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=["at", "fb"])
    parser.add_argument("team")
    args = parser.parse_args()
    try:
        print(create_team(args.role, args.team))
    except (ValueError, OSError) as exc:
        parser.exit(1, f"error: {exc}\n")
