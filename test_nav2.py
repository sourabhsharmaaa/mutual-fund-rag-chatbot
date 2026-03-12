import asyncio
from backend.services.nav_fetcher import fetch_live_nav

async def main():
    print("PPFCF:", await fetch_live_nav("PPFCF"))
    print("PPTSF:", await fetch_live_nav("PPTSF"))

asyncio.run(main())
