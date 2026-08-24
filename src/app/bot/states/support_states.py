from aiogram.fsm.state import State, StatesGroup


class SupportStates(StatesGroup):
    writing_message = State()
