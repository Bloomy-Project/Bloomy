import asyncio
import signal
from logging import getLogger
from pathlib import Path

import discord.app_commands
from discord.ext import commands

from bloomy._logger import BloomyStreamHandler, BloomyFileHandler
from bloomy.config import DictConfig
from bloomy.database import DatabaseManager
from bloomy.plugin import PluginManager
from bloomy.ui._discord import hook_error_handlers, unhook_error_handlers
from bloomy.util import traceback_format_simple, with_error

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
    replace_error_message: bool = True

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
        hook_error_handlers()
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

    def __del__(self):
        unhook_error_handlers()

    def setup_loggers(self, *names: str, file_out=True, discord_level: int | None = None):
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

        if discord_level is not None:
            _log = getLogger("discord")
            _log.setLevel(discord_level)
            _log.addHandler(self.log_stream_handler)
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
        self.setup_bot(self.bot)
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

    def setup_bot(self, bot: commands.Bot):
        _tree_on_error = bot.tree.on_error

        async def on_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
            await _tree_on_error(interaction, error)
            await self.handle_interaction_error("App Command", interaction, error)

        bot.tree.on_error = on_error

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

    async def handle_interaction_error(
        self,
        error_type: str,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError | Exception,
    ):
        r = interaction.response  # type: discord.InteractionResponse

        if self.config.replace_error_message:
            embed = discord.Embed(
                description="内部エラーが発生しました。管理者にお問い合わせください。",
                color=0xFF0000,
            )

            try:
                if r.is_done():
                    await interaction.edit_original_response(content=None, embed=embed, view=None)
                else:
                    await r.send_message(embed=embed, ephemeral=True)
            except Exception as e:
                log.warning("Exception in send user error message", exc_info=e)

        try:
            await self.report_error_to_owner(error_type, interaction, error)
        except Exception as e:
            log.warning("Exception in send owners error report", exc_info=e)

    async def report_error_to_owner(
        self,
        error_type: str,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError | Exception,
    ):
        if not self.owners:
            return

        guild = interaction.guild
        channel = interaction.channel
        user = interaction.user
        exc = error.original if isinstance(error, discord.app_commands.CommandInvokeError) else error

        input_command = None
        if isinstance(interaction.command, discord.app_commands.Command):
            input_command = "/" + interaction.command.name
            args = interaction.namespace.__dict__
            if args:
                args = ", ".join(f"{k}:{repr(v)}" for k, v in args.items())
                input_command += f" {{{args}}}"

        if isinstance(guild, discord.Guild):
            jump_url = channel.jump_url
            try:
                res_message = await interaction.original_response()
            except discord.HTTPException:
                pass
            else:
                if not res_message.flags.ephemeral:
                    jump_url = res_message.jump_url

            location = f"[{guild} #{channel}]({jump_url})"
            report = (f":warning: コマンド実行エラーです ({error_type})\n\n"
                      f"> メッセージ: {str(exc)}\n"
                      f"> 場所: {location}\n"
                      f"> 実行者: {user}\n"
                      f"> コマンド: `{input_command or 'N/A'}`")
        else:
            report = (f":warning: コマンド実行エラーです ({error_type})\n\n"
                      f"> メッセージ: {str(exc)}\n"
                      f"> 場所: @{user} チャンネル\n"
                      f"> コマンド: `{input_command or 'N/A'}`")

        require = "```py\n```"
        split_trace = ""
        trace = list(reversed(traceback_format_simple(exc).replace("```", "\\```").splitlines()))
        line = trace.pop(0)
        while 0 <= 2000 - len(split_trace + require + line + "\n"):
            split_trace = line + "\n" + split_trace
            if trace:
                line = trace.pop(0)
            else:
                break

        content = f"```py\n{split_trace}```"
        embed = discord.Embed(description=report, color=0xFF0000)

        for owner in self.owners.values():
            if owner is not None:
                task = self.loop.create_task(owner.send(content=content, embed=embed))
                task.add_done_callback(with_error(log, lambda e: f"Failed to send to {owner}: {e}", exc_info=False))
