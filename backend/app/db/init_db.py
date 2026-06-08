"""
Run this once to create all tables:
  python -m app.db.init_db
"""
import asyncio
from app.db.session import engine, Base

# Import all models so Base knows about them
from app.models import user, project  # noqa


async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ All tables created")


if __name__ == "__main__":
    asyncio.run(init())
