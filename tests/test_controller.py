import logging
from pprint import pprint

import coloredlogs
import trio

from olive.devices.errors import UnsupportedDeviceError
from olive.drivers.asi import Tiger

coloredlogs.install(
    level="DEBUG", fmt="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"
)

logger = logging.getLogger(__name__)


async def action(axis):
    print(".. action 0")
    await axis.set_absolute_position(0)
    print(".. action 1")
    await axis.set_absolute_position(10)
    print(".. action 2")
    await axis.set_origin()
    print(".. action 3")
    await axis.set_relative_position(-10)
    print(".. action 4")
    await axis.home()


async def main():
    controller = Tiger(None, "COM5")

    await controller.test_open()
    try:
        await controller.open()
        axes = await controller.enumerate_axes()

        print("OPEN")
        for axis in axes:
            await axis.open()

        print("MOVE")
        async with trio.open_nursery() as nursery:
            for axis in axes:
                nursery.start_soon(action, axis)

        print("CLOSE")
        for axis in axes:
            await axis.close()
    finally:
        await controller.close()


if __name__ == "__main__":
    trio.run(main)
