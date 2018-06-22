#!/usr/local/bin/python -u

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

EXIT_CHAR = 0
def set_exit_char(exit_char):
    global EXIT_CHAR
    EXIT_CHAR = chr(ord(exit_char) - ord('@'))

set_exit_char('X')  # Control-X

class Logger(object):

    def __init__(self, log_file=None):
        self._log_file = log_file
        self._line = ''

    def log(self, log_str, end='\n'):
        if not self._log_file:
            return

        for char in log_str + end:
            if char == '\r':
                continue
            if len(self._line) == 0:
                self._line += self.timestamp()
            if char == '\n':
                print(self._line, file=self._log_file)
                self._line = ''
            else:
                self._line += char

    def print(self, log_str, end='\n'):
        print(log_str, end=end)
        if self._log_file:
            self.log(log_str, end=end)

    def timestamp(self):
        curr_time = round(time.time(), 4)
        time_str = time.strftime('%H:%M:%S', time.localtime(curr_time))
        time_str += '{:.4f}: '.format(curr_time - int(curr_time))[1:]
        return time_str


def is_usb_serial(device, args=None):
    """Checks device to see if its a USB Serial device.

    The caller already filters on the subsystem being 'tty'.

    If serial_num or vendor is provided, then it will further check to
    see if the serial number and vendor of the device also matches.
    """
    if 'ID_VENDOR' not in device:
        return False
    if not args is None:
        if args.port and args.port not in device.device_node:
            return False
        if args.vendor and not device['ID_VENDOR'].startswith(args.vendor):
            return False
        if args.serial and device['ID_SERIAL_SHORT'] != args.serial:
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
    log.print('Use Control-%c to exit.\r' % chr(ord(EXIT_CHAR) + ord('@')))

    if device['ID_VENDOR'].startswith('Synthetos'):
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
                        log.print("Serial.Read '%c' 0x%02x\r" % (x, ord(x)))
                pos = 0
                while True:
                    nl_pos = data.find('\n', pos)
                    if nl_pos < 0:
                        break
                    if nl_pos > 0 and data[nl_pos - 1] == '\r':
                        # already have \r before \n - just leave things be
                        pos = nl_pos + 1
                        continue
                    data = data[:nl_pos] + '\r' + data[nl_pos:]
                    pos = nl_pos + 2
                sys.stdout.write(data)
                sys.stdout.flush()
                log.log(data, end='')
            if fileno == sys.stdin.fileno():
                data = sys.stdin.read(1)
                if len(data) == 0:
                    continue
                if debug:
                    for x in data:
                        log.print("stdin.Read '%c' 0x%02x\r" % (x, ord(x)))
                if data[0] == EXIT_CHAR:
                    raise KeyboardInterrupt
                if echo:
                    sys.stdout.write(data)
                    if data[0] == '\r':
                        sys.stdout.write('\n')
                    sys.stdout.flush()
                if data[0] == '\n':
                    serial_port.write('\r')
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
        epilog="Press Control-%c to quit" % chr(ord(EXIT_CHAR) + ord('@'))
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

    global log
    log = Logger(open(args.log, "w"))

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
            if is_usb_serial(device):
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
            dev = {}
            if args.serial:
                dev['ID_SERIAL_SHORT'] = args.serial
            if args.vendor:
                dev['ID_VENDOR'] = args.vendor
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
                        data = sys.stdin.read(1)
                        if data[0] == EXIT_CHAR:
                            raise KeyboardInterrupt
    except KeyboardInterrupt:
        log.print('\r')
    except Exception:
        traceback.print_exc()
    # Restore stdin back to its old settings
    termios.tcsetattr(stdin_fd, termios.TCSANOW, old_settings)

main()
