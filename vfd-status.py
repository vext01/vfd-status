#/usr/bin/env python2.7
import serial
import sys
import time
import os
import mailbox

from socket import gethostname

MOD = sys.modules[__name__]
SER = serial.Serial('/dev/ttyU0', 38400, timeout=1)
USER =os.environ["USER"]
MBOX = os.sep + os.path.join("var", "mail", USER)

CMDS = {
    "CLR": (0x0e, 900),     # clear
    "FF": (0x0c, 200),      # form feed
    "CR": (0xd, 200),       # carriage return
    "LF": (0xa, 900),       # line feed
    "DC6": (0x16, 200),     # cursor off
}

class Cmd:
    MICROSEC = 10 ** -6

    def __init__(self, ser, val, sleep):
        self.val = val
        self.ser = ser
        self.sleep = sleep

    def __call__(self):
        self.ser.write([self.val])
        time.sleep(self.sleep * self.MICROSEC)

for name, (val, sleep) in CMDS.items():
    setattr(MOD, name, Cmd(SER, val, sleep))

def write(msg):
    SER.write(bytes(msg, encoding="ascii"))

def CLRFF():
    CLR()
    FF()

def mk_mail(ticks):
    box = mailbox.mbox(MBOX)
    write("Mail: %s" % USER)
    LF()
    CR()
    write("%d messages" % len(box))
    box.close()
    for i in range(ticks):
        _ = yield

def mk_hostname(ticks):
    write(gethostname())
    LF()
    for i in range(ticks):
        _ = yield

def mk_time(ticks):
    tm_s = time.strftime("%A %b %d, %Y")
    write(tm_s)
    LF()
    for i in range(ticks):
        CR()
        tm_s = time.strftime("%H:%M:%S")
        write(tm_s)
        _ = yield

class Status:
    def __init__(self):
        self.current_mode = -1
        self.modes = [mk_hostname, mk_time, mk_mail]
        self.n_modes = len(self.modes)
        self.gen = None
        self.mode_duration = 5
        self.next_mode()

    def next_mode(self):
        CLRFF()
        self.current_mode = (self.current_mode + 1) % self.n_modes
        self.gen = self.modes[self.current_mode](self.mode_duration)

    def run(self):
        while True:
            try:
                self.gen.send(None)
            except StopIteration as e:
                self.next_mode()
                continue
            time.sleep(1)


if __name__ == "__main__":
    status = Status()
    status.run()
    SER.close()
