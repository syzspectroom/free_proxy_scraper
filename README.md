# Free Proxy Scraper 🔍⚡

A Python script that scrapes free proxies from multiple sources, checks their validity, and saves working proxies to a file. Features colorful console output and parallel checking for maximum speed.

![Python Version](https://img.shields.io/badge/python-3.6%2B-blue)
![Dependencies](https://img.shields.io/badge/dependencies-requests%2Cbeautifulsoup4%2Ccolorama%2Ctermcolor-green)

## Features ✨

- Scrapes proxies from **7+ sources** simultaneously
- Multi-threaded validation with configurable workers
- Automatic duplicate removal
- Latency measurement for valid proxies ⏱️
- Lightweight and easy to modify

## Scraped Sources 🌐

1. spys.me
2. free-proxy-list.net
3. SSLProxies
4. GeoNode
5. ProxyScrape
6. HideMy
7. US-Proxy

## Installation 📦

```bash
pip install requests beautifulsoup4 colorama termcolor
```

## Usage 🚀

```bash
python proxy_checker.py
```

## Configuration ⚙️

Edit these variables at the top of `proxy_checker.py`:

```python
TEST_URL = "http://httpbin.org/ip"  # URL to test proxies against
TIMEOUT = 5                         # Connection timeout in seconds
MAX_WORKERS = 30                    # Concurrent validation threads
OUTPUT_FILE = "valid_proxies.txt"   # Output filename
SCRAPE_DELAY = 1                    # Delay between scrapers (seconds)
```

## Disclaimer ⚠️

Public proxies can be:

- Unreliable or slow
- Monitored by third parties
- Temporarily available
- Potentially insecure Potentially insecure

Use at your own risk. The maintainers are not responsible for any misuse.

## Contributing 🤝

Found a broken source? Open an issue! Want to add features? Submit a PR!
