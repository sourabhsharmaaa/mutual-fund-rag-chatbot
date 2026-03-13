import httpx
import logging

logger = logging.getLogger(__name__)

async def fetch_live_nav(fund_code: str) -> str:
    """Fetches live NAV from AMFI portal using async httpx."""
    # AMFI Portal URL
    AMFI_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"
    
    amfi_codes = {
        "PPFCF": "122639", # Parag Parikh Flexi Cap Fund - Direct Plan - Growth
        "PPTSF": "147481", # Parag Parikh ELSS Tax Saver Fund- Direct Growth
        "PPCHF": "148958", # Parag Parikh Conservative Hybrid Fund - Direct Plan - Growth
        "PPLF": "143269",  # Parag Parikh Liquid Fund- Direct Plan- Growth
    }
    
    full_names = {
        "PPFCF": "Parag Parikh Flexi Cap Fund",
        "PPTSF": "Parag Parikh ELSS Tax Saver Fund",
        "PPCHF": "Parag Parikh Conservative Hybrid Fund",
        "PPLF": "Parag Parikh Liquid Fund",
    }
    
    code = amfi_codes.get(fund_code)
    if not code:
        return ""

    import asyncio

    # Retry parameters - keep timeout short enough to stay under Render's 30s limit
    MAX_ATTEMPTS = 2
    TIMEOUT = 8.0

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=TIMEOUT) as client:
                resp = await client.get(AMFI_URL, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True)
                if resp.status_code == 200:
                    # AMFI uses latin-1; try utf-8 first, then fall back
                    try:
                        text = resp.content.decode("utf-8")
                    except UnicodeDecodeError:
                        text = resp.content.decode("latin-1")
                    
                    lines = text.split('\n')
                    for line in lines:
                        if line.startswith(code):
                            parts = line.split(';')
                            if len(parts) >= 6:
                                nav_value = parts[4]
                                date = parts[5].strip()
                                display_name = full_names.get(fund_code, fund_code)
                                return f"The current NAV (Net Asset Value) of {display_name} as of {date} is ₹{nav_value}."
                    
                    logger.warning(f"Fund code {code} not found in AMFI list on attempt {attempt}")
                else:
                    logger.error(f"AMFI returned status {resp.status_code} on attempt {attempt}")
                    
        except Exception as e:
            logger.error(f"Attempt {attempt} failed to fetch NAV for {fund_code}: {e}")
        
        if attempt < MAX_ATTEMPTS:
            await asyncio.sleep(1)

    # Return empty string — generator will fall back to seed NAV data
    logger.warning(f"All NAV fetch attempts failed for {fund_code}, returning empty.")
    return ""

