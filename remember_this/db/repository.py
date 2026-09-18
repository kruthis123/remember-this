from datetime import datetime

import asyncpg
from pgvector.asyncpg import register_vector

from remember_this.config import get_settings
from remember_this.models import MemoryMatch

_pool: asyncpg.Pool | None = None


async def _init_connection(connection: asyncpg.Connection) -> None:
    """Run once per pooled connection so it knows how to (de)serialize `vector`."""
    await register_vector(connection)


async def init_pool() -> None:
    """Create the pool. Call once at startup. Safe to call more than once."""
    global _pool
    if _pool is not None:
        return
    database_url = get_settings().database_url
    _pool = await asyncpg.create_pool(
        dsn=database_url,
        init=_init_connection,
    )


async def close_pool() -> None:
    """Close the pool. Call at shutdown."""
    global _pool
    if _pool is None:
        raise RuntimeError("close_pool() called before init_pool().")
    await _pool.close()
    _pool = None


def _get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Connection pool not initialized. Call init_pool() first.")
    return _pool


# --- messages / memories ---

async def save_message_with_memories(
    user_id: int,
    raw_text: str,
    facts: list[tuple[str, list[float]]],
) -> int:
    """Store the raw message and its extracted facts atomically. Returns the message id."""
    pool = _get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            message_id = await conn.fetchval(
                """
                INSERT INTO messages (user_id, raw_text)
                VALUES ($1, $2)
                RETURNING id
                """,
                user_id,
                raw_text,
            )
            if facts:
                await conn.executemany(
                    """
                    INSERT INTO memories (user_id, message_id, fact_text, embedding)
                    VALUES ($1, $2, $3, $4)
                    """,
                    [
                        (user_id, message_id, fact_text, embedding)
                        for fact_text, embedding in facts
                    ],
                )
            return message_id


async def search_memories(
    user_id: int,
    query_embedding: list[float],
    threshold: float,
    limit: int,
) -> list[MemoryMatch]:
    pool = _get_pool()
    rows = await pool.fetch(
        """
        SELECT id, fact_text, created_at,
               1 - (embedding <=> $1) AS similarity
        FROM memories
        WHERE user_id = $2
          AND 1 - (embedding <=> $1) >= $3
        ORDER BY embedding <=> $1
        LIMIT $4
        """,
        query_embedding,
        user_id,
        threshold,
        limit,
    )
    return [MemoryMatch(**row) for row in rows]


async def delete_all_memories(user_id: int) -> None:
    """Wipe everything for this user: messages, and their memories via ON DELETE CASCADE."""
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            DELETE FROM messages
            WHERE user_id = $1
            """,
            user_id,
        )


# --- idempotency ---

async def claim_update(update_id: int) -> bool:
    """Return True if this update_id is new, False if it has already been processed."""
    pool = _get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO processed_updates (update_id)
                VALUES ($1)
                """,
                update_id,
            )
    except asyncpg.UniqueViolationError:
        return False
    return True


# --- users / usage ---

async def record_turn(user_id: int) -> None:
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO usages (user_id)
            VALUES ($1)
            """,
            user_id,
        )


async def count_recent_turns(user_id: int, since: datetime) -> int:
    pool = _get_pool()
    return await pool.fetchval(
        """
        SELECT COUNT(*)
        FROM usages
        WHERE user_id = $1
          AND created_at >= $2
        """,
        user_id,
        since,
    )
