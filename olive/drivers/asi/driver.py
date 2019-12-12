import logging

from serial.tools import list_ports

from olive.core import Driver

__all__ = ["ASI"]

logger = logging.getLogger(__name__)


class ASI(Driver):
    def __init__(self):
        super().__init__()

    ##

    async def initialize(self):
        pass

    async def shutdown(self):
        pass

    async def enumerate_devices(self) -> Union[Tiger]:
        pass
