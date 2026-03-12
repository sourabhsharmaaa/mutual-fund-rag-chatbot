import requests # type: ignore
import json
import os
import sys
import time
import random
from typing import List, Dict

# Set up paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BASE_DIR, "data", "structured", "mutual_funds.json")

# A list of realistic browser user agents to rotate
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1"
]

def check_link(url: str, fund_name: str, retry_count: int = 2) -> Dict:
    """Checks the health of a single URL with retry logic and agent rotation."""
    report = {
        "url": url,
        "fund": fund_name,
        "status": "OK",
        "error": None,
        "type": "standard"
    }
    
    for attempt in range(retry_count + 1):
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/"
        }

        try:
            # We use a session to handle cookies if needed
            session = requests.Session()
            resp = session.get(url, headers=headers, timeout=12)
            
            # If we get 403, try again with a delay (anti-bot cooldown)
            if resp.status_code == 403:
                if attempt < retry_count:
                    time.sleep(2 * (attempt + 1))
                    continue
                report["status"] = "BROKEN"
                report["error"] = "HTTP 403 (Forbidden/Bot Protection Blocked Access)"
                return report

            if resp.status_code != 200:
                report["status"] = "BROKEN"
                report["error"] = f"HTTP {resp.status_code}"
                return report

            # Special handling for INDmoney (Dynamic 404s)
            if "indmoney.com" in url:
                report["type"] = "INDmoney"
                error_keywords = [
                    "We could not find the page you are looking for",
                    "404 - Page Not Found"
                ]
                content = resp.text
                if any(kw in content for kw in error_keywords):
                    report["status"] = "BROKEN"
                    report["error"] = "Dynamic 404 (Page Not Found content detected)"
                    return report
            
            # If we reached here, status is OK
            report["status"] = "OK"
            report["error"] = None
            return report

        except requests.exceptions.RequestException as e:
            if attempt < retry_count:
                time.sleep(1)
                continue
            report["status"] = "BROKEN"
            report["error"] = f"Connection Failed: {str(e)}"
            return report

    return report

def main():
    print("🚀 Starting Mutual Fund Link Health Validator v2...")
    
    if not os.path.exists(DATA_PATH):
        print(f"❌ Error: Data file not found at {DATA_PATH}")
        sys.exit(1)

    with open(DATA_PATH, 'r') as f:
        data = json.load(f)

    schemes = data.get("schemes", [])
    total_checked = 0
    broken_links = []

    print(f"📊 Found {len(schemes)} schemes. Validating links...\n")

    for scheme in schemes:
        fund_name = scheme.get("scheme_name", "Unknown")
        urls = scheme.get("source_urls", [])
        
        for url in urls:
            total_checked += 1 # type: ignore
            print(f"🔎 Checking: {url[:60]}...")
            result = check_link(url, fund_name)
            
            if result["status"] == "BROKEN":
                print(f"   ❌ BROKEN: {result['error']}")
                broken_links.append(result)
            else:
                print(f"   ✅ OK")
            
            # Tiny sleep to be polite
            time.sleep(0.5)

    print("\n" + "="*50)
    print("✅ Validation Finished!")
    print(f"📝 Total Links Checked: {total_checked}")
    print(f"🚩 Total Broken Links: {len(broken_links)}")
    print("="*50)

    if broken_links:
        print("\n🚨 ACTION REQUIRED: The following links are broken:")
        for bl in broken_links:
            print(f"- [{bl['fund']}] -> {bl['url']} (Reason: {bl['error']})")
        sys.exit(1)
    else:
        print("\n✨ All links are healthy!")
        sys.exit(0)

if __name__ == "__main__":
    main()
