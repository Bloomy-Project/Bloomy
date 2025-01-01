from discord.ext.commands import Cog

from bloomy.util import getbloomy

__all__ = [
    "BloomyCog",
]


class BloomyCog(Cog):
    @property
    def bloomy(self):
        return getbloomy()
