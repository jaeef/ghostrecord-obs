"""GhostRec OBS — command-line recorder.

Run:  python record.py            (interactive window picker)
      python record.py --list     (list windows)
      python record.py --help
"""

import sys

from ghostrec.cli import run

if __name__ == "__main__":
    sys.exit(run())
