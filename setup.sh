#!/usr/bin/env bash
# =============================================================================
# AI YouTube Video Generator — one-shot setup
# Run once after cloning:
#   bash setup.sh
# =============================================================================
set -euo pipefail

# ── Resolve project root (directory of this script) ─────────────────────────
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "▶ Project root: $REPO_DIR"

# ── 1. Create .env from template (skip if already exists) ────────────────────
if [[ ! -f "$REPO_DIR/.env" ]]; then
    cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
    # Write the detected BASE_DIR into .env automatically
    sed -i "s|^BASE_DIR=.*|BASE_DIR=$REPO_DIR|" "$REPO_DIR/.env"
    echo "✔ Created .env  (BASE_DIR set to $REPO_DIR)"
    echo "  → Edit .env to set LLAMA_MODEL_PATH and other options."
else
    echo "✔ .env already exists — skipping"
fi

# ── 2. Create required runtime directories ───────────────────────────────────
echo "▶ Creating runtime directories …"
dirs=(
    logs
    models
    final
    temp/audio
    temp/clip
    temp/image
    temp/mix
    temp/subtitle
    temp/temp
    temp/video
    temp/voice
    song/bright
    song/calm
    song/dark
    song/dramatic
    song/funky
    song/happy
    song/inspirational
    song/sad
    optic
)
for d in "${dirs[@]}"; do
    mkdir -p "$REPO_DIR/$d"
done
echo "✔ Directories created"

# ── 3. Install Python dependencies ───────────────────────────────────────────
echo "▶ Installing Python dependencies …"
echo "  (llama-cpp-python will be built from source — may take a few minutes)"

# Detect CUDA availability and build llama-cpp-python accordingly
if command -v nvcc &>/dev/null || [[ -d /usr/local/cuda ]]; then
    echo "  CUDA detected — building llama-cpp-python with GPU support"
    CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python --no-cache-dir --quiet
else
    echo "  No CUDA detected — building llama-cpp-python for CPU only"
    pip install llama-cpp-python --no-cache-dir --quiet
fi

pip install -r "$REPO_DIR/requirements.txt" --quiet
echo "✔ Python dependencies installed"

# ── 4. Initialise the SQLite database ────────────────────────────────────────
echo "▶ Initialising database …"
cd "$REPO_DIR" && python create.py
echo "✔ Database ready"

# ── 5. Install cron job ───────────────────────────────────────────────────────
echo "▶ Installing cron job …"

PYTHON_BIN="$(command -v python3 || command -v python)"
PIPELINE="$REPO_DIR/pipeline.py"
LOG_FILE="$REPO_DIR/logs/cron.log"

# Run the full pipeline every hour.
# Adjust the schedule (first five fields) to your preference:
#   "0 * * * *"   → every hour   (default)
#   "0 */6 * * *" → every 6 hours
#   "0 2 * * *"   → daily at 02:00
CRON_SCHEDULE="* * * * *"
CRON_CMD="$PYTHON_BIN $PIPELINE >> $LOG_FILE 2>&1"
CRON_ENTRY="$CRON_SCHEDULE $CRON_CMD"
CRON_MARKER="# ai-youtube-video-generator"

# Read current crontab (ignore error if empty)
CURRENT_CRON="$(crontab -l 2>/dev/null || true)"

if echo "$CURRENT_CRON" | grep -qF "$CRON_MARKER"; then
    echo "✔ Cron job already installed — skipping"
else
    # Append new entry with a marker comment so we can find it later
    (
        echo "$CURRENT_CRON"
        echo ""
        echo "$CRON_MARKER"
        echo "$CRON_ENTRY"
    ) | crontab -
    echo "✔ Cron job installed: $CRON_SCHEDULE"
    echo "  Command : $CRON_CMD"
    echo "  Log     : $LOG_FILE"
fi

# ── 6. Next steps ─────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════"
echo " Setup complete!  What to do next:"
echo ""
echo " 1. Download a GGUF model into $REPO_DIR/models/"
echo "    e.g.:"
echo "    huggingface-cli download bartowski/Llama-3.2-3B-Instruct-GGUF \\"
echo "        Llama-3.2-3B-Instruct-Q6_K.gguf --local-dir $REPO_DIR/models"
echo ""
echo " 2. Add background music MP3s to $REPO_DIR/song/<genre>/"
echo "    Genres: bright calm dark dramatic funky happy inspirational sad"
echo ""
echo " 3. Add optical flare videos (1.mp4 – 9.mp4) to $REPO_DIR/optic/"
echo ""
echo " 4. Place your YouTube client_secret.json in $REPO_DIR/"
echo "    Then run: python pipeline.py --module upload"
echo "    (first run will open a browser for OAuth)"
echo ""
echo " 5. Test a single run:"
echo "    python $PIPELINE --module feed"
echo ""
echo " Or run the full pipeline once:"
echo "    python $PIPELINE"
echo ""
echo " Cron runs automatically: $CRON_SCHEDULE  (every minute)"
echo " Cron log: $LOG_FILE"
echo "════════════════════════════════════════════════════════"
