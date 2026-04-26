import requests
import time
import threading
import os
from bs4 import BeautifulSoup

SERVER_URL = "https://luckyloop-tracker.onrender.com"
CAMPAIGNS  = ["1033", "1470", "2289", "1891"]
INTERVAL   = 30

PHPSESSID  = os.environ.get("MW_PHPSESSID", "")

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Cookie": f"PHPSESSID={PHPSESSID}"
})

def get_campaign_data(cid):
    try:
        url = f"https://microworkers.com/jobs.php?Filter={cid}"
        r = session.get(url, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        rows = soup.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) >= 3 and cid in row.get_text():
                position  = cells[1].get_text(strip=True)
                available = cells[2].get_text(strip=True)
                return position, available, url
        return None, None, None
    except Exception as e:
        print(f"[Scraper] Campaign {cid} error: {e}")
        return None, None, None

def push(cid, position, available, link):
    try:
        requests.post(f"{SERVER_URL}/save", json={
            "job_name" : cid,
            "position" : position,
            "available": available,
            "link"     : link
        }, timeout=10)
        print(f"[Scraper] Pushed {cid} pos={position} avail={available}")
    except Exception as e:
        print(f"[Scraper] Push error: {e}")

def scrape_loop():
    print("[Scraper] Starting with cookie session...")
    time.sleep(5)
    while True:
        for cid in CAMPAIGNS:
            pos, avail, link = get_campaign_data(cid)
            if pos:
                push(cid, pos, avail, link)
            time.sleep(3)
        print(f"[Scraper] Sleeping {INTERVAL}s...")
        time.sleep(INTERVAL)

def start_scraper():
    t = threading.Thread(target=scrape_loop, daemon=True)
    t.start()
