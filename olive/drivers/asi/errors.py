from olive.devices.errors import MotionError, UnknownCommandError


class ASIError(MotionError):
    """Base class for ASI device error."""


class UnrecognizedAxisError(UnknownCommandError):
    pass


class MissingParameterError(UnknownCommandError):
    pass


class InvalidCardAddressError(ASIError):
    pass


class HaltError(InterruptedError):
    pass


class UnknownError(ASIError):
    pass
