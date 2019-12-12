import logging

import trio
from serial import Serial

from olive.core import DeviceInfo
from olive.devices import MotionController
from olive.devices.errors import (
    UnsupportedDeviceError,
    OutOfRangeError,
    UnknownCommandError,
)
from olive.devices.motion import Axis

from . import errors

__all__ = ["ASIAxis", "ASISerialCommandController"]

logger = logging.getLogger(__name__)


class ASIAxis(Axis):
    def __init__(self, parent, axis, *args, **kwargs):
        super().__init__(parent.driver, *args, parent, **kwargs)
        self._axis = axis

        self._info = None

    ##

    async def test_open(self):
        try:
            await self.open()
            if not await self.get_property("motor_control"):
                raise UnsupportedDeviceError("axis not connected")
            logger.info(f".. {self.info}")
        finally:
            await self.close()

    async def _open(self):
        self._info = DeviceInfo(vendor="ASI", model=self.axis)

        response = self.parent.send_cmd("UM", f"{self.axis}?")
        logger.debug(f"{self.axis} unit mul: {response}")

    async def _close(self):
        await self.stop()
        self._info = None

    ##

    async def enumerate_properties(self):
        return ("motor_control",)

    async def _get_motor_control(self):
        status = self.parent.send_cmd("MC", f"{self.axis}?")
        return status == "1"

    ##

    async def home(self, blocking=True):
        self.parent.send_cmd("!", self.axis)
        await trio.sleep(0)
        if blocking:
            await self.wait()

    async def get_position(self):
        response = self.parent.send_cmd("W", f"{self.axis}")
        print(f".. {response}")
        pos = float(response) / (1000 * 10)
        return pos

    async def set_absolute_position(self, pos, blocking=True):
        # 0.1 micron per unit step
        pos *= 1000 * 10
        self.parent.send_cmd("M", **{self.axis: pos})
        await trio.sleep(0)
        if blocking:
            await self.wait()

    async def set_relative_position(self, pos, blocking=True):
        # 0.1 micron per unit step
        pos *= 1000 * 10
        self.parent.send_cmd("R", **{self.axis: pos})
        await trio.sleep(0)
        if blocking:
            await self.wait()

    ##

    async def get_velocity(self):
        response = self.parent.send_cmd("S", f"{self.axis}?")
        return float(response.split("=")[1])

    async def set_velocity(self, vel):
        self.parent.send_cmd("S", self.axis, vel)

    ##

    async def get_acceleration(self):
        response = self.parent.send_cmd("AC", f"{self.axis}?")
        return float(response.split("=")[1])

    async def set_acceleration(self, acc):
        self.parent.send_cmd("AC", self.axis, acc)

    ##

    async def set_origin(self):
        self.parent.send_cmd("HM", f"{self.axis}+")
        await trio.sleep(0)

    async def get_limits(self):
        response = self.parent.send_cmd("SL", f"{self.axis}?")
        lo = float(response.split("=")[1])
        response = self.parent.send_cmd("SU", f"{self.axis}?")
        hi = float(response.split("=")[1])
        await trio.sleep(0)
        return lo, hi

    async def set_limits(self, lim):
        lo, hi = tuple(lim)
        self.parent.send_cmd("SL", self.axis, lo)
        self.parent.send_cmd("AU", self.axis, hi)

    ##

    async def calibrate(self, unit_step=1):
        # run until negative limit
        while not self._is_limit_switch_triggered("-"):
            await self.set_relative_position(-unit_step)
        lo = await self.get_position()

        # run until positive limit
        while not self._is_limit_switch_triggered("+"):
            await self.set_relative_position(unit_step)
        hi = await self.get_position()

        logger.debug(f"current range [{lo}, {hi}]")

        # move to center
        center = (hi + lo) / 2.0
        await self.set_absolute_position(center)

        # reset
        await self.set_origin()

    def _is_limit_switch_triggered(self, direction):
        assert direction in "+-", "unknown direction flag"

        flag = "U" if direction == "+" else "L"
        return self.parent.send_cmd("RS", f"{self.axis}-") == flag

    async def stop(self, emergency=False):
        self.parent.send_cmd("\\")

    async def wait(self):
        while self.is_busy:
            pos = await self.get_position()
            logger.debug(f"{self.axis}: {pos}")
            await trio.sleep(1)

    ##

    @property
    def axis(self):
        return self._axis

    @property
    def info(self):
        return self._info

    @property
    def is_busy(self):
        return self.parent.is_busy

    @property
    def is_opened(self):
        return self.info is not None


class ASISerialCommandController(MotionController):
    def __init__(self, driver, port, *args, baudrate=115200, **kwargs):
        super().__init__(driver, *args, **kwargs)

        ser = Serial()
        ser.port = port
        ser.baudrate = baudrate
        self._handle, self._lock = ser, trio.StrictFIFOLock()

        self._info = None

    ##

    async def _open(self):
        self.handle.open()

        # create info
        model = self.send_cmd("BU")
        version = self.send_cmd("V")
        self._info = DeviceInfo(vendor="ASI", model=model, version=version)

    async def _close(self):
        self._info = None
        self.handle.close()

    ##

    async def enumerate_properties(self):
        return tuple()

    ##

    @property
    def handle(self):
        return self._handle

    @property
    def info(self):
        return self._info

    @property
    def is_busy(self):
        """
        STATUS is handles quickly in the ASI command parser. The official way to rapid poll.
        """
        response = self.send_cmd("/")
        return response == "B"

    @property
    def is_opened(self):
        return self.handle.is_open

    @property
    def lock(self):
        return self._lock

    ##

    def send_cmd(self, *args, **kwargs):
        # 1) compact
        args = [str(arg) for arg in args]
        kwargs = [f"{str(k)}={v}" for k, v in kwargs.items()]

        # 2) join
        cmd = " ".join(args + kwargs)

        # 3) response format
        cmd = f"{cmd}\r".encode()
        logger.debug(f"SEND {cmd}")

        # 4) send
        self.handle.write(cmd)

        # 5) ack
        response = self.handle.read_until(b"\r\n")
        # ... ensure multi-line response is received properly
        response = response.replace(b"\r", b"\n")
        response = response.decode("ascii").rstrip()
        logger.debug(f"RECV {response}")
        response = self._check_error(response)

        return response

    def _check_error(self, response):
        if response.startswith(":N"):
            errno = int(response[2:])
            ASISerialCommandController.interpret_error(errno)
        elif response.startswith(":A"):
            return response[2:].strip()
        return response

    @staticmethod
    def interpret_error(errno):
        klass, msg = {
            1: (UnknownCommandError, ""),
            2: (errors.UnrecognizedAxisError, ""),
            3: (errors.MissingParameterError, ""),
            4: (OutOfRangeError, ""),
            5: (RuntimeError, "operation failed"),
            6: (RuntimeError, "undefined error"),
            7: (errors.InvalidCardAddressError, ""),
            21: (errors.HaltError, ""),
        }.get(errno, (errors.UnknownError, f"errno={errno}"))
        raise klass(msg)
