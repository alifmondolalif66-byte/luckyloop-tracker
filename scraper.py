import requests
import time
import threading
from bs4 import BeautifulSoup
import os

MW_EMAIL    = os.environ.get("MW_EMAIL", "bdmicroworkers376@gmail.com")
MW_PASSWORD = os.environ.get("MW_PASSWORD", "YOUR_NEW_PASSWORD")
SERVER_URL  = "https://luckyloop-tracker.onrender.com"
CAMPAIGNS   = ["1033", "1470", "2289", "1891"]
INTERVAL    = 30

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
})

def login():
    try:
        r = session.get("https://microworkers.com/login.php", timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        token_input = soup.find("input", {"name": "token"})
        token = token_input["value"] if token_input else ""
        payload = {
            "email"   : MW_EMAIL,
            "password": MW_PASSWORD,
            "token"   : token,
            "submit"  : "Login"
        }
        r2 = session.post("https://microworkers.com/login.php", data=payload, timeout=15)
        if "logout" in r2.text.lower():
            print("[Scraper] Login OK!")
            return True
        print("[Scraper] Login FAILED!")
        return False
    except Exception as e:
        print(f"[Scraper] Login error: {e}")
        return False

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
        r = requests.post(f"{SERVER_URL}/save", json={
            "job_name" : cid,
            "position" : position,
            "available": available,
            "link"     : link
        }, timeout=10)
        print(f"[Scraper] Pushed {cid} pos={position} avail={available}")
    except Exception as e:
        print(f"[Scraper] Push error: {e}")

def scrape_loop():
    print("[Scraper] Starting background scraper...")
    time.sleep(10)
    if not login():
        time.sleep(60)
        login()
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
