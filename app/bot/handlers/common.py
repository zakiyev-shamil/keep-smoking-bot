from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks.common import MenuCallback
from app.bot.keyboards.common import menu_keyboard, no_party_keyboard, party_selector_keyboard
from app.bot.keyboards.party import party_keyboard
from app.bot.texts.ru import (
    HELP,
    INVALID_INVITATION,
    WELCOME_NO_PARTY,
    party_joined,
    party_screen,
)
from app.bot.utils import edit_or_answer
from app.core.exceptions import InvalidInvitationError
from app.models.user import User
from app.services.container import RequestServices

router = Router(name="common")


async def show_menu(
    message: Message,
    current_user: User,
    services: RequestServices,
    *,
    edit: bool = False,
) -> None:
    parties = await services.parties.get_user_parties(current_user.id)
    if not parties:
        if edit:
            await edit_or_answer(message, WELCOME_NO_PARTY, no_party_keyboard())
        else:
            await message.answer(WELCOME_NO_PARTY, reply_markup=no_party_keyboard())
        return
    if len(parties) > 1:
        text = "Выбери Party:"
        keyboard = party_selector_keyboard(parties)
        if edit:
            await edit_or_answer(message, text, keyboard)
        else:
            await message.answer(text, reply_markup=keyboard)
        return
    party = parties[0]
    await services.parties.set_active_party(current_user.id, party.id)
    count = await services.parties.count_members(party.id)
    if edit:
        await edit_or_answer(message, party_screen(party.name, count), party_keyboard(party.id))
    else:
        await message.answer(party_screen(party.name, count), reply_markup=party_keyboard(party.id))


@router.message(CommandStart())
async def start(
    message: Message,
    command: CommandObject,
    current_user: User,
    services: RequestServices,
) -> None:
    args = command.args or ""
    if args.startswith("join_"):
        token = args.removeprefix("join_")
        try:
            result = await services.parties.join_party(current_user.id, token)
        except InvalidInvitationError:
            await message.answer(INVALID_INVITATION, reply_markup=menu_keyboard())
            return
        await message.answer(party_joined(result.party.name, result.joined))
        count = await services.parties.count_members(result.party.id)
        await message.answer(
            party_screen(result.party.name, count),
            reply_markup=party_keyboard(result.party.id),
        )
        return
    await show_menu(message, current_user, services)


@router.message(Command("menu", "party"))
async def menu_command(
    message: Message, current_user: User, services: RequestServices, state: FSMContext
) -> None:
    await state.clear()
    await show_menu(message, current_user, services)


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(HELP, reply_markup=menu_keyboard())


@router.callback_query(MenuCallback.filter(F.action == "menu"))
async def menu_callback(
    callback: CallbackQuery,
    current_user: User,
    services: RequestServices,
    state: FSMContext,
) -> None:
    await state.clear()
    if callback.message:
        await show_menu(callback.message, current_user, services, edit=True)


@router.callback_query(MenuCallback.filter(F.action == "cancel_fsm"))
async def cancel_fsm(
    callback: CallbackQuery,
    current_user: User,
    services: RequestServices,
    state: FSMContext,
) -> None:
    await state.clear()
    if callback.message:
        await show_menu(callback.message, current_user, services, edit=True)
