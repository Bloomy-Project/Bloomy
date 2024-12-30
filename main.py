import logging
import os
import asyncio
import sys

from pathlib import Path

import discord
from discord.ext import commands
from ruamel.yaml import YAML

yaml = YAML()

# config.ymlの読み込み
with open("config/config.yml") as file:
    config = yaml.load(file)

log = logging.getLogger(__name__)
bot = commands.Bot(
    intents=discord.Intents.all(),  # 必要なものを選択すべし
    command_prefix=[],
)


@bot.event
async def on_ready():
    log.info(f"ボット {bot.user} で接続しました！")

    # アクティビティ、ステータスの変更 (必要であれば)
    guild_count = len(bot.guilds)
    game = discord.Game(f'{guild_count} サーバー数に導入されています')
    await bot.change_presence(status=discord.Status.online, activity=game)
    print(f"ステータスの変更が完了しました！")

    await bot.tree.sync()
    log.info("同期が完了しました！")


async def load_extensions():
    names = []
    plugins_dir = Path("plugins")
    plugins_dir.mkdir(exist_ok=True)
    for child in plugins_dir.iterdir():
        if child.name.startswith("_"):
            continue
        if child.is_file() and child.suffix == ".py":
            name = child.name.split(".")[0]
            await bot.load_extension(f"plugins.{name}")
            names.append(name)
        elif child.is_dir():
            name = child.name
            await bot.load_extension(f"plugins.{name}")
            names.append(name)

    log.info(f"プラグイン(%d)を読み込みました: %s", len(names), ", ".join(names))


async def on_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    command = interaction.command
    if command is not None:
        if command._has_any_error_handlers():
            return
        log.error('Ignoring exception in command %r', command.name, exc_info=error)
    else:
        log.error('Ignoring exception in command tree', exc_info=error)


async def main():
    async with bot:
        bot.tree.on_error = on_error
        await load_extensions()
        # config.ymlからトークンを読み込んでbotを起動
        await bot.start(config["token"])


if __name__ == '__main__':
    logging.basicConfig(
        format='{asctime} - {lineno:>3} {filename:16} | {levelname:>7s} - {message}',
        style='{',
        level=logging.DEBUG,
    )
    logging.getLogger(sys.modules[__name__].__package__).setLevel(logging.DEBUG)
    asyncio.run(main())