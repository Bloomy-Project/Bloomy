from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING

from discord.ext.commands import Cog, Bot

from bloomy.util import getbloomy

if TYPE_CHECKING:
    from .bloomy import Bloomy
    from .database import DatabaseManager

log = getLogger(__name__)
__all__ = [
    "BloomyCog",
]


class BloomyCog(Cog):
    @property
    def bloomy(self) -> "Bloomy":
        """
        Bloomy 内部インスタンスを返します
        これらのアクセスは将来的に更新などで互換性がなくなる場合がある点に注意が必要です
        """
        return getbloomy()

    @property
    def database(self) -> "DatabaseManager":
        """
        Bloomy データベースを返します
        これは Bloomy や他のプラグインと共有します。
        """
        return self.bloomy.db

    @property
    def data_dir(self) -> Path:
        """
        プラグインのデータフォルダのパスを返します
        プラグインのモジュール名が testplugin なら ./data/testplugin というパスになります
        """
        return self.bloomy.plugin_manager.get_data_dir(self)


class PluginManager(object):
    def __init__(
        self,
        plugins_dir: str = "plugins/",
        extensions_dir: str = "extensions/",
        data_dir: str = "data/",
    ):
        self.plugins_dir = Path(plugins_dir)
        self.data_dir = Path(data_dir)
    
    async def load_plugins(self, bot: Bot):
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
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

    def get_data_dir(self, cog: Cog):
        if not cog.__module__.startswith("plugins."):
            raise ValueError(f"Invalid module name, {cog!r} is not a plugin.")
        mod_name = cog.__module__.split(".")[1]
        return self.data_dir / mod_name
