from aiogram.fsm.state import State, StatesGroup


class AdminTicketStates(StatesGroup):
    waiting_for_reply = State()


class AdminBroadcastStates(StatesGroup):
    waiting_for_message = State()
    confirming = State()
