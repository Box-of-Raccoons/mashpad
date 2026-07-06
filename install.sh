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
# --no-install-recommends: espeak-ng's recommends can pull in speech-dispatcher
# (sd_espeak-ng), a console screen reader that speaks tty text over the app.
#
# Package roles beyond pygame/numpy/espeak/alsa:
#   libgl1-mesa-dri libegl1 libgles2 — the Mesa EGL/GLES userspace + the v3d DRI
#     driver. A bare Pi OS Lite image ships none of these (the text console uses
#     the kernel framebuffer directly), so without them SDL's kmsdrm/GL init dies
#     with "EGL not initialized" and mashpad crash-loops on a blank screen.
#   cage  — a single-app Wayland kiosk. mashpad runs INSIDE it: SDL's bare kmsdrm
#     backend does not present on the Pi 4's split GPU (v3d renders, vc4 scans
#     out), so the app renders black. cage drives the GL/scanout path correctly.
#   seatd — seat manager. cage (via libseat) needs a seat for DRM + VT access;
#     from a systemd system service there is no logind session, so seatd provides
#     it. Debian runs 'seatd -g video', so the socket is group-video and the
#     existing 'video' membership in the unit is all cage needs — no extra group.
if ! apt-get install -y --no-install-recommends \
        python3-pygame python3-numpy espeak-ng alsa-utils \
        libgl1-mesa-dri libegl1 libgles2 cage seatd; then
    echo "[install] ERROR: apt-get failed. Are you running as root (sudo bash install.sh)?"
    exit 1
fi
echo "[install] System packages installed."

echo "[install] Enabling seatd (seat manager for the cage kiosk)..."
systemctl enable --now seatd || \
    echo "[install] WARNING: could not enable seatd — mashpad may fail to acquire a seat."

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

echo "[install] Generating piano-melody notes..."
if ! sudo -u "${SCRIPT_USER}" env PYTHONPATH="${REPO_DIR}" \
        python3 -m mashpad.gen_notes; then
    echo "[install] WARNING: gen_notes failed."
    echo "          Run manually: cd ${REPO_DIR} && python3 -m mashpad.gen_notes"
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

# ── 5.5 Preflight: the runtime deps mashpad needs to actually render ──────────
#
# The original failure mode this guards against: a bare Pi OS Lite install would
# happily set up the service, then hand the user a black screen and a silent
# crash-loop because the GL/EGL userspace and the cage kiosk were never present.
# Fail loudly HERE, with the fix, instead of at boot with no hint.

echo "[install] Verifying display runtime prerequisites..."
PREFLIGHT_OK=1
for bin in cage seatd; do
    if ! command -v "${bin}" >/dev/null 2>&1; then
        echo "[install] ERROR: '${bin}' is not installed — the kiosk cannot start without it."
        PREFLIGHT_OK=0
    fi
done
if ! ldconfig -p 2>/dev/null | grep -q 'libEGL\.so\.1'; then
    echo "[install] ERROR: libEGL.so.1 not found — SDL/GL init will fail with 'EGL not initialized'."
    echo "          Install it with: apt-get install libgl1-mesa-dri libegl1 libgles2"
    PREFLIGHT_OK=0
fi
if [ "${PREFLIGHT_OK}" != "1" ]; then
    echo "[install] ERROR: display prerequisites are missing (see above). Aborting before"
    echo "          enabling the service so you don't boot into a blank screen."
    exit 1
fi
echo "[install] Display prerequisites present (cage, seatd, libEGL)."

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
