#!/bin/sh

sudo sh -c 'cat > /etc/udev/rules.d/49-pyboard.rules' <<EOF
# f055:9800, 9801, 9802 MicroPython pyboard
ATTRS{idVendor}=="f055", ENV{ID_MM_DEVICE_IGNORE}="1"
ATTRS{idVendor}=="f055", ENV{MTP_NO_PROBE}="1"
SUBSYSTEMS=="usb", ATTRS{idVendor}=="f055", MODE:="0666"
KERNEL=="ttyACM*", ATTRS{idVendor}=="f055", MODE:="0666"

# Add lines like the following to create custom named device nodes based on the
# serial number.
# KERNEL=="ttyACM*", ATTRS{idVendor}=="f055", ATTRS{serial}=="385435603432", SYMLINK+="pyboard", MODE:="0666"
EOF

sudo udevadm control --reload-rules

echo "Unplug and replug your device to activate the new rules."
