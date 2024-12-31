import asyncio
from logging import getLogger
from pathlib import Path

import discord
from discord.ext import commands

log = getLogger(__name__)


class Bloomy(object):
    def __init__(
        self, *,
        loop: asyncio.AbstractEventLoop,
        logs_dir: str = "logs/",
        plugins_dir: str = "plugins/",
    ):
        self.logs_dir = Path(logs_dir)
        self.plugins_dir = Path(plugins_dir)
        self.loop = loop
        self.bot = commands.Bot(
            command_prefix=[],
            intents=discord.Intents.all(),
        )

    async def start(self):
        log.debug("on initializing")
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

        self._event_handling(self.bot)
        log.debug("Loading plugins")
        await self.load_plugins()

        async def _on_connect():
            await self.bot.wait_until_ready()
            await self.bot.tree.sync(guild=discord.Object(id=1319681052981330020))
            log.info(f"Connected to Discord: {self.bot.user}")

            guilds = self.bot.guilds
            log.info("")
            if guilds:
                for guild in guilds:
                    log.info(f"- {guild.id}/{guild.name} - {guild.owner or guild.owner_id}")
            else:
                log.info("  No joined guilds")
            log.info("")

        asyncio.create_task(_on_connect())

        log.debug("Connecting to Discord...")
        import os
        await self.bot.start(token=os.environ["TOKEN"])  # TODO: load from config

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
