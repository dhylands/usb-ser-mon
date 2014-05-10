#!/bin/sh

sudo sh -c 'cat > /etc/udev/rules.d/49-pyboard.rules' <<EOF
# f055:9800 MicroPython pyboard
ATTRS{idVendor}=="f055", ATTRS{idProduct}=="9800", ENV{ID_MM_DEVICE_IGNORE}="1"
ATTRS{idVendor}=="f055", ATTRS{idProduct}=="9800", ENV{MTP_NO_PROBE}="1"
SUBSYSTEMS=="usb", ATTRS{idVendor}=="f055", ATTRS{idProduct}=="9800", MODE:="0666"
KERNEL=="ttyACM*", ATTRS{idVendor}=="f055", ATTRS{idProduct}=="9800", MODE:="0666"
EOF

sudo udevadm control --reload-rules

echo "Unplug and replug your device to activate the new rules."
