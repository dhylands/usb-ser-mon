#!/usr/bin/python -u

"""Program which auto-connects to USB serial devices.

This program waits for the device to be connected and when the device is
disconnected, then it will go back to waiting for a device to once again
be connected.

"""

from __future__ import print_function

import select
import pyudev
import serial
import sys
import tty
import termios
import traceback
import syslog
import argparse
import time

EXIT_CHAR = chr(ord('X') - ord('@'))    # Control-X

def is_usb_serial(device, args):
    """Checks device to see if its a USB Serial device.

    The caller already filters on the subsystem being 'tty'.

    If serial_num or vendor is provided, then it will further check to
    see if the serial number and vendor of the device also matches.
    """
    if 'ID_VENDOR' not in device:
        return False
    if not args.vid is None:
        if device['ID_VENDOR_ID'] != args.vid:
            return False
    if not args.pid is None:
        if device['ID_MODEL_ID'] != args.pid:
            return False
    if not args.vendor is None:
        if not device['ID_VENDOR'].startswith(args.vendor):
            return False
    if not args.serial is None:
        if not device['ID_SERIAL_SHORT'].startswith(args.serial):
            return False
    return True


def extra_info(device):
    extra_items = []
    if 'ID_VENDOR' in device:
        extra_items.append("vendor '%s'" % device['ID_VENDOR'])
    if 'ID_SERIAL_SHORT' in device:
        extra_items.append("serial '%s'" % device['ID_SERIAL_SHORT'])
    if extra_items:
        return ' with ' + ' '.join(extra_items)
    return ''


def main():
    """The main program."""

    default_baud = 115200
    parser = argparse.ArgumentParser(
        prog="find-port.py",
        usage="%(prog)s [options] [command]",
        description="Find the /dev/tty port for a USB Serial devices",
    )
    parser.add_argument(
        "-d", "--debug",
        dest="debug",
        action="store_true",
        help="Turn on debugging",
        default=False
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

    context = pyudev.Context()

    if args.list:
        detected = False
        for device in context.list_devices(subsystem='tty'):
            if is_usb_serial(device, args):
                print('USB Serial Device %s:%s%s found @%s\r' % (
                      device['ID_VENDOR_ID'], device['ID_MODEL_ID'],
                      extra_info(device), device.device_node))
                detected = True
        if not detected:
            print('No USB Serial devices detected.\r')
        return

    for device in context.list_devices(subsystem='tty'):
        if is_usb_serial(device, args):
            print(device.device_node)
            return
    sys.exit(1)


main()
