"""Command line dispatch."""

import sys

from research_mapper.commands import COMMANDS
from research_mapper.cli import run


def main() -> None:
    """Run a command, or the terminal app if none is given."""
    if len(sys.argv) < 2:
        run()
        return
    name, *args = sys.argv[1:]
    command = COMMANDS.get(name)
    if command is None:
        raise SystemExit(f"unknown command: {name}. try: {', '.join(COMMANDS)}")
    command(*args)


if __name__ == "__main__":
    main()
