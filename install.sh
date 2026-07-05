#!/usr/bin/env bash
# install.sh — idempotent Pi installer for mashpad
#
# Usage:  sudo bash install.sh
# Run from the root of the repository checkout.
#
# Uses set -u (undefined variables are errors) but NOT set -e, so the optional
# piper steps can fail without aborting the whole install.

set -u

# ── Resolve paths ─────────────────────────────────────────────────────────────

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Run generators as the invoking user so file ownership stays right.
SCRIPT_USER="${SUDO_USER:-$(whoami)}"

SERVICE_NAME="mashpad"
SERVICE_SRC="${REPO_DIR}/mashpad.service"
SERVICE_DEST="/etc/systemd/system/${SERVICE_NAME}.service"

PIPER_MODEL_NAME="en_US-lessac-medium"
PIPER_VOICES_DIR="/home/${SCRIPT_USER}/.local/share/piper-voices"
PIPER_MODEL="${PIPER_VOICES_DIR}/${PIPER_MODEL_NAME}.onnx"
PIPER_MODEL_CONFIG="${PIPER_VOICES_DIR}/${PIPER_MODEL_NAME}.onnx.json"
PIPER_BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium"
PIPER_MODEL_URL="${PIPER_BASE_URL}/${PIPER_MODEL_NAME}.onnx"
PIPER_MODEL_CONFIG_URL="${PIPER_BASE_URL}/${PIPER_MODEL_NAME}.onnx.json"

# ── 1. System packages ────────────────────────────────────────────────────────

echo "[install] Updating package index..."
if ! apt-get update; then
    echo "[install] WARNING: apt-get update failed; trying install with the existing index."
fi

echo "[install] Installing system packages..."
if ! apt-get install -y python3-pygame python3-numpy espeak-ng alsa-utils; then
    echo "[install] ERROR: apt-get failed. Are you running as root (sudo bash install.sh)?"
    exit 1
fi
echo "[install] System packages installed."

# ── 2. piper-tts (optional — espeak is the fallback) ─────────────────────────

PIPER_OK=0
echo "[install] Installing piper-tts via pip (failure is tolerated; espeak-ng is the fallback)..."
if pip install piper-tts --break-system-packages 2>&1; then
    echo "[install] piper-tts installed."
    PIPER_OK=1
else
    echo "[install] piper-tts install failed — voice clips will be generated with espeak-ng."
fi

# ── 3. Download piper voice model ─────────────────────────────────────────────

if [ "${PIPER_OK}" = "1" ]; then
    if [ ! -f "${PIPER_MODEL}" ] || [ ! -f "${PIPER_MODEL_CONFIG}" ]; then
        echo "[install] Downloading piper voice model ${PIPER_MODEL_NAME} (~60 MB)..."
        sudo -u "${SCRIPT_USER}" mkdir -p "${PIPER_VOICES_DIR}"
        DL_OK=1
        if ! sudo -u "${SCRIPT_USER}" wget -q --show-progress \
                -O "${PIPER_MODEL}" "${PIPER_MODEL_URL}"; then
            echo "[install] Model .onnx download failed."
            DL_OK=0
        fi
        if [ "${DL_OK}" = "1" ] && ! sudo -u "${SCRIPT_USER}" wget -q \
                -O "${PIPER_MODEL_CONFIG}" "${PIPER_MODEL_CONFIG_URL}"; then
            echo "[install] Model config download failed."
            DL_OK=0
        fi
        if [ "${DL_OK}" = "1" ]; then
            echo "[install] Voice model downloaded to ${PIPER_VOICES_DIR}."
        else
            echo "[install] Voice model download failed — falling back to espeak-ng."
            PIPER_OK=0
        fi
    else
        echo "[install] Voice model already present, skipping download."
    fi
fi

# ── 4. Generate sound effects ─────────────────────────────────────────────────

echo "[install] Generating sound effects..."
if ! sudo -u "${SCRIPT_USER}" env PYTHONPATH="${REPO_DIR}" \
        python3 -m mashpad.gen_effects; then
    echo "[install] WARNING: gen_effects failed."
    echo "          Run manually: cd ${REPO_DIR} && python3 -m mashpad.gen_effects"
fi

# ── 5. Generate voice clips ───────────────────────────────────────────────────

echo "[install] Generating voice clips..."
if [ "${PIPER_OK}" = "1" ]; then
    if ! sudo -u "${SCRIPT_USER}" env PYTHONPATH="${REPO_DIR}" \
            python3 -m mashpad.gen_voice --engine piper --voice "${PIPER_MODEL}"; then
        echo "[install] gen_voice (piper) failed — retrying with espeak-ng..."
        if ! sudo -u "${SCRIPT_USER}" env PYTHONPATH="${REPO_DIR}" \
                python3 -m mashpad.gen_voice --engine espeak; then
            echo "[install] WARNING: gen_voice (espeak) also failed."
            echo "          Run manually: cd ${REPO_DIR} && python3 -m mashpad.gen_voice --engine espeak"
        fi
    fi
else
    if ! sudo -u "${SCRIPT_USER}" env PYTHONPATH="${REPO_DIR}" \
            python3 -m mashpad.gen_voice --engine espeak; then
        echo "[install] WARNING: gen_voice failed."
        echo "          Run manually: cd ${REPO_DIR} && python3 -m mashpad.gen_voice --engine espeak"
    fi
fi

# ── 6. Install and enable the systemd service ─────────────────────────────────

echo "[install] Installing systemd service..."
sed \
    -e "s|@REPO@|${REPO_DIR}|g" \
    -e "s|@USER@|${SCRIPT_USER}|g" \
    "${SERVICE_SRC}" > "${SERVICE_DEST}"
echo "[install] Service written to ${SERVICE_DEST}."
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}.service"
echo "[install] ${SERVICE_NAME}.service enabled."

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo "[install] Done.  Reboot to start mashpad automatically."
echo "          To start now without rebooting: systemctl start ${SERVICE_NAME}"
