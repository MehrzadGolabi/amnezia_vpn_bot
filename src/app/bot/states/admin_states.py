from aiogram.fsm.state import State, StatesGroup


class AdminTicketStates(StatesGroup):
    waiting_for_reply = State()
