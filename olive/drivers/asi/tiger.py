import logging
from typing import Union

from olive.devices.errors import UnsupportedClassError

from .base import ASIAxis, ASISerialCommandController

__all__ = ["Tiger"]

logger = logging.getLogger(__name__)


class Tiger(ASISerialCommandController):
    async def test_open(self):
        try:
            await self.open()

            # test controller string
            if self.info.model != "TIGER_COMM":
                raise UnsupportedClassError
            logger.info(f".. {self.info}")
        finally:
            await self.close()

    ##

    async def enumerate_properties(self):
        return ("cards",)

    async def _get_cards(self):
        response = self.send_cmd("N")
        cards = []
        for line in response.split("\n"):
            # strip card address
            address, line = line.split(":", maxsplit=1)
            address = int(address[3:])

            # split options
            line = line.strip()
            function, version, character, *options = line.split(" ")

            cards.append(
                {
                    "address": address,
                    "character": character,
                    "version": version,
                    "function": function,
                }
            )
        return tuple(cards)

    ##

    async def enumerate_axes(self) -> Union[ASIAxis]:
        cards = await self.get_property("cards")

        print(">>>")
        import json  # noqa

        print(json.dumps(cards, indent=4))
        print("<<<")

        axes = []
        for card in cards:
            if card["character"] not in ("SCAN_XY_LED", "STD_ZF"):
                continue
            # parse axes identifier
            motors = card["function"].split(",")
            for motor in motors:
                axes.append(motor.split(":", maxsplit=1)[0])

        valid_axes = []
        logger.debug("TESTING VALID AXES")
        for axis in axes:
            try:
                axis = ASIAxis(self, axis)
                await axis.test_open()
                valid_axes.append(axis)
            except UnsupportedClassError:
                pass
        return tuple(valid_axes)
