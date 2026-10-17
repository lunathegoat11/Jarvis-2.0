#!/bin/bash
# Sets up Jarvis Nano's body server on the robot's Raspberry Pi and starts it
# at every boot. Run on the Pi from the robot folder:  bash setup.sh
# Do the build guide's hardware and Crickit steps first (I2C on, firmware,
# speaker installer, mute trace cut).
set -e
cd "$(dirname "$0")"

sudo apt install -y python3-picamera2 python3-venv alsa-utils
python3 -m venv --system-site-packages env
env/bin/pip install -r requirements.txt

TOKEN_FILE="$HOME/.jarvisbot-token"
if [ ! -f "$TOKEN_FILE" ]; then
  python3 -c 'import secrets; print(secrets.token_urlsafe(24))' > "$TOKEN_FILE"
  chmod 600 "$TOKEN_FILE"
fi
TOKEN=$(cat "$TOKEN_FILE")

sed -e "s|USER|$USER|g" -e "s|TOKEN|$TOKEN|g" jarvisbot.service | sudo tee /etc/systemd/system/jarvisbot.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now jarvisbot

echo
echo "Jarvis Nano's body is running on port 8080."
echo "Put these two lines in ~/.jarvis-nano/.env on the computer that runs Jarvis Nano:"
echo
echo "JARVIS_NANO_ROBOT=http://$(hostname).local:8080"
echo "JARVIS_NANO_TOKEN=$TOKEN"
