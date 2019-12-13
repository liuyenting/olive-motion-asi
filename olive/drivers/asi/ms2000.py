import logging
from typing import Union

from olive.core import DeviceInfo
from olive.devices.errors import UnsupportedDeviceError

from .base import ASIAxis, ASISerialCommandController

__all__ = ["LX4000", "MS2000"]

logger = logging.getLogger(__name__)


class MS2000(ASISerialCommandController):
    async def test_open(self):
        try:
            await self.open()

            # test controller string
            name = self.send_cmd("N")
            if not name.startswith("ASI-MS2000"):
                raise UnsupportedDeviceError
            logger.info(f".. {self.info}")
        finally:
            await self.close()

    async def _open(self):
        self.handle.open()

        # create info
        version = self.send_cmd("V")
        _, version = version.split(" ")
        self._info = DeviceInfo(vendor="ASI", model="MS2000", version=version)

    ##

    async def enumerate_properties(self):
        return await super().enumerate_properties()

    ##

    async def enumerate_axes(self) -> Union[ASIAxis]:
        fw_info = self.send_cmd("BU")
        axes = set(fw_info.split("_")[1])

        valid_axes = []
        for axis in axes:
            try:
                axis = ASIAxis(self, axis)
                await axis.test_open()
                valid_axes.append(axis)
            except UnsupportedDeviceError:
                pass
        return tuple(valid_axes)


class LX4000(MS2000):
    async def test_open(self):
        try:
            await self.open()

            # test controller string
            name = self.send_cmd("N")
            print(name)

            if not name.startswith("ASI-MS2000"):
                raise UnsupportedDeviceError
            logger.info(f".. {self.info}")
        finally:
            await self.close()

    async def _open(self):
        self.handle.open()

        model = self.send_cmd("BU")

        # create info
        version = self.send_cmd("V")
        _, version = version.split(" ")
        self._info = DeviceInfo(vendor="ASI", model="LX4000", version=version)

    ##

    def send_cmd(self, *args, **kwargs):
        kwargs.update({"address": "2H", "term": "\r\n\3"})
        # TODO switch address
        return super().send_cmd(*args, **kwargs)

