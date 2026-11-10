import asyncio
import sys

# Ensure UTF-8 output for Windows console
sys.stdout.reconfigure(encoding='utf-8')

from sqlalchemy import text
from app.db.session import async_engine, async_session_factory
from app.core.config import settings


async def main():
    print(f"Connecting to: {settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}...")
    
    async with async_session_factory() as session:
        # Test 1: Ping
        result = await session.execute(text("SELECT 1 AS alive"))
        print(f"Ping result: {result.scalar_one()}")

        # Test 2: Fetch 5 properties
        query = text("""
            SELECT id, name_ar 
            FROM properties 
            WHERE status = 1 
            LIMIT 5
        """)
        res = await session.execute(query)
        rows = res.fetchall()

        print(f"\nSuccessfully retrieved {len(rows)} hotels from database:")
        for row in rows:
            print(f"- [ID: {row.id}] {row.name_ar}")

    # Dispose engine
    await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
