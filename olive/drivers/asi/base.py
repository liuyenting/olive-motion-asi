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
from olive.devices.motion import Axis, LimitStatus

from . import errors

__all__ = ["ASIAxis", "ASISerialCommandController"]

logger = logging.getLogger(__name__)


class ASIAxis(Axis):
    def __init__(self, parent, axis, *args, **kwargs):
        super().__init__(parent.driver, *args, parent, **kwargs)
        self._axis = axis

        self._info = None
        self._multiplier = 1

    ##

    async def test_open(self):
        try:
            await self.open()
            flag = self.parent.send_cmd("RS", f"{self.axis}-")
            if flag == "D":
                raise UnsupportedDeviceError("axis not connected")
            logger.info(f".. {self.info}")
        finally:
            await self.close()

    async def _open(self):
        self._info = DeviceInfo(vendor="ASI", model=self.axis)
        self._multiplier = await self.get_property("unit_multiplier")

    async def _close(self):
        self.stop()
        self._info = None

    ##

    async def enumerate_properties(self):
        return ("motor_control", "unit_multiplier")

    async def _get_motor_control(self):
        status = self.parent.send_cmd("MC", f"{self.axis}?")
        return status == "1"

    async def _get_unit_multiplier(self):
        unit_mul = self.parent.send_cmd("UM", f"{self.axis}?")

        # ":X=100000.00000 A"
        unit_mul = unit_mul.split(" ")[0][1:]
        unit_mul = unit_mul.split("=")[1]

        return float(unit_mul)

    ##

    async def go_home(self, blocking=True):
        self.parent.send_cmd("!", self.axis)
        await trio.sleep(0)
        if blocking:
            await self.wait()

    def get_position(self):
        response = self.parent.send_cmd("W", f"{self.axis}")
        pos = float(response) / self._multiplier
        return pos

    async def move_absolute(self, pos, blocking=True):
        # 0.1 micron per unit step
        pos *= self._multiplier
        # remove decimal
        pos = int(pos)
        self.parent.send_cmd("M", **{self.axis: pos})
        await trio.sleep(0)
        if blocking:
            await self.wait()

    async def move_relative(self, pos, blocking=True):
        # 0.1 micron per unit step
        pos *= self._multiplier
        # remove decimal
        pos = int(pos)
        self.parent.send_cmd("R", **{self.axis: pos})
        await trio.sleep(0)
        if blocking:
            await self.wait()

    def move_continuous(self, vel):
        self.parent.send_cmd("VE", f"{self.axis}={vel}")

    ##

    def get_velocity(self):
        response = self.parent.send_cmd("S", f"{self.axis}?")
        return float(response.split("=")[1])

    def set_velocity(self, vel):
        self.parent.send_cmd("S", self.axis, vel)

    ##

    def get_acceleration(self):
        response = self.parent.send_cmd("AC", f"{self.axis}?")
        return float(response.split("=")[1])

    def set_acceleration(self, acc):
        self.parent.send_cmd("AC", self.axis, acc)

    ##

    def set_origin(self):
        self.parent.send_cmd("H", f"{self.axis}")

    def get_limits(self):
        response = self.parent.send_cmd("SL", f"{self.axis}?")
        lo = float(response.split("=")[1])
        response = self.parent.send_cmd("SU", f"{self.axis}?")
        hi = float(response.split("=")[1])
        return lo, hi

    def get_limit_status(self):
        flag = self.parent.send_cmd("RS", f"{self.axis}-")
        return {"U": LimitStatus.UpperLimit, "L": LimitStatus.LowerLimit}.get(
            flag, LimitStatus.WithinRange
        )

    def set_limits(self, lim):
        lo, hi = tuple(lim)
        self.parent.send_cmd("SL", **{self.axis: lo})
        self.parent.send_cmd("SU", **{self.axis: hi})

    ##

    async def calibrate(self, vel=5):
        """
             -------|--
        1)          ==| N
        2)   |========= P
        3)   =======|
        """
        logger.debug(f"axis {self.axis} calibration started...")

        # reset limit to an impossible value (1 meter)
        self.set_limits((-1000, 1000))

        # remember current position
        ref = self.get_position()

        # run until upper limit
        self.move_continuous(vel)
        while self.get_limit_status() != LimitStatus.UpperLimit:
            await trio.sleep(0)
        hi = self.get_position()
        # run until lower limit
        self.move_continuous(-vel)
        while self.get_limit_status() != LimitStatus.LowerLimit:
            await trio.sleep(0)
        lo = self.get_position()
        logger.debug(f".. current {self.axis} limits [{lo}, {hi}]")

        # move to center
        full = hi - lo
        half = full / 2.0
        await self.move_relative(half)
        # reset
        self.set_origin()
        # update limits
        self.set_limits((-half, half))

        # move to original position
        await self.move_relative((ref - lo) - half)

    def stop(self, emergency=False):
        self.parent.send_cmd("\\")

    async def wait(self):
        while self.is_busy:
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

    def send_cmd(self, *args, address="", term=b"\r\n", **kwargs):
        # 1) compact
        args = [str(arg) for arg in args]
        kwargs = [f"{str(k)}={v}" for k, v in kwargs.items()]

        # 2) join
        cmd = " ".join(args + kwargs)

        # 3) response format
        cmd = f"{address}{cmd}\r".encode()
        # logger.debug(f"SEND {cmd}")

        # 4) send
        self.handle.write(cmd)

        # 5) ack
        response = self.handle.read_until(term)
        response = response[: -len(term)]
        # ... ensure multi-line response is received properly
        response = response.replace(b"\r", b"\n")
        response = response.decode("ascii").rstrip()
        # logger.debug(f"RECV {response}")
        response = self._check_error(response)

        return response

    def _check_error(self, response):
        if response.startswith(":N"):
            errno = int(response[3:])  # neglect the sign
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
