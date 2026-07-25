
__all__ = [
    "getbloomy",
]


def getbloomy():
    from ..bloomy import Bloomy
    try:
        return Bloomy._inst
    except AttributeError:
        raise RuntimeError("Not instanced") from None
