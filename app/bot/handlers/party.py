from __future__ import annotations

from math import ceil

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks.common import MenuCallback
from app.bot.callbacks.party import (
    PartyCallback,
    PartyMemberAdminCallback,
    PartyMembersCallback,
)
from app.bot.keyboards.common import cancel_fsm_keyboard, party_selector_keyboard
from app.bot.keyboards.party import (
    delete_party_confirmation_keyboard,
    members_keyboard,
    party_created_keyboard,
    party_keyboard,
    stats_keyboard,
)
from app.bot.states.party import CreatePartyState
from app.bot.texts.ru import (
    CREATE_PARTY_NAME,
    INVALID_PARTY_NAME,
    delete_party_confirmation,
    members_text,
    party_created,
    party_screen,
    user_party_stats_text,
)
from app.bot.utils import edit_or_answer
from app.core.enums import PartyRole
from app.core.exceptions import PartyNameInvalidError, PermissionDeniedError
from app.models.user import User
from app.services.container import RequestServices, ServiceContainer

router = Router(name="party")
PAGE_SIZE = 10


@router.callback_query(MenuCallback.filter(F.action == "create_party"))
async def begin_create_party(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CreatePartyState.waiting_for_name)
    if callback.message:
        await edit_or_answer(callback.message, CREATE_PARTY_NAME, cancel_fsm_keyboard())


@router.message(CreatePartyState.waiting_for_name)
async def finish_create_party(
    message: Message,
    state: FSMContext,
    current_user: User,
    services: RequestServices,
    container: ServiceContainer,
    bot: Bot,
) -> None:
    try:
        party = await services.parties.create_party(current_user.id, message.text or "")
    except PartyNameInvalidError:
        await message.answer(INVALID_PARTY_NAME, reply_markup=cancel_fsm_keyboard())
        return
    await state.clear()
    username = container.settings.bot_username or (await bot.get_me()).username
    invite_url = container.invitations.deep_link(username, party.invite_code)
    await message.answer(
        party_created(party.name, invite_url),
        reply_markup=party_created_keyboard(party.id, invite_url),
    )


@router.callback_query(PartyCallback.filter(F.action == "open"))
async def open_party(
    callback: CallbackQuery,
    callback_data: PartyCallback,
    current_user: User,
    services: RequestServices,
    state: FSMContext,
) -> None:
    await state.clear()
    party, membership = await services.parties.get_party_for_member(
        callback_data.party_id,
        current_user.id,
    )
    await services.parties.set_active_party(current_user.id, party.id)
    count = await services.parties.count_members(party.id)
    if callback.message:
        await edit_or_answer(
            callback.message,
            party_screen(party.name, count),
            party_keyboard(
                party.id,
                is_owner=membership.role == PartyRole.OWNER,
            ),
        )


@router.callback_query(PartyCallback.filter(F.action == "delete"))
async def confirm_delete_party(
    callback: CallbackQuery,
    callback_data: PartyCallback,
    current_user: User,
    services: RequestServices,
) -> None:
    party, membership = await services.parties.get_party_for_member(
        callback_data.party_id,
        current_user.id,
    )
    if membership.role != PartyRole.OWNER or party.owner_id != current_user.id:
        raise PermissionDeniedError
    if callback.message:
        await edit_or_answer(
            callback.message,
            delete_party_confirmation(party.name),
            delete_party_confirmation_keyboard(party.id),
        )


@router.callback_query(PartyCallback.filter(F.action == "delete_confirm"))
async def delete_party(
    callback: CallbackQuery,
    callback_data: PartyCallback,
    current_user: User,
    services: RequestServices,
    state: FSMContext,
) -> None:
    await services.parties.delete_party(callback_data.party_id, current_user.id)
    await state.clear()
    if callback.message:
        from app.bot.handlers.common import show_menu

        await show_menu(callback.message, current_user, services, edit=True)


@router.callback_query(PartyCallback.filter(F.action == "switch"))
async def switch_party(
    callback: CallbackQuery,
    current_user: User,
    services: RequestServices,
) -> None:
    parties = await services.parties.get_user_parties(current_user.id)
    if callback.message:
        await edit_or_answer(
            callback.message,
            "Выбери Party:",
            party_selector_keyboard(parties),
        )


@router.callback_query(PartyCallback.filter(F.action == "stats"))
async def show_stats(
    callback: CallbackQuery,
    callback_data: PartyCallback,
    current_user: User,
    services: RequestServices,
) -> None:
    stats = await services.stats.get_user_party_stats(
        callback_data.party_id,
        current_user.id,
    )
    if callback.message:
        await edit_or_answer(
            callback.message,
            user_party_stats_text(stats),
            stats_keyboard(callback_data.party_id),
        )


@router.callback_query(PartyCallback.filter(F.action == "invite"))
async def show_invite(
    callback: CallbackQuery,
    callback_data: PartyCallback,
    current_user: User,
    services: RequestServices,
    container: ServiceContainer,
    bot: Bot,
) -> None:
    party, membership = await services.parties.get_party_for_member(
        callback_data.party_id, current_user.id
    )
    if membership.role not in {PartyRole.OWNER, PartyRole.ADMIN}:
        raise PermissionDeniedError
    username = container.settings.bot_username or (await bot.get_me()).username
    invite_url = container.invitations.deep_link(username, party.invite_code)
    if callback.message:
        await edit_or_answer(
            callback.message,
            f"Приглашение в 🏢 {party.name}:\n\n{invite_url}",
            party_created_keyboard(party.id, invite_url),
        )


@router.callback_query(PartyMembersCallback.filter())
async def list_members(
    callback: CallbackQuery,
    callback_data: PartyMembersCallback,
    current_user: User,
    services: RequestServices,
) -> None:
    party, requester, members, total = await services.parties.get_party_members(
        callback_data.party_id,
        current_user.id,
        callback_data.page,
        PAGE_SIZE,
    )
    pages = max(1, ceil(total / PAGE_SIZE))
    page = min(max(0, callback_data.page), pages - 1)
    if page != callback_data.page:
        party, requester, members, total = await services.parties.get_party_members(
            callback_data.party_id,
            current_user.id,
            page,
            PAGE_SIZE,
        )
    if callback.message:
        await edit_or_answer(
            callback.message,
            members_text(party.name, members, total, page, pages),
            members_keyboard(
                party_id=party.id,
                page=page,
                total=total,
                page_size=PAGE_SIZE,
                requester_role=requester.role,
                members=members,
            ),
        )


@router.callback_query(PartyMemberAdminCallback.filter())
async def change_admin(
    callback: CallbackQuery,
    callback_data: PartyMemberAdminCallback,
    current_user: User,
    services: RequestServices,
) -> None:
    role = PartyRole.ADMIN if callback_data.action == "promote" else PartyRole.MEMBER
    membership = await services.parties.set_membership_role(
        callback_data.membership_id,
        current_user.id,
        role,
    )
    party, requester, members, total = await services.parties.get_party_members(
        membership.party_id, current_user.id, 0, PAGE_SIZE
    )
    pages = max(1, ceil(total / PAGE_SIZE))
    if callback.message:
        await edit_or_answer(
            callback.message,
            members_text(party.name, members, total, 0, pages),
            members_keyboard(
                party_id=party.id,
                page=0,
                total=total,
                page_size=PAGE_SIZE,
                requester_role=requester.role,
                members=members,
            ),
        )
