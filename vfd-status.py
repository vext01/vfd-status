#/usr/bin/env python2.7
import serial
import sys
import time
import os
import mailbox

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

def mk_mail(vhd, ticks):
    box = mailbox.mbox(MBOX)
    count = len(box)
    box.close()

    vhd.write("Mail: %s" % USER)
    vhd.line_feed()
    vhd.carriage_return()
    vhd.write("%d messages" % count)
    for i in range(ticks):
        _ = yield

def mk_hostname(vhd, ticks):
    vhd.write(gethostname())
    vhd.line_feed()
    for i in range(ticks):
        _ = yield

def mk_time(vhd, ticks):
    tm_s = time.strftime("%A %b %d, %Y")
    vhd.write(tm_s)
    vhd.line_feed()  # assume date doesn't change for duration of this screen
    for i in range(ticks):
        vhd.carriage_return()
        tm_s = time.strftime("%H:%M:%S")
        vhd.write(tm_s)
        _ = yield

class Status:
    def __init__(self, vfd):
        self.vhd = vhd
        self.vhd.cursor_off()
        self.current_mode = -1
        self.modes = [mk_hostname, mk_time, mk_mail]
        self.n_modes = len(self.modes)
        self.gen = None
        self.mode_duration = 5
        self.next_mode()

    def next_mode(self):
        self.vhd.clear()
        self.vhd.cursor_home()
        self.current_mode = (self.current_mode + 1) % self.n_modes
        self.gen = self.modes[self.current_mode](self.vhd, self.mode_duration)

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
