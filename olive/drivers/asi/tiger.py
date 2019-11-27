from functools import lru_cache
import logging
from typing import Union

import trio
from serial import Serial
from serial.tools import list_ports

from olive.core import Driver, DeviceInfo
from olive.devices import MotionController
from olive.devices.errors import UnsupportedDeviceError
from olive.devices.motion import Axis

__all__ = ["MultiDigitalSynthesizer"]

logger = logging.getLogger(__name__)


class ASIAxis(Axis):
    def __init__(self, parent, axis, *args, **kwargs):
        super().__init__(parent.driver, *args, parent, **kwargs)

    ##

    async def enumerate_properties(self):
        pass

    ##

    async def home(self):
        pass

    async def get_position(self):
        pass

    async def set_absolute_position(self, pos):
        pass

    async def set_relative_position(self, pos):
        pass

    ##

    async def get_velocity(self):
        pass

    async def set_velocity(self, vel):
        pass

    ##

    async def get_acceleration(self):
        pass

    async def set_acceleration(self, acc):
        pass

    ##

    async def set_origin(self):
        pass

    async def get_limits(self):
        pass

    async def set_limits(self):
        pass

    ##

    async def calibrate(self):
        pass

    async def stop(self, emergency=False):
        pass

    async def wait(self):
        pass

    ##

    @property
    def busy(self):
        pass

    @property
    @lru_cache(maxsize=1)
    def info(self):
        pass


class Tiger(MotionController):
    def __init__(self, driver, port, *args, baudrate=115200, **kwargs):
        super().__init__(driver, *args, **kwargs)

        ser = Serial()
        ser.port = port
        ser.baudrate = baudrate
        self._handle = ser

    ##

    async def test_open(self):
        try:
            self.handle.open()
            logger.info(f".. {self.info}")
        except SyntaxError:
            raise UnsupportedDeviceError
        finally:
            self.handle.close()

    async def open(self):
        self.handle.open()

    async def close(self):
        self.handle.close()

    ##

    async def enumerate_properties(self):
        return tuple()

    ##

    async def enumerate_axes(self) -> Union[ASIAxis]:
        pass

    ##

    @property
    def busy(self):
        pass

    @property
    def handle(self):
        return self._handle

    @property
    def info(self):
        pass

    @property
    def is_opened(self):
        pass

    ##

    async def _send_cmd(self, *args, **kwargs):
        # 1) compact
        args = [str(arg) for arg in args]
        kwargs = [f"{str(k)}={str(v)}" for k, v in kwargs.items()]
        # 2) join
        cmd = " ".join(args + kwargs)
        # 3) response format
        cmd = f"{cmd}\r".encode()
        # 4) send
        await trio.to_thread.run_sync(self.handle.write, cmd)
        response = await self._check_error()

    async def _check_error(self):
        response = await trio.to_thread.run_sync(self.handle.read_until, b"\r\n")
        response = response.decode("ascii").strip()
        if response.startswith(":N"):
            self._determine_error(response)
        return response

    def _determine_error(self, response):
        errno = int(response[2:])
        msg = {
            1: "unknown command",
            2: "unrecognized axis parameter",
            3: "missing parameter",
            4: "parameter out of range",
            5: "operation failed",
            6: "undefined error",
            7: "invalid card address",
            21: "serial command halted by the halt command",
        }[errno]
        raise RuntimeError(msg)


class ASIControllers(Driver):
    def __init__(self):
        super().__init__()

    ##

    async def initialize(self):
        pass

    async def shutdown(self):
        pass

    async def enumerate_devices(self) -> Union[Tiger]:
        pass


async def _test():
    controller = Tiger(None, "COM5")
    try:
        await controller.open()
        await controller._send_cmd("E", X="?")
    finally:
        await controller.close()


if __name__ == "__main__":
    trio.run(_test)
