from typing import Any

import discord.ui.view
from discord import Interaction
from discord._types import ClientT
from discord.ui import Item

from bloomy.util import getbloomy


class FakeBaseView(discord.ui.view.BaseView):
    async def on_error(self, interaction: Interaction[ClientT], error: Exception, item: Item[Any], /) -> None:
        await _BaseView_on_error(self, interaction, error, item)
        await getbloomy().handle_interaction_error("View", interaction, error)


class FakeModal(discord.ui.Modal):
    async def on_error(self, interaction: Interaction[ClientT], error: Exception, /) -> None:
        await _Modal_on_error(self, interaction, error)
        await getbloomy().handle_interaction_error("Modal", interaction, error)


_BaseView_on_error = discord.ui.view.BaseView.on_error
_Modal_on_error = discord.ui.Modal.on_error


def hook_error_handlers():
    discord.ui.view.BaseView.on_error = FakeBaseView.on_error
    discord.ui.Modal.on_error = FakeModal.on_error
    pass


def unhook_error_handlers():
    discord.ui.view.BaseView.on_error = _BaseView_on_error
    discord.ui.Modal.on_error = _Modal_on_error
