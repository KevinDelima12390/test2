#!/bin/bash

# Navigate to the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

# Activate the virtual environment
source venv/bin/activate

# Run the main GUI application
python main_gui.py