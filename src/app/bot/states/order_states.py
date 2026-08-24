from aiogram.fsm.state import State, StatesGroup


class OrderFlowStates(StatesGroup):
    selecting_server = State()
    selecting_plan = State()
    awaiting_receipt = State()
