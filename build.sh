
#!/usr/bin/env bash
# Production build script for FRC Team 2073 Scouting System

set -euo pipefail

echo "========================================="
echo "FRC Scouting System - Build"
echo "========================================="

# Detect Python
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
else
    echo "ERROR: Python not found."
    exit 1
fi

echo "Using Python: $PYTHON_CMD"
$PYTHON_CMD --version

# Check Node.js
if ! command -v node >/dev/null 2>&1; then
    echo "ERROR: Node.js not found."
    exit 1
fi

echo "Using Node.js: $(node --version)"
echo "Using npm: $(npm --version)"

# Step 1: Create an isolated Python environment
echo "[1/6] Setting up Python environment..."

if [ ! -x ".venv/bin/python" ]; then
    "$PYTHON_CMD" -m venv .venv
fi

VENV_PYTHON=".venv/bin/python"

# Step 2: Install Python dependencies
echo "[2/6] Installing Python dependencies..."
"$VENV_PYTHON" -m pip install --disable-pip-version-check \
    --no-cache-dir -r requirements.txt

# Step 3: Install Node.js dependencies
echo "[3/6] Installing Node.js dependencies..."
if [ -f "package-lock.json" ]; then
    npm ci --quiet
else
    npm install --quiet
fi

# Step 4: Build frontend assets
echo "[4/6] Building frontend assets..."
npm run build

# Step 5: Collect static files
echo "[5/6] Collecting Django static files..."
"$VENV_PYTHON" manage.py collectstatic --no-input

# Step 6: Optional migrations
if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    echo "[6/6] Running database migrations..."
    "$VENV_PYTHON" manage.py migrate --no-input
else
    echo "[6/6] Skipping migrations."
fi

echo "========================================="
echo "Build completed successfully!"
echo "========================================="
