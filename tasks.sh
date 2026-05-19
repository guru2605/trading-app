#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 [-f format] [-s style] [-t type-check] [-u unit-test] [-c coverage] [-x fix]"
    exit 1
}

if [ $# -eq 0 ]; then
    usage
fi

while getopts "fstucx" opt; do
    case $opt in
        f)
            echo "==> Formatting with ruff..."
            poetry run ruff format app tests
            ;;
        s)
            echo "==> Style checking with ruff..."
            poetry run ruff check app tests
            ;;
        t)
            echo "==> Type checking with mypy..."
            poetry run mypy app
            ;;
        u)
            echo "==> Running unit tests..."
            poetry run pytest tests/ -v
            ;;
        c)
            echo "==> Running tests with coverage..."
            poetry run pytest tests/ --cov=app --cov-report=term-missing
            ;;
        x)
            echo "==> Auto-fixing with ruff..."
            poetry run ruff check app tests --fix
            poetry run ruff format app tests
            ;;
        *)
            usage
            ;;
    esac
done
