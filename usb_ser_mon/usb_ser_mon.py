#!/usr/bin/python3

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
import os
import tty
import termios
import traceback
import syslog
import argparse
import time
from collections import namedtuple

EXIT_CHAR = 0
def set_exit_char(exit_char):
    global EXIT_CHAR
    EXIT_CHAR = ord(exit_char) - ord('@')

set_exit_char('X')  # Control-X

class Logger(object):

    def __init__(self, log_file=None):
        self._log_file = log_file
        self._line = b''

    def log(self, log_bytes):
        if not self._log_file:
            return

        for char in log_bytes:
            char = bytes([char])
            if char == b'\r':
                continue
            if len(self._line) == 0:
                self._line += self.timestamp()
            self._line += char
            if char == b'\n':
                self._log_file.write(self._line)
                self._line = b''


    def print(self, log_str, end='\n'):
        # print accepts a string, but assumes it's ascii-only
        log_str += end
        sys.__stdout__.write(log_str)
        if self._log_file:
            self.log(log_str.encode('ascii'))

    def timestamp(self):
        curr_time = round(time.time(), 4)
        time_str = time.strftime('%H:%M:%S', time.localtime(curr_time))
        time_str += '{:.4f}: '.format(curr_time - int(curr_time))[1:]
        return time_str.encode('ascii')

    def char(self, prefix, c):
        self.print( "%s.Read '%c' 0x%02x\r" % (prefix, chr(c) if c >= 0x20 and c < 0x7f else '?', c))


def is_usb_serial(device, args=None):
    """Checks device to see if its a USB Serial device.

    The caller already filters on the subsystem being 'tty'.

    If serial_num or vendor is provided, then it will further check to
    see if the serial number and vendor of the device also matches.
    """
    prop = device.properties
    if 'ID_VENDOR' not in prop:
        return False
    if not args is None:
        if args.port and args.port not in device.device_node:
            return False
        if args.vendor:
            if 'ID_VENDOR' not in prop:
              return False
            if not prop['ID_VENDOR'].startswith(args.vendor):
              return False
        if args.serial:
            if 'ID_SERIAL_SHORT' not in prop:
                return False
            if prop['ID_SERIAL_SHORT'] != args.serial:
                return False
        if args.intf:
            if 'ID_USB_INTERFACE_NUM' not in prop:
                return False
            if prop['ID_USB_INTERFACE_NUM'] != args.intf:
                return False
    return True


def extra_info(device):
    #for x in device:
    #    print(x, device[x])
    output = ''
    prop = device.properties
    if 'ID_VENDOR_ID' in prop:
        output = ' {}:{}'.format(prop['ID_VENDOR_ID'], prop['ID_MODEL_ID'])
    extra_items = []
    if 'ID_VENDOR' in prop:
        extra_items.append("vendor '%s'" % prop['ID_VENDOR'])
    if 'ID_SERIAL_SHORT' in prop:
        extra_items.append("serial '%s'" % prop['ID_SERIAL_SHORT'])
    if 'ID_USB_INTERFACE_NUM' in prop:
        extra_items.append('intf {}'.format(prop['ID_USB_INTERFACE_NUM']))
    if extra_items:
        output += ' with '
        output += ' '.join(extra_items)
    return output


def usb_serial_mon(monitor, device, baud=115200, debug=False, echo=False):
    """Monitors the serial port from a given USB serial device.

    This function open the USB serial port associated with device, and
    will read characters from it and send to stdout. It will also read
    characters from stdin and send them to the device.

    This function returns when the deivce disconnects (or is
    disconnected).

    """
    port_name = device.device_node
    log.print('USB Serial device%s connected @%s\r' % (
              extra_info(device), port_name))
    log.print('Use Control-%c to exit.\r' % chr(EXIT_CHAR + ord('@')))

    if device.properties['ID_VENDOR'].startswith('Synthetos'):
        echo = True

    epoll = select.epoll()
    epoll.register(monitor.fileno(), select.POLLIN)

    try:
        serial_port = serial.Serial(port=port_name,
                                    baudrate=baud,
                                    timeout=0.001,
                                    bytesize=serial.EIGHTBITS,
                                    parity=serial.PARITY_NONE,
                                    stopbits=serial.STOPBITS_ONE,
                                    xonxoff=False,
                                    rtscts=False,
                                    dsrdtr=False)
    except serial.serialutil.SerialException:
        log.print("Unable to open port '%s'\r" % port_name)
        return

    serial_fd = serial_port.fileno()
    tty.setraw(serial_fd)
    new_settings = termios.tcgetattr(serial_fd)
    new_settings[6][termios.VTIME] = 0
    new_settings[6][termios.VMIN] = 1
    termios.tcsetattr(serial_fd, termios.TCSANOW, new_settings)

    epoll.register(serial_port.fileno(), select.POLLIN)
    epoll.register(sys.stdin.fileno(), select.POLLIN)

    while True:
        events = epoll.poll()
        for fileno, _ in events:
            if fileno == monitor.fileno():
                dev = monitor.poll()
                if (dev.device_node != port_name or
                        dev.action != 'remove'):
                    continue
                log.print('USB Serial device @%s disconnected.\r' % port_name)
                log.print('\r')
                serial_port.close()
                return
            if fileno == serial_port.fileno():
                try:
                    data = serial_port.read(256)
                except serial.serialutil.SerialException:
                    log.print('USB Serial device @%s disconnected.\r' % port_name)
                    log.print('\r')
                    serial_port.close()
                    return
                if debug:
                    for x in data:
                        log.char("Serial", x)
                pos = 0
                while True:
                    nl_pos = data.find(b'\n', pos)
                    if nl_pos < 0:
                        break
                    if nl_pos > 0 and data[nl_pos-1:nl_pos] == b'\r':
                        # already have \r before \n - just leave things be
                        pos = nl_pos + 1
                        continue
                    data = data[:nl_pos] + b'\r' + data[nl_pos:]
                    pos = nl_pos + 2
                sys.stdout.write(data)
                sys.stdout.flush()
                log.log(data)
            if fileno == sys.stdin.fileno():
                data = os.read(fileno, 1)
                if len(data) == 0:
                    continue
                if debug:
                    for x in data:
                        log.char("stdin", x)
                if data[0] == EXIT_CHAR:
                    raise KeyboardInterrupt
                if echo:
                    sys.stdout.write(data)
                    if data[0:1] == b'\r':
                        sys.stdout.write(b'\n')
                    sys.stdout.flush()
                if data[0:1] == b'\n':
                    serial_port.write(b'\r')
                else:
                    serial_port.write(data)
                time.sleep(0.002)

