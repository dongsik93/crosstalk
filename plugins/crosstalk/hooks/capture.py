#!/usr/bin/env python3
"""Load the installed capture hook, or the source checkout during development."""
import os
from pathlib import Path
import sys

state = Path(os.environ.get('CROSSTALK_CONFIG_DIR', Path.home() / '.claude/crosstalk'))
installed = state / 'current/assets/scripts'
source = Path(__file__).resolve().parents[3] / 'assets/scripts'
runtime = installed if (installed / 'crosstalk_lib/intake.py').is_file() else source
sys.path.insert(0, str(runtime))

if __name__ == '__main__':
    try:
        from crosstalk_lib.intake import hook_main
        hook_main()
    except ImportError:
        print('Crosstalk input capture requires the v0.12.1 runtime installation.', file=sys.stderr)
