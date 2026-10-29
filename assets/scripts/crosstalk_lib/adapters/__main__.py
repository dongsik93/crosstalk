"""Fixed adapter entry point for the legacy launcher; never dispatches engine commands."""
import argparse
import sys
from .registry import launch
from ..protocol import Error


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    start = sub.add_parser('launch')
    start.add_argument('kind', choices=('claude', 'codex', 'antigravity', 'agy'))
    start.add_argument('--auto-approve', action='store_true')
    start.add_argument('--fresh-for-input', help='Create a new Codex conversation for this recorded input')
    args = parser.parse_args()
    try:
        print(launch(args.kind, auto_approve=args.auto_approve, fresh_for_input=args.fresh_for_input))
        return 0
    except (Error, OSError, ValueError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