def main():
    """The main program."""

    default_baud = 115200
    parser = argparse.ArgumentParser(
        prog="usb-ser-mon.py",
        usage="%(prog)s [options] [command]",
        description="Monitor serial output from USB Serial devices",
        epilog="Press Control-%c to quit" % chr(EXIT_CHAR + ord('@'))
    )
    parser.add_argument(
        "-p", "--port",
        dest="port",
        action="store",
        help="Set the port to connect to",
        default=None
    )
    parser.add_argument(
        "-b", "--baud",
        dest="baud",
        action="store",
        type=int,
        help="Set the baudrate used (default = %d)" % default_baud,
        default=default_baud
    )
    parser.add_argument(
        "-d", "--debug",
        dest="debug",
        action="store_true",
        help="Turn on debugging",
        default=False
    )
    parser.add_argument(
        "-e", "--echo",
        dest="echo",
        action="store_true",
        help="Turn on local echo",
        default=False
    )
    parser.add_argument(
        "-i", "--intf",
        dest="intf",
        help="Connect to USB serial device with a given interface",
        default=None
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
        help="Connect to USB Serial device with a given serial number",
        default=None
    )
    parser.add_argument(
        "--log",
        dest="log",
        default="usb-ser-mon.log",
        help="Log the session to a file."
    )
    parser.add_argument(
        "-n", "--vendor",
        dest="vendor",
        help="Connect to USB Serial device with a given vendor",
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
        "-y",
        dest="ctrl_y_exit",
        action="store_true",
        help="Use Control-Y to exit rather than Control-X",
        default=False
    )
    args = parser.parse_args(sys.argv[1:])
    sys.stdout = sys.stdout.buffer

    global log
    log = Logger(open(args.log, "wb"))

    if args.verbose:
        log.print('pyudev version = %s' % pyudev.__version__)
        log.print('echo = %d' % args.echo)

    if args.ctrl_y_exit:
        set_exit_char('Y')

    context = pyudev.Context()
    context.log_priority = syslog.LOG_NOTICE

    if args.list:
        detected = False
        for device in context.list_devices(subsystem='tty'):
            if is_usb_serial(device, args):
                log.print('USB Serial Device%s found @%s\r' % (
                          extra_info(device), device.device_node))
                detected = True
        if not detected:
            log.print('No USB Serial devices detected.\r')
        return

    stdin_fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(stdin_fd)
    try:
        # Make some changes to stdin. We want to turn off canonical
        # processing  (so that ^H gets sent to the device), turn off echo,
        # and make it unbuffered.
        tty.setraw(stdin_fd)
        new_settings = termios.tcgetattr(stdin_fd)
        new_settings[3] &= ~(termios.ICANON | termios.ECHO)
        new_settings[6][termios.VTIME] = 0
        new_settings[6][termios.VMIN] = 1
        termios.tcsetattr(stdin_fd, termios.TCSANOW, new_settings)

        monitor = pyudev.Monitor.from_netlink(context)
        monitor.start()
        monitor.filter_by('tty')

        # Check to see if the USB Serial device is already present.
        for device in context.list_devices(subsystem='tty'):
            if is_usb_serial(device, args):
                usb_serial_mon(monitor, device, baud=args.baud,
                        debug=args.debug, echo=args.echo)

        # Otherwise wait for the teensy device to connect
        while True:
            dev = namedtuple('Device', ['properties'])({})
            if args.serial:
                dev.properties['ID_SERIAL_SHORT'] = args.serial
            if args.vendor:
                dev.properties['ID_VENDOR'] = args.vendor
            log.print('Waiting for USB Serial Device%s ...\r' % extra_info(dev))
            epoll = select.epoll()
            epoll.register(monitor.fileno(), select.POLLIN)
            epoll.register(sys.stdin.fileno(), select.POLLIN)
            while True:
                events = epoll.poll()
                for fileno, _ in events:
                    if fileno == monitor.fileno():
                        device = monitor.poll()
                        if device.action != 'add':
                            continue
                        if is_usb_serial(device, args):
                            usb_serial_mon(monitor, device, baud=args.baud,
                                debug=args.debug, echo=args.echo)
                            break
                    if fileno == sys.stdin.fileno():
                        data = os.read(fileno, 1)
                        if data[0] == EXIT_CHAR:
                            raise KeyboardInterrupt
    except KeyboardInterrupt:
        log.print('\r')
    except Exception:
        traceback.print_exc()
    # Restore stdin back to its old settings
    termios.tcsetattr(stdin_fd, termios.TCSANOW, old_settings)

if __name__ == "__main__":
    main()
