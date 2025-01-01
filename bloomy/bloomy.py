import asyncio
from logging import getLogger
from pathlib import Path

import discord
from discord.ext import commands

from bloomy._logger import BloomyStreamHandler, BloomyFileHandler
from bloomy.config import DictConfig

log = getLogger(__name__)
__all__ = [
    "BloomyConfig",
    "Bloomy",
]


class BloomyConfig(DictConfig):
    token: str
    owner_id: int | None
    log_level: str = "debug"
    file_log_level: str = "info"
    command_prefix: str | None = None


class Bloomy(object):
    _inst: "Bloomy"
    bot: commands.Bot  # delay init

    def __init__(
        self, *,
        loop: asyncio.AbstractEventLoop,
        logs_dir: str = "logs/",
        plugins_dir: str = "plugins/",
        config_file: str = "config/config.yml",
    ):
        Bloomy._inst = self  # singleton
        self.logs_dir = Path(logs_dir)
        self.plugins_dir = Path(plugins_dir)
        self.config_file = Path(config_file)
        self.loop = loop
        self.config = BloomyConfig.create_yaml(self.config_file)
        self.owners = {}  # type: dict[int, discord.User | None]
        #
        self.log_stream_handler = None  # type: BloomyStreamHandler | None
        self.log_file_handler = None  # type: BloomyFileHandler | None

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

    async def start(self):
        log.debug("on initializing")
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

        self.config.load_file()
        self.update_logger_level()

        self.bot = commands.Bot(
            command_prefix=[self.config.command_prefix] if self.config.command_prefix else ["!"],
            owner_ids=[self.config.owner_id] if self.config.owner_id else [],
            intents=discord.Intents.all(),
        )
        self._event_handling(self.bot)
        log.debug("Loading plugins")
        await self.load_plugins()

        async def _on_connect():
            await self.bot.wait_until_ready()
            log.info(f"Connected to Discord: {self.bot.user}")

            try:
                owners = await self.update_owners()
            except Exception as e:
                log.warning(f"Exception in update_owners: {e}", exc_info=e)
                owners = {self.config.owner_id: None}
            log.info("Owners: %s", ", ".join([str(v or k) for k, v in owners.items()]))

            guilds = self.bot.guilds
            log.info("")
            if guilds:
                for guild in guilds:
                    log.info(f"- {guild.id}/{guild.name} - {guild.owner or guild.owner_id}")
            else:
                log.info("  No joined guilds")
            log.info("")

            await self.bot.tree.sync()
            log.info("Tree Sync completed")

        asyncio.create_task(_on_connect())

        log.debug("Connecting to Discord...")
        await self.bot.start(token=self.config.token)

    async def load_plugins(self):
        names = []
        for child in self.plugins_dir.iterdir():  # type: Path
            if child.name.startswith(("_", ".", )):
                continue

            if child.is_file() and child.suffix == ".py":
                name = child.name.split(".")[0]
            elif child.is_dir() and child.suffix != ".bak":
                name = child.name
            else:
                continue

            try:
                await self.bot.load_extension(f"plugins.{name}")
            except Exception as e:
                log.warning("Error in load extension: %s", name, exc_info=e)
                continue

            names.append(name)

        log.info(f"Loaded %d plugins: %s", len(names), ", ".join(names))

    def _event_handling(self, bot: commands.Bot):
        pass

    async def update_owners(self):
        log.debug("updating owner users")
        self.owners.clear()
        owners = {}
        if owner_id := self.config.owner_id:
            if not (owner := self.bot.get_user(owner_id)):
                try:
                    owner = await self.bot.fetch_user(owner_id)
                except discord.HTTPException:
                    pass  # ignore
            if owner:
                self.owners[owner_id] = owner
            owners[owner_id] = owner
        return owners
