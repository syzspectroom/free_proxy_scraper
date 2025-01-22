import requests
import re
import concurrent.futures
import threading
import time
from datetime import datetime
from colorama import Fore, Style, init
from termcolor import colored
from bs4 import BeautifulSoup

# Initialize colorama
init(autoreset=True)

TEST_URL = "http://httpbin.org/ip"
TIMEOUT = 5
MAX_WORKERS = 30
OUTPUT_FILE = "valid_proxies.txt"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
}
SCRAPE_DELAY = 1  # Seconds between scrapers

print_lock = threading.Lock()
checked_count = 0
total_proxies = 0


def scrape_spysme():
    try:
        c = requests.get("https://spys.me/proxy.txt",
                         headers=HEADERS, timeout=10)
        regex = r"[0-9]+(?:\.[0-9]+){3}:[0-9]+"
        return [m.group() for m in re.finditer(regex, c.text)]
    except Exception:
        return []


def scrape_free_proxy_list():
    try:
        d = requests.get("https://free-proxy-list.net/",
                         headers=HEADERS, timeout=10)
        soup = BeautifulSoup(d.content, 'html.parser')
        rows = soup.select('.fpl-list .table tbody tr')
        return [f"{row.select_one('td').text}:{row.select_one('td:nth-child(2)').text}" for row in rows]
    except Exception:
        return []


def scrape_sslproxies():
    try:
        res = requests.get("https://www.sslproxies.org/",
                           headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.content, 'html.parser')
        textarea = soup.find('textarea', {'readonly': 'readonly'})
        if textarea:
            proxies = []
            for line in textarea.text.split('\n'):
                if re.match(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+', line.strip()):
                    proxies.append(line.strip())
            return proxies
        return []
    except Exception:
        return []


def scrape_geonode():
    try:
        url = "https://proxylist.geonode.com/api/proxy-list?protocols=http%2Chttps&limit=500&page=1&sort_by=lastChecked&sort_type=desc"
        res = requests.get(url, headers=HEADERS, timeout=10)
        data = res.json()
        return [f"{p['ip']}:{p['port']}" for p in data.get('data', [])
                if any(proto in p.get('protocols', []) for proto in ['http', 'https'])]
    except Exception:
        return []


def scrape_proxyscrape():
    try:
        res = requests.get("https://api.proxyscrape.com/v3/free-proxy-list/get?request=displayproxies",
                           headers=HEADERS, timeout=10)
        return [line.strip() for line in res.text.splitlines() if re.match(r'\d+\.\d+\.\d+\.\d+:\d+', line.strip())]
    except Exception:
        return []


def scrape_hidemy():
    try:
        res = requests.get("https://hidemy.name/en/proxy-list/",
                           headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.content, 'html.parser')
        return [f"{row.select_one('td').text}:{row.select_one('td:nth-child(2)').text}"
                for row in soup.select('.table_block table tr') if row.select('td')]
    except Exception:
        return []


def scrape_usproxy():
    try:
        res = requests.get("https://www.us-proxy.org/",
                           headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.content, 'html.parser')
        textarea = soup.find('textarea', {'readonly': 'readonly'})
        if textarea:
            proxies = []
            for line in textarea.text.split('\n'):
                if re.match(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+', line.strip()):
                    proxies.append(line.strip())
            return proxies
        return []
    except Exception:
        return []


SCRAPERS = [
    ("spys.me", scrape_spysme),
    ("free-proxy-list.net", scrape_free_proxy_list),
    ("SSLProxies", scrape_sslproxies),
    ("GeoNode", scrape_geonode),
    ("ProxyScrape", scrape_proxyscrape),
    ("HideMy", scrape_hidemy),
    ("US-Proxy", scrape_usproxy)
]


def print_status(message, emoji, color=Fore.WHITE):
    with print_lock:
        print(f"{emoji}  {color}{message}{Style.RESET_ALL}")


def check_proxy(proxy):
    global checked_count
    proxies = {"http": f"http://{proxy}", "https": f"http://{proxy}"}

    try:
        start_time = datetime.now()
        response = requests.get(TEST_URL, proxies=proxies, timeout=TIMEOUT)

        if response.status_code == 200:
            latency = (datetime.now() - start_time).total_seconds()
            print_status(
                f"{proxy.ljust(21)} | Latency: {latency:.2f}s | Valid",
                "✅",
                Fore.GREEN
            )
            return proxy
        else:
            print_status(
                f"{proxy.ljust(21)} | HTTP {response.status_code} | Invalid",
                "❌",
                Fore.RED
            )
    except Exception as e:
        error = str(e).split("\n")[0]
        print_status(
            f"{proxy.ljust(21)} | {error[:30].ljust(30)} | Error",
            "⚠️ ",
            Fore.YELLOW
        )
    finally:
        with print_lock:
            checked_count += 1
            print(
                f"⏳ Checked {checked_count}/{total_proxies} proxies...".rjust(50), end="\r")

    return None


def main():
    global total_proxies

    print("\n" + colored(" PROXY SCRAPER & CHECKER ",
          "white", "on_blue", attrs=["bold"]))

    # Scrape proxies from all sources
    all_proxies = []
    for name, scraper in SCRAPERS:
        try:
            time.sleep(SCRAPE_DELAY)
            print(colored(f"\n🌐 Scraping {name}...", "cyan"))
            proxies = scraper()
            print(colored(f"✅ Found {len(proxies)} proxies", "green"))
            all_proxies.extend(proxies)
        except Exception as e:
            print(colored(f"❌ Failed to scrape {name}: {str(e)[:50]}", "red"))

    # Remove duplicates while preserving order
    seen = set()
    unique_proxies = [p for p in all_proxies if not (p in seen or seen.add(p))]
    total_proxies = len(unique_proxies)

    if not unique_proxies:
        print(colored("\n❌ No proxies found. Exiting...", "red"))
        return

    print(colored(
        f"\n🌟 Total unique proxies found: {total_proxies}\n", "cyan", attrs=["bold"]))

    # Check proxies concurrently
    valid_proxies = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(check_proxy, proxy): proxy for proxy in unique_proxies}

        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                valid_proxies.append(result)

    # Save valid proxies
    with open(OUTPUT_FILE, "w") as f:
        f.write("\n".join(valid_proxies))

    # Final summary
    print("\n" + "━" * 50)
    print(colored("📋 Final Summary:", "cyan", attrs=["bold"]))
    print(colored(f"   Total scraped proxies:  {len(all_proxies)}", "white"))
    print(colored(f"   Unique proxies:         {total_proxies}", "white"))
    print(colored(
        f"   🔴 Invalid proxies:     {total_proxies - len(valid_proxies)}", "red"))
    print(colored(f"   🟢 Valid proxies:       {len(valid_proxies)}", "green"))
    print(colored(
        f"   Success rate:          {(len(valid_proxies)/total_proxies)*100:.1f}%", "yellow"))
    print("━" * 50)
    print(colored(f"\n💾 Valid proxies saved to: {OUTPUT_FILE}", "green"))


if __name__ == "__main__":
    main()
