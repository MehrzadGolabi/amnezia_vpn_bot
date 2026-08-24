import pytest
from pydantic import SecretStr
from src.app.config.settings import Settings
from src.app.db.session import get_engine, get_session_factory, get_db_session, dispose_engine
from src.app.db.models.base import Base
from src.app.db.models.user import User


@pytest.mark.asyncio
async def test_session_lifecycle():
    custom_settings = Settings(
        TELEGRAM_BOT_TOKEN="token",
        ADMIN_TELEGRAM_IDS=[123],
        ADMIN_CHAT_ID=-100,
        DATABASE_URL=SecretStr("sqlite+aiosqlite:///:memory:"),
    )
    
    engine = get_engine(custom_settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    async with get_db_session(custom_settings) as session:
        user = User(telegram_user_id=88888, username="session_user")
        session.add(user)
    
    # Verify committed in new session
    async with get_db_session(custom_settings) as session:
        res = await session.get(User, user.id)
        assert res is not None
        assert res.username == "session_user"

    await dispose_engine()
