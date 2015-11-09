#/usr/bin/env python2.7
import serial
import sys
import time
import os
import mailbox
from abc import ABCMeta, abstractmethod
from socket import gethostname

USER =os.environ["USER"]
MBOX = os.sep + os.path.join("var", "mail", USER)

class Wait:
    """Wait decorator"""

    MICROSEC = 10 ** -6

    def __init__(self, usecs):
        self.usecs = usecs

    def __call__(self, func):
        def wrap(*args, **kwargs):
            func(*args, **kwargs)
            time.sleep(self.usecs * self.MICROSEC)
        return wrap

    @staticmethod
    def wait(usecs):
        time.sleep(Wait.MICROSEC * usecs)


class VHD:
    """Raw access to the VHD via serial interface."""

    def __init__(self, port="/dev/ttyU0", baud=38400):
        self.ser = serial.Serial(port, baud, timeout=1)

    def write(self, msg):
        for ch in msg:
            self.ser.write(bytes(str(ch), encoding="ascii"))
            # Strictly speaking we should wait 200us, however, this visibly
            # slows down writing to the VHD. Presumably the interpeter overhead
            # is already greter than the required wait.
            #Wait.wait(200)

    @Wait(900)
    def clear(self):
        self.ser.write([0xe])

    @Wait(200)
    def cursor_home(self):
        """AKA form feed"""
        self.ser.write([0xc])

    @Wait(200)
    def carriage_return(self):
        self.ser.write([0xd])

    @Wait(900)
    def line_feed(self):
        self.ser.write([0xa])

    @Wait(200)
    def cursor_off(self):
        """AKA DC6"""
        self.ser.write([0x16])


class BasePlugiun(metaclass=ABCMeta):
    def __init__(self, vhd, duration):
        self.vhd = vhd
        self.duration = duration
        self.generator = self.make_generator()

    @abstractmethod
    def make_generator(self):
        pass


class TimePlugin(BasePlugiun):
    def make_generator(self):
        tm_s = time.strftime("%A %b %d, %Y")
        self.vhd.write(tm_s)
        self.vhd.line_feed()  # assume date doesn't change for duration of this screen
        for i in range(self.duration):
            self.vhd.carriage_return()
            tm_s = time.strftime("%H:%M:%S")
            self.vhd.write(tm_s)
            _ = yield


class MailPlugin(BasePlugiun):
    def make_generator(self):
        box = mailbox.mbox(MBOX)
        count = len(box)
        box.close()

        self.vhd.write("Mail: %s" % USER)
        self.vhd.line_feed()
        self.vhd.carriage_return()
        self.vhd.write("%d messages" % count)
        for i in range(self.duration):
            _ = yield


class HostNamePlugin(BasePlugiun):
    def make_generator(self):
        self.vhd.write(gethostname())
        self.vhd.line_feed()
        for i in range(self.duration):
            _ = yield


class Status:
    def __init__(self, vfd):
        self.vhd = vhd
        self.vhd.cursor_off()
        self.current_mode = -1
        self.modes = [HostNamePlugin, TimePlugin, MailPlugin]
        self.n_modes = len(self.modes)
        self.gen = None
        self.mode_duration = 5
        self.next_mode()

    def next_mode(self):
        self.vhd.clear()
        self.vhd.cursor_home()
        self.current_mode = (self.current_mode + 1) % self.n_modes
        plugin = self.modes[self.current_mode](self.vhd, self.mode_duration)
        self.gen = plugin.make_generator()

    def run(self):
        while True:
            try:
                self.gen.send(None)
            except StopIteration as e:
                self.next_mode()
                continue
            time.sleep(1)


if __name__ == "__main__":
    vhd = VHD()
    status = Status(vhd)
    status.run()
