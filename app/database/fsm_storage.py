from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.bot_fsm_state import BotFsmState


class PostgresStorage(BaseStorage):
    """Small persistent aiogram FSM storage backed by the application's database."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    @staticmethod
    def _key(key: StorageKey) -> str:
        payload = json.dumps(
            {
                "bot_id": key.bot_id,
                "chat_id": key.chat_id,
                "user_id": key.user_id,
                "thread_id": key.thread_id,
                "business_connection_id": key.business_connection_id,
                "destiny": key.destiny,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return f"fsm:{hashlib.sha256(payload.encode()).hexdigest()}"

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        state_value = state.state if isinstance(state, State) else state
        await self._upsert(self._key(key), state=state_value)

    async def get_state(self, key: StorageKey) -> str | None:
        async with self.session_factory() as session:
            return await session.scalar(
                select(BotFsmState.state).where(BotFsmState.key == self._key(key))
            )

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        await self._upsert(self._key(key), data=dict(data))

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        async with self.session_factory() as session:
            value = await session.scalar(
                select(BotFsmState.data).where(BotFsmState.key == self._key(key))
            )
        return dict(value or {})

    async def close(self) -> None:
        return None

    async def _upsert(
        self,
        key: str,
        *,
        state: str | None | object = ...,
        data: dict[str, Any] | object = ...,
    ) -> None:
        async with self.session_factory() as session:
            dialect = session.get_bind().dialect.name
            values: dict[str, Any] = {"key": key}
            updates: dict[str, Any] = {"updated_at": func.now()}
            if state is not ...:
                values["state"] = state
                updates["state"] = state
            if data is not ...:
                values["data"] = data
                updates["data"] = data
            values.setdefault("state", None)
            values.setdefault("data", {})

            if dialect == "postgresql":
                statement = postgresql_insert(BotFsmState).values(**values)
                statement = statement.on_conflict_do_update(
                    index_elements=[BotFsmState.key],
                    set_=updates,
                )
                await session.execute(statement)
            elif dialect == "sqlite":
                statement = sqlite_insert(BotFsmState).values(**values)
                statement = statement.on_conflict_do_update(
                    index_elements=[BotFsmState.key],
                    set_=updates,
                )
                await session.execute(statement)
            else:
                row = await session.get(BotFsmState, key)
                if row is None:
                    session.add(BotFsmState(**values))
                else:
                    if state is not ...:
                        row.state = state
                    if data is not ...:
                        row.data = data
            await session.commit()
