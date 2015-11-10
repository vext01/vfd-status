#/usr/bin/env python3.4
import serial
import sys
import time
import os
import mailbox
import subprocess
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


class VFD:
    """Raw access to the VFD via serial interface."""

    def __init__(self, port="/dev/ttyU0", baud=38400):
        self.ser = serial.Serial(port, baud, timeout=1)
        # XXX hard-coded
        self.n_rows = 2
        self.n_cols = 20
        self.n_chars = self.n_rows * self.n_cols
        self.japanese_font()

    def write(self, msg):
        for ch in msg:
            self.ser.write(bytes(str(ch), encoding="ascii"))
            Wait.wait(200)

    def raw_write(self, ch, wait=200):
        self.ser.write([ch])
        Wait.wait(wait)

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

    @Wait(200)
    def japanese_font(self):
        """AKA CT1"""
        self.ser.write([0x19])


class BasePlugiun(metaclass=ABCMeta):
    def __init__(self, vfd, duration):
        self.vfd = vfd
        self.duration = duration
        self.generator = self.make_generator()

    @abstractmethod
    def make_generator(self):
        pass

class MpdPlugin(BasePlugiun):
    PLAY_SYMBOL = 0x99
    PAUSE_SYMBOL = 0x9c
    STOP_SYMBOL = 0xf8

    def _get_playstate(self):
        p = subprocess.Popen("mpc", shell=True, stdout=subprocess.PIPE)
        stdout, stderr = p.communicate()
        stdout_s = stdout.decode("utf-8").strip()
        lines = stdout_s.split("\n")

        if len(lines) == 1:
            return self.STOP_SYMBOL
        else:
            assert len(lines) == 3
            s_idx = lines[1].index("[")
            e_idx = lines[1].index("]")
            mode = lines[1][s_idx + 1:e_idx]
            if mode == "playing":
                mode_ch = self.PLAY_SYMBOL
            elif mode == "paused":
                mode_ch = self.PAUSE_SYMBOL
            return mode_ch

    def _get_field(self, field):
        p = subprocess.Popen("mpc -f %%%s%%" % field,
                              shell=True, stdout=subprocess.PIPE)
        stdout, stderr = p.communicate()
        stdout_s = stdout.decode("utf-8").rstrip()
        lines = stdout_s.split("\n")

        if len(lines) == 1:
            # hrm, MPD is stopped
            v = ""
        else:
            assert(len(lines) == 3)
            v = lines[0].strip()

        print("field %s=%s" % (field, v))
        return v

    def _get_song_info(self):
        # This isn't an exact science
        artist = self._get_field("artist")
        title = self._get_field("title")
        if artist == "":
            # Streams tend to put artist and title here
            return title
        else:
            return artist + " - " + title

    def make_generator(self):
        self.vfd.clear()
        self.vfd.cursor_home()

        mode_ch = self._get_playstate()
        if mode_ch != self.STOP_SYMBOL:
            song = self._get_song_info()
        else:
            song = "MPD idle"

        remain_space = self.vfd.n_chars - 2
        trim_song = song[:remain_space]
        self.vfd.raw_write(mode_ch)
        self.vfd.write(" %s" % trim_song)

        for i in range(self.duration):
            _ = yield

class TimePlugin(BasePlugiun):
    def make_generator(self):
        tm_s = time.strftime("%a %b %d, %Y")
        self.vfd.write(tm_s)
        self.vfd.cursor_home()  # assume date doesn't change for duration of this screen
        self.vfd.line_feed()
        for i in range(self.duration):
            self.vfd.carriage_return()
            tm_s = time.strftime("%H:%M:%S")
            self.vfd.write(tm_s)
            _ = yield


class MailPlugin(BasePlugiun):
    def make_generator(self):
        box = mailbox.mbox(MBOX)
        count = len(box)
        box.close()

        self.vfd.write("Mail: %s" % USER)
        self.vfd.line_feed()
        self.vfd.carriage_return()
        self.vfd.write("%d messages" % count)
        for i in range(self.duration):
            _ = yield


class HostNamePlugin(BasePlugiun):
    def make_generator(self):
        self.vfd.write(gethostname())
        self.vfd.line_feed()
        for i in range(self.duration):
            _ = yield


class Status:
    def __init__(self, vfd):
        self.vfd = vfd
        self.vfd.cursor_off()
        self.current_mode = -1
        self.modes = [HostNamePlugin, TimePlugin, MailPlugin, MpdPlugin]
        self.n_modes = len(self.modes)
        self.gen = None
        self.mode_duration = 5
        self.next_mode()

    def next_mode(self):
        self.vfd.clear()
        self.vfd.cursor_home()
        self.current_mode = (self.current_mode + 1) % self.n_modes
        plugin = self.modes[self.current_mode](self.vfd, self.mode_duration)
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
    vfd = VFD()
    status = Status(vfd)
    status.run()
