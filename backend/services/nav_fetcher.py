import httpx
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

async def fetch_live_nav(fund_code: str) -> str:
    """Fetches live NAV from AMFI or the AMC site.
    We will map fund codes to AMFI scheme codes for reliable API fetching.
    """
    # AMFI API URL: https://www.amfiindia.com/spages/NAVAll.txt
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

    try:
        import requests
        import asyncio
        
        def _fetch():
            resp = requests.get("https://www.amfiindia.com/spages/NAVAll.txt", headers={"User-Agent": "Mozilla/5.0"}, timeout=5.0)
            if resp.status_code == 200:
                lines = resp.text.split('\n')
                for line in lines:
                    if line.startswith(code):
                        parts = line.split(';')
                        if len(parts) >= 6:
                            nav_value = parts[4]
                            date = parts[5].strip()
                            display_name = full_names.get(fund_code, fund_code)
                            return f"The current NAV (Net Asset Value) of {display_name} as of {date} is ₹{nav_value}."
            return ""
            
        return await asyncio.to_thread(_fetch)
        
    except Exception as e:
        logger.error(f"Failed to fetch NAV for {fund_code}: {e}")
    
    return ""
