#!/usr/bin/env python

"""Program which detects USB serial ports.
This program will search for a USB serial port using a search criteria.
In its simplest form, you can use the -l (--list) option to list all of
the detected serial ports.
You can also add the following filters:
--vid 2341      Will only match devices with a Vendor ID of 2341.
--pid 0001      Will only match devices with a Product ID of 0001
--vendor Micro  Will only match devices whose vendor name starts with Micro
--seral  00123  Will only match devices whose serial number stats with 00123
If you use -l or --list then detailed information about all of the matches
will be printed. If you don't use -l (or --list) then only the name of
the device will be printed (i.e. /dev/ttyACM0). This is useful in scripts
where you want to pass the name of the serial port into a utiity to open.
"""

from __future__ import print_function

import pyudev
import sys
import argparse


def is_usb_serial(device, vid=None, pid=None, vendor=None, serial=None, *args,
                  **kwargs):
    """Checks device to see if its a USB Serial device.
    The caller already filters on the subsystem being 'tty'.
    If serial_num or vendor is provided, then it will further check to
    see if the serial number and vendor of the device also matches.
    """
    if 'ID_VENDOR' not in device.properties:
        return False
    if vid is not None:
        if device.properties['ID_VENDOR_ID'] != vid:
            return False
    if pid is not None:
        if device.properties['ID_MODEL_ID'] != pid:
            return False
    if vendor is not None:
        if 'ID_VENDOR' not in device.properties:
            return False
        if not device.properties['ID_VENDOR'].startswith(vendor):
            return False
    if serial is not None:
        if 'ID_SERIAL_SHORT' not in device.properties:
            return False
        if not device.properties['ID_SERIAL_SHORT'].startswith(serial):
            return False
    return True


def extra_info(device):
    extra_items = []
    if 'ID_VENDOR' in device.properties:
        extra_items.append("vendor '%s'" % device.properties['ID_VENDOR'])
    if 'ID_SERIAL_SHORT' in device.properties:
        extra_items.append("serial '%s'" % device.properties['ID_SERIAL_SHORT'])
    if extra_items:
        return ' with ' + ' '.join(extra_items)
    return ''


def list_devices(vid=None, pid=None, vendor=None, serial=None, *args,
                 **kwargs):
    devs = []
    context = pyudev.Context()
    for device in context.list_devices(subsystem='tty'):
        if is_usb_serial(device, vid=vid, pid=pid, vendor=vendor,
                         serial=serial):
            devs.append([device.properties['ID_VENDOR_ID'], device.properties['ID_MODEL_ID'],
                         extra_info(device), device.device_node])
    return devs


def main():
    """The main program."""
    parser = argparse.ArgumentParser(
        prog="find-port.py",
        usage="%(prog)s [options] [command]",
        description="Find the /dev/tty port for a USB Serial devices",
    )
    parser.add_argument(
        "-l", "--list",
        dest="list",
        action="store_true",
        help="List USB Serial devices currently connected"
    )
    parser.add_argument(
        "-s", "--serial",
        dest="serial",
        help="Only show devices with the indicated serial number",
        default=None,
    )
    parser.add_argument(
        "-n", "--vendor",
        dest="vendor",
        help="Only show devices with the indicated vendor name",
        default=None
    )
    parser.add_argument(
        "--pid",
        dest="pid",
        action="store",
        help="Only show device with indicated PID",
        default=None
    )
    parser.add_argument(
        "-v", "--verbose",
        dest="verbose",
        action="store_true",
        help="Turn on verbose messages",
        default=False
    )
    parser.add_argument(
        "--vid",
        dest="vid",
        action="store",
        help="Only show device with indicated VID",
        default=None
    )
    args = parser.parse_args(sys.argv[1:])

    if args.verbose:
        print('pyudev version = %s' % pyudev.__version__)

    if args.list:
        '''Print all USB Serial devices'''
        devices = list_devices(**vars(args))
        for device in devices:
            print('USB Serial Device {}:{}{} found @{}'.format(*device))
        if len(devices) == 0:
            print('No USB Serial devices detected.')
        return

    context = pyudev.Context()
    for device in context.list_devices(subsystem='tty'):
        if is_usb_serial(device, **vars(args)):
            print(device.device_node)
            return
    sys.exit(1)


if __name__ == "__main__":
    main()
