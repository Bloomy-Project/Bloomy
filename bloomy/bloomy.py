import asyncio
import signal
from logging import getLogger
from pathlib import Path

import discord
from discord.ext import commands

from bloomy._logger import BloomyStreamHandler, BloomyFileHandler
from bloomy.config import DictConfig
from bloomy.database import DatabaseManager
from bloomy.plugin import PluginManager

log = getLogger(__name__)
__all__ = [
    "BloomyConfig",
    "Bloomy",
]


class BloomyConfig(DictConfig):
    token: str
    owner_ids: list[int]
    log_level: str = "debug"
    file_log_level: str = "info"
    command_prefix: str | None = None
    database_url: str = "sqlite+aiosqlite:///data/database.db"

    @property
    def owner_id(self) -> int | None:
        if self.owner_ids:
            return self.owner_ids[0]
        return None


class Bloomy(object):
    _inst: "Bloomy"
    bot: commands.Bot  # delay init

    def __init__(
        self, *,
        loop: asyncio.AbstractEventLoop,
        logs_dir: str = "logs/",
        plugins_dir: str = "plugins/",
        config_file: str = "config/config.yml",
        data_dir: str = "data/",
    ):
        Bloomy._inst = self  # singleton
        self.logs_dir = Path(logs_dir)
        self.config_file = Path(config_file)
        self.data_dir = Path(data_dir)
        self.loop = loop
        self.plugin_manager = PluginManager(plugins_dir, data_dir=data_dir)
        self.config = BloomyConfig.create_yaml(self.config_file)
        self.owners = {}  # type: dict[int, discord.User | None]
        #
        self.log_stream_handler = None  # type: BloomyStreamHandler | None
        self.log_file_handler = None  # type: BloomyFileHandler | None

        # 追加：設定ファイル読み込み前に、パスプレースホルダーでDatabaseManagerを初期化
        # パスは init() 内で config.load_file() が呼ばれた後に正確に解決されます
        self.db = DatabaseManager()

    def setup_loggers(self, *names: str, file_out=True):
        if self.log_stream_handler is None:
            self.log_stream_handler = BloomyStreamHandler()

        if self.log_file_handler is None and file_out:
            self.log_file_handler = BloomyFileHandler(self.logs_dir / "latest.log")

        self.update_logger_level()

        for name in names:
            _log = getLogger(name)
            _log.setLevel(-1)
            _log.addHandler(self.log_stream_handler)
            if file_out:
                _log.addHandler(self.log_file_handler)

    def update_logger_level(self):
        if handler := self.log_stream_handler:
            handler.setLevel(self.config.log_level.upper())
        if handler := self.log_file_handler:
            handler.setLevel(self.config.file_log_level.upper())

    #

    async def init(self):
        log.debug("on initializing")
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.config.load_file()
        self.update_logger_level()

        await self.db.connect(self.config.database_url)

        self.bot = commands.Bot(
            command_prefix=[self.config.command_prefix] if self.config.command_prefix else ["!"],
            owner_ids=self.config.owner_ids,
            intents=discord.Intents.all(),
        )
        self._event_handling(self.bot)
        log.debug("Loading plugins")
        await self.plugin_manager.load_plugins(self.bot)

        log.info("Initialized Bloomy!")

    async def on_connect(self):
        await self.bot.wait_until_ready()
        log.info(f"Connected to Discord: {self.bot.user}")

        owners = await self.update_owners_cache()
        log.info("Owners: %s", ", ".join([str(v or k) for k, v in owners.items()]))

        guilds = self.bot.guilds
        log.info("")
        if guilds:
            for guild in guilds:
                log.info(f"- {guild.id}/{guild.name} - {guild.owner or guild.owner_id}")
        else:
            log.info("  No joined guilds")
        log.info("")

        sync_task = self.loop.create_task(self.bot.tree.sync())
        try:
            await asyncio.wait_for(asyncio.shield(sync_task), timeout=3)
        except asyncio.TimeoutError:
            log.warning("Syncing application commands... (waiting)")
        await sync_task
        log.debug("Synced application commands")

    async def run(self):
        try:
            bot = self.bot
        except AttributeError:
            raise RuntimeError("Bloomy is not initialized") from None
        log.debug("Connecting to Discord...")

        # noinspection PyTypeChecker
        signal.signal(signal.SIGTERM, lambda *_: self.loop.create_task(self.shutdown()))
        signal.signal(signal.SIGINT, lambda _, __: self.loop.create_task(self.shutdown()))
        if hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, lambda _, __: self.loop.create_task(self.shutdown()))
        asyncio.create_task(self.on_connect())
        await bot.start(token=self.config.token)

    async def shutdown(self):
        if bot := self.bot:
            await bot.close()

    async def cleanup(self):
        log.info("Cleanup Bloomy")

        # 追加：データベース接続を安全に閉じる
        try:
            await self.db.close()
        except Exception as e:
            log.exception("Exception in db.close", exc_info=e)

        if bot := self.bot:
            log.debug("Unloading extensions")
            for cog_name in list(bot.cogs):
                try:
                    await bot.remove_cog(cog_name)
                except Exception as e:
                    log.exception("Exception in remove cog: %s", cog_name, exc_info=e)

            for extension_name in list(bot.extensions):
                try:
                    await bot.unload_extension(extension_name)
                except Exception as e:
                    log.exception("Exception in unload extension: %s", extension_name, exc_info=e)

            log.debug("Closing discord bot")
            try:
                await bot.close()
            except Exception as e:
                log.warning(f"Failed to close bot: {e}")

            bot.clear()

        del self.bot

    def _event_handling(self, bot: commands.Bot):
        pass

    async def update_owners_cache(self):
        log.debug("Updating owners cache")
        self.owners.clear()
        for owner_id in self.config.owner_ids:
            if not (owner := self.bot.get_user(owner_id)):
                try:
                    owner = await self.bot.fetch_user(owner_id)
                except discord.HTTPException:
                    owner = None
            self.owners[owner_id] = owner
        return self.owners
