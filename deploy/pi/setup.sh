#!/bin/bash
# One-time setup on Raspberry Pi OS (Bookworm, desktop). Run as root from the repo root:
#   sudo bash deploy/pi/setup.sh
# Review each step first; steps 5 and 6 change how the Pi boots.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"

echo "1. Packages (installed once while you still have internet)"
apt-get update
apt-get install -y python3-gpiozero python3-smbus2 curl i2c-tools
apt-get install -y chromium-browser || apt-get install -y chromium

echo "2. Service user and data directories"
id lsst >/dev/null 2>&1 || useradd --system --groups gpio,i2c --home /data/lsst lsst
mkdir -p /data/lsst/state /media/lsst-usb/lsst /etc/lsst
chown -R lsst:lsst /data/lsst /media/lsst-usb/lsst

echo "3. Hardware: I2C (sensor, battery monitor), backlight access, clean shutdown, watchdog"
raspi-config nonint do_i2c 0
install -m 644 "$REPO/deploy/pi/99-lsst-backlight.rules" /etc/udev/rules.d/99-lsst-backlight.rules
udevadm control --reload && udevadm trigger --subsystem-match=backlight
echo 'lsst ALL=(root) NOPASSWD: /usr/bin/systemctl poweroff' > /etc/sudoers.d/lsst-poweroff
chmod 440 /etc/sudoers.d/lsst-poweroff && visudo -cf /etc/sudoers.d/lsst-poweroff
# The Pi 5 has its own real-time clock: fit the RTC backup cell to the J5 BAT connector so
# the mission clock survives a dead main battery. No overlay is needed.
grep -q "^RuntimeWatchdogSec" /etc/systemd/system.conf || echo "RuntimeWatchdogSec=15" >> /etc/systemd/system.conf

echo "4. Install the app (make the /data partition and mount the USB drive first: see step 6)"
rm -rf /opt/lunar-sleep-shift && cp -r "$REPO" /opt/lunar-sleep-shift
python3 /opt/lunar-sleep-shift/web/build.py
cp "$REPO/deploy/pi/lsst.env" /etc/lsst/lsst.env
cp "$REPO/deploy/pi/lsst.service" /etc/systemd/system/lsst.service
systemctl daemon-reload && systemctl enable --now lsst.service

echo "5. Kiosk autostart for the desktop user"
install -m 755 "$REPO/deploy/pi/kiosk.sh" /usr/local/bin/lsst-kiosk
AUTOSTART=/etc/xdg/autostart/lsst-kiosk.desktop
printf '[Desktop Entry]\nType=Application\nName=LSST kiosk\nExec=/usr/local/bin/lsst-kiosk\n' > "$AUTOSTART"

cat <<'NOTE'
6. Manual steps (do these last, they need a reboot):
   - Make a separate ext4 data partition mounted at /data (noatime). Add the USB drive to
     /etc/fstab at /media/lsst-usb with the 'nofail' option.
   - Turn on the read-only root overlay so power cuts cannot damage the OS:
       sudo raspi-config  ->  Performance Options  ->  Overlay File System  ->  enable
     /data and the USB drive stay writable because they are separate filesystems.
   - Reboot. The service and kiosk start on their own.
NOTE
