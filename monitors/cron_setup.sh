#!/usr/bin/env bash
# Outputs the crontab line to add for midnight PT daily execution.
# Usage: run this script, then add the output to your crontab with: crontab -e

echo "Crontab line for midnight PT daily run:"
echo ""
echo "0 0 * * * cd ~/Projects/res-dashboard && /Users/lisalobster/.local/bin/python3.12 monitors/run_checks.py >> /tmp/res-monitor.log 2>&1"
echo ""
echo "To install: (crontab -l 2>/dev/null; echo '0 0 * * * cd ~/Projects/res-dashboard && /Users/lisalobster/.local/bin/python3.12 monitors/run_checks.py >> /tmp/res-monitor.log 2>&1') | crontab -"
