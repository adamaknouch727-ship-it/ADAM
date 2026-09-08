#!/usr/bin/env python3
"""Double-click launcher: starts the KDP Niche Finder web app.

    python3 run.py              # http://127.0.0.1:8777
    python3 run.py 9000         # custom port
"""

import sys

from kdpniche.cli import main

if __name__ == "__main__":
    args = ["serve"]
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        args += ["--port", sys.argv[1]]
    else:
        args += sys.argv[1:]
    sys.exit(main(args))
