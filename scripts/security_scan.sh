#!/bin/bash
# Security scan script for PB Studio Rebuild
# Uses Bandit to scan Python code for security vulnerabilities

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "======================================"
echo "PB Studio Security Scan with Bandit"
echo "======================================"
echo ""

# Activate virtual environment if it exists
if [ -f "$PROJECT_ROOT/.venv/Scripts/activate" ]; then
    echo "Activating virtual environment..."
    source "$PROJECT_ROOT/.venv/Scripts/activate"
elif [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    echo "Activating virtual environment..."
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

# Check if bandit is installed
if ! command -v bandit &> /dev/null; then
    echo "ERROR: Bandit is not installed. Install with: pip install bandit"
    exit 1
fi

# Run bandit security scan
echo "Running Bandit security scan..."
echo "Excluding: .venv, vendor, tests, installer, scripts"
echo ""

# Run with medium+ severity for CI/CD
bandit -r "$PROJECT_ROOT" \
    -x "./.venv/*,./vendor/*,./tests/*,./installer/*,./scripts/*" \
    -ll \
    -f txt \
    -o "$PROJECT_ROOT/security_scan_report.txt"

echo ""
echo "Security scan complete!"
echo "Report saved to: security_scan_report.txt"
echo ""

# Also generate JSON for machine parsing
bandit -r "$PROJECT_ROOT" \
    -x "./.venv/*,./vendor/*,./tests/*,./installer/*,./scripts/*" \
    -f json \
    -o "$PROJECT_ROOT/security_scan_results.json"

echo "JSON results saved to: security_scan_results.json"
echo ""

# Parse and display summary
echo "Summary:"
grep -E "Total issues|Total lines of code" "$PROJECT_ROOT/security_scan_report.txt" || true
