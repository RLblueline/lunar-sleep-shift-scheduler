#!/bin/sh
# Starts the crew display full screen once the data service answers. Launched from the desktop autostart.
# Scale 2: on the 1280x720 Touch Display 2 (0.121 mm per pixel) a 48 px button becomes 11.6 mm
# and 12 px text 2.9 mm (NASA-STD-3001 V2 10066). Gloved input goes through the hardware keys.
until curl -sf http://127.0.0.1:8642/api/health >/dev/null; do sleep 0.5; done
BROWSER=$(command -v chromium-browser || command -v chromium)
exec "$BROWSER" --kiosk --noerrdialogs --disable-infobars --incognito \
  --disable-features=Translate --check-for-update-interval=31536000 \
  --force-dark-mode --force-device-scale-factor=2 http://127.0.0.1:8642/
