#!/usr/bin/env bash
# Exit on error
set -o errexit

# Install python dependencies
pip install -r requirements.txt

# Install playwright browser and OS dependencies
playwright install chromium
playwright install-deps chromium
