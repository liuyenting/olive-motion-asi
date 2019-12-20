import logging
from pprint import pprint

import coloredlogs
import trio

from olive.devices.errors import UnsupportedDeviceError
from olive.drivers.asi import LX4000, MS2000, Tiger

coloredlogs.install(
    level="DEBUG", fmt="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"
)

logger = logging.getLogger(__name__)


async def action(axis):
    axis_id = axis.axis
    try:
        logger.info(f"{axis_id}, 0, open")
        await axis.open()

        vel = axis.get_velocity()
        logger.info(f"{axis_id}, velocity: {vel}")
        limits = axis.get_limits()
        logger.info(f"{axis_id}, limits: {limits}")

        await axis.calibrate()

        limits = axis.get_limits()
        logger.info(f"{axis_id}, limits: {limits}")
        pos = axis.get_position()
        logger.info(f"{axis_id}, pos: {pos}")

        logger.info(f"{axis_id}, 1, reset")
        await axis.move_absolute(0)

        #logger.info(f"{axis_id}, 2, shift")
        #await axis.move_absolute(1000)

        # logger.info(f"{axis_id}, 3, set home")
        # await axis.set_origin()

        # logger.info(f"{axis_id}, 4, rel move to prev origin")
        # await axis.set_relative_position(-10)

        # logger.info(f"{axis_id}, 5, return home (should move)")
        # await axis.home()
    finally:
        logger.info(f"{axis_id}, 6, close")
        await axis.close()


async def main():
    controller = MS2000(None, "COM5", baudrate=9600)
    #controller = LX4000(None, "COM10", baudrate=115200)

    await controller.test_open()
    try:
        await controller.open()
        axes = await controller.enumerate_axes()

        async with trio.open_nursery() as nursery:
            for axis in axes:
                nursery.start_soon(action, axis)
    finally:
        await controller.close()


if __name__ == "__main__":
    trio.run(main)
