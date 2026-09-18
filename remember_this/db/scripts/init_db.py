from pathlib import Path
import asyncpg
import asyncio
import sys

from remember_this.config import get_settings

"""
Command to run the script from the root of this project: 
uv run python -m remember_this.db.scripts.init_db
"""

async def initialize_schema():
    DATABASE_URL = get_settings().database_url
    schema_file_path = Path(__file__).parent.parent / "schema.sql"

    try:
        sql_commands = schema_file_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"Error: Could not find the schema file as {schema_file_path}")
        sys.exit(1)

    connection = await asyncpg.connect(DATABASE_URL)
    print("Successfully connected to the database")

    try:
        await connection.execute(sql_commands)
        print("Schema executed successfully")
    except Exception as e:
        print(f"An error occurred while executing the SQL: {e}")
        sys.exit(1)
    finally:
        await connection.close()

def main() -> None:
    asyncio.run(initialize_schema())

    
if __name__ == "__main__":
    main()
