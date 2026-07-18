from aiogram.fsm.state import State, StatesGroup


class CreatePartyState(StatesGroup):
    waiting_for_name = State()
