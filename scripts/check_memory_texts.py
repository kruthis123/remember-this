import asyncio
import sys

from remember_this.db import repository as db


async def main() -> None:
    ids = [int(x) for x in sys.argv[1:]]
    await db.init_pool()
    try:
        rows = await db._get_pool().fetch(
            "SELECT id, fact_text FROM memories WHERE id = ANY($1) ORDER BY id",
            ids,
        )
        for row in rows:
            print(row["id"], "->", row["fact_text"])
    finally:
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
