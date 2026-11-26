#!/bin/sh
# Run the stdlib-only test suite (no pytest, no third-party deps).
set -eu
cd "$(dirname "$0")/.."
exec python3 -m unittest discover -s tests -v "$@"
