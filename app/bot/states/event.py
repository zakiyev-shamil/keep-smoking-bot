from aiogram.fsm.state import State, StatesGroup


class CustomEventState(StatesGroup):
    waiting_for_title = State()
    confirming = State()


class LunchPollState(StatesGroup):
    waiting_for_options = State()
    confirming = State()
