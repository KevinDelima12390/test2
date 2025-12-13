#!/bin/bash
set -x

# Navigate to the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

# Activate the virtual environment
source venv/bin/activate

# Run MAVProxy
venv/bin/python venv/bin/mavproxy.py --master=udp:0.0.0.0:14550 --out=udp:127.0.0.1:14551 --out=udp:127.0.0.1:14552 --out=udp:127.0.0.1:14553 > mavproxy.log 2> mavproxy.err.log
