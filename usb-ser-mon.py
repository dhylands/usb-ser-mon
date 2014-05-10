#!/usr/bin/python -u

"""Program which auto-connects to USB serial devices.

This program waits for the device to be connected and when the device is
disconnected, then it will go back to waiting for a device to once again
be connected.

"""

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

def is_usb_serial(device, serial_num=None, vendor=None):
    """Checks device to see if its a USB Serial device.

    The caller already filters on the subsystem being 'tty'.

    If serial_num or vendor is provided, then it will further check to
    see if the serial number and vendor of the device also matches.
    """
    if 'ID_VENDOR' not in device:
        return False
    if not vendor is None:
        if not device['ID_VENDOR'].startswith(vendor):
            return False
    if not serial_num is None:
        if device['ID_SERIAL_SHORT'] != serial_num:
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


def usb_serial_mon(monitor, device, baud=115200):
    """Monitors the serial port from a given USB serial device.

    This function open the USB serial port associated with device, and
    will read characters from it and send to stdout. It will also read
    characters from stdin and send them to the device.

    This function returns when the deivce disconnects (or is
    disconnected).

    """
    port_name = device.device_node
    print 'USB Serial device%s connected @%s\r' % (
        extra_info(device), port_name)
    print 'Use Control-%c to exit.\r' % chr(ord(EXIT_CHAR) + ord('@'))
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
        print "Unable to open port '%s'\r" % port_name
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
                print 'USB Serial device @', port_name, ' disconnected.\r'
                print '\r'
                serial_port.close()
                return
            if fileno == serial_port.fileno():
                try:
                    data = serial_port.read(256)
                except serial.serialutil.SerialException:
                    print 'USB Serial device @', port_name, ' disconnected.\r'
                    print '\r'
                    serial_port.close()
                    return
                #for x in data:
                #    print "Serial.Read '%c' 0x%02x\r" % (x, ord(x))
                sys.stdout.write(data)
                sys.stdout.flush()
            if fileno == sys.stdin.fileno():
                data = sys.stdin.read(1)
                #for x in data:
                #    print "stdin.Read '%c' 0x%02x\r" % (x, ord(x))
                if data[0] == EXIT_CHAR:
                    raise KeyboardInterrupt
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
        "-b", "--baud",
        dest="baud",
        action="store",
        type=int,
        help="Set the baudrate used (default = %d)" % default_baud,
        default=default_baud
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
        help="Connect to USB Serial device with a given serial number"
    )
    parser.add_argument(
        "-n", "--vendor",
        dest="vendor",
        help="Connect to USB Serial device with a given vendor"
    )
    parser.add_argument(
        "-v", "--verbose",
        dest="verbose",
        action="store_true",
        help="Turn on verbose messages",
        default=False
    )
    args = parser.parse_args(sys.argv[1:])

    if args.verbose:
        print 'pyudev version =', pyudev.__version__

    context = pyudev.Context()
    context.log_priority = syslog.LOG_NOTICE

    if args.list:
        detected = False
        for device in context.list_devices(subsystem='tty'):
            if is_usb_serial(device):
                print 'USB Serial Device%s found @%s\r' % (
                    extra_info(device), device.device_node)
                detected = True
        if not detected:
            print 'No USB Serial devices detected.\r'
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
            if is_usb_serial(device, serial_num=args.serial, vendor=args.vendor):
                usb_serial_mon(monitor, device, baud=args.baud)

        # Otherwise wait for the teensy device to connect
        while True:
            dev = {}
            if args.serial:
                dev['ID_SERIAL_SHORT'] = args.serial
            if args.vendor:
                dev['ID_VENDOR'] = args.vendor
            print 'Waiting for USB Serial Device%s ...\r' % extra_info(dev)
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
                        if is_usb_serial(device, serial_num=args.serial, vendor=args.vendor):
                            usb_serial_mon(monitor, device, baud=args.baud)
                            break
                    if fileno == sys.stdin.fileno():
                        data = sys.stdin.read(1)
                        if data[0] == EXIT_CHAR:
                            raise KeyboardInterrupt
    except KeyboardInterrupt:
        print '\r\n'
    except Exception:
        traceback.print_exc()
    # Restore stdin back to its old settings
    termios.tcsetattr(stdin_fd, termios.TCSANOW, old_settings)

main()
