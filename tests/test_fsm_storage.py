from aiogram.fsm.storage.base import StorageKey

from app.database.fsm_storage import PostgresStorage


async def test_fsm_state_and_data_survive_storage_instances(session_factory):
    key = StorageKey(bot_id=1, chat_id=2, user_id=3)
    first = PostgresStorage(session_factory)

    await first.set_state(key, "party:create")
    await first.set_data(key, {"party_id": "abc"})

    second = PostgresStorage(session_factory)
    assert await second.get_state(key) == "party:create"
    assert await second.get_data(key) == {"party_id": "abc"}

    await second.set_state(key, None)
    assert await first.get_state(key) is None
    assert await first.get_data(key) == {"party_id": "abc"}
