usb_ser_mon
==============

A serial monitor for USB Serial devices.

usb-ser-mon.py will automatically detect your connected USB Serial device and
print the output from it.

This is similar in functionality to the Arduino serial monitor, except that
usb-ser-mon.py deals with the device disconnects automtically, and will wait
for your device to reconnect.

If you have more than one USB device connected, you can use the -s
option to specify the serial number of the device you wish to connect to,
or use the -n command to specify the device vendor.

Currently, this program only works under linux.

It was tested with the following devices:
  - Teensy 3.1
  - STM32F4DISCOVERY board
  - Prolific USB to Serial adapter

Installation
============
Download or checkout this repository. With a terminal opened in the project directory.
Install using pip:
```
pip install .
```

If you want to edit the files in this directory and use them, install in edit mode:
```
pip install -e .
```

Usage
=====

Use -l to list all of the connected devices.
```
./usb-ser-mon.py -l
````

will show you the currently connected devices, for example:
```
USB Serial Device with vendor 'Teensyduino' serial '21973' found @/dev/ttyACM1
USB Serial Device with vendor 'Prolific_Technology_Inc.' found @/dev/ttyUSB0
USB Serial Device with vendor 'STMicroelectronics' serial '00000000050C' found @/dev/ttyACM0
```

If you want to connect with the STM device (an STM32FDISCOVERY board in this situation), then you might do:
```
./usb-ser-mon.py -n Teensy
```

and then see:
```
USB Serial device with vendor 'Teensyduino' serial '21973' connected @/dev/ttyACM1

>>>
```

In the previous example the Teensy was already connected. If I unplug and replug the Teensy device then I'd see:
```
USB Serial device @ /dev/ttyACM1  disconnected.

Waiting for USB Serial Device with vendor 'Teensy' ...
USB Serial device with vendor 'Teensyduino' serial '21973' connected @/dev/ttyACM1
Done executing '/src/main.py'
Micro Python for Teensy 3.1
Type "help()" for more information.
>>>
```

You only need to use as many characters as are required to uniquely identify a
device, so I could use ```./usb-ser-mon.py -n STM``` to connect to the
Discovery board.

Use Control-X to exit from usb-ser-mon.py.

The ```mk-udev-rules-stm32.sh``` script will create the appropriate udev rules
for the STM32F4 series processors.

The ```mk-udev-rules-pyboard.sh``` script will create the appropriate udev rules
for the MicroPython pyboard.

The ```mk-udev-rules-teensy.sh``` script will create the appropriate udev rules
for the Teensy 3.1 board.
