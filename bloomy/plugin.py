import zipfile
from pathlib import Path
from logging import getLogger

from discord.ext.commands import Cog, Bot

from bloomy.util import getbloomy

log = getLogger(__name__)
__all__ = [
    "BloomyCog",
]


class BloomyCog(Cog):
    @property
    def bloomy(self):
        return getbloomy()

class PluginManager():
    def __init__(
            self,
            plugins_dir: str = "plugins/",
            extensions_dir: str = "extensions/"
    ):

        self.plugins_dir = Path(plugins_dir)
    
    async def load_plugins(self, bot: Bot):
        names = []
        for child in self.plugins_dir.iterdir():  # type: Path
            if child.name.startswith(("_", ".", )):
                continue

            if child.is_file() and child.suffix == ".py":
                name = child.stem
            elif child.is_dir() and child.suffix != ".bak":
                name = child.name
            else:
                continue

            try:
                await bot.load_extension(f"plugins.{name}")
            except Exception as e:
                log.warning("Error in load extension: %s", name, exc_info=e)
                continue

            names.append(name)

        log.info(f"Loaded %d plugins: %s", len(names), ", ".join(names))