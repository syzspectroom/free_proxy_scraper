import asyncio
import argparse
import json
import os
import random
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.extraction_strategy import LLMExtractionStrategy
from dotenv import load_dotenv
from playwright.async_api import Error as PlaywrightError
from colorama import Fore, Style, init
from termcolor import colored

# Initialize colorama
init(autoreset=True)

load_dotenv()


class ProxyManager:
    def __init__(self, proxy_file: Optional[str] = None):
        self.proxies = []
        if proxy_file and Path(proxy_file).exists():
            with open(proxy_file, 'r') as f:
                self.proxies = [self._format_proxy(
                    line.strip()) for line in f if line.strip()]
            random.shuffle(self.proxies)

    def _format_proxy(self, proxy: str) -> str:
        """Ensure HTTP proxy format"""
        if proxy.startswith(("http://", "https://")):
            return proxy
        return f"http://{proxy}"

    def get_random_proxy(self) -> Optional[str]:
        return random.choice(self.proxies) if self.proxies else None

    def remove_proxy(self, proxy: str):
        if proxy in self.proxies:
            self.proxies.remove(proxy)


class ArticleScraper:
    def __init__(self, proxy_file: Optional[str] = None, max_retries: int = 3):
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY not found in .env file")

        self.proxy_manager = ProxyManager(proxy_file)
        self.max_retries = max_retries
        self.current_attempt = 0

        self.article_schema = {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "publish_date": {"type": "string", "format": "date"},
                "content": {"type": "string"},
                "images": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "format": "uri"},
                            "description": {"type": "string"},
                            "caption": {"type": "string"}
                        },
                        "required": ["url"]
                    }
                },
                "embeds": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "platform": {"type": "string", "enum": ["youtube", "twitter", "instagram", "tiktok", "other"]},
                            "url": {"type": "string", "format": "uri"},
                            "embed_code": {"type": "string"},
                            "description": {"type": "string"}
                        },
                        "required": ["platform", "url"]
                    }
                }
            },
            "required": ["title", "content"]
        }

    instruction = """
        Extract structured article information as a SINGLE JSON OBJECT. Follow these rules:

        1. Main Content:
        - Title: The main article title
        - Publish Date: In ISO 8601 format (YYYY-MM-DD)
        - Content: Full text with paragraphs preserved

        2. Images:
        - For each image:
            * URL: Direct image source URL
            * Description: Based on alt text, caption, or surrounding context
            * Caption: Exact caption text if present

        3. Embeds:
        - Identify embedded content from: YouTube, Twitter, Instagram, TikTok
        - For each embed:
            * Platform: Social media platform name
            * URL: Direct link to original content
            * Embed Code: Full iframe/embed code if available
            * Description: Context from surrounding text explaining the embed

        4. Formatting:
        - Preserve original language and formatting
        - Exclude ads, comments, and non-article content
        - Maintain chronological order of content elements

        Example output format:
        {
            "title": "Article Title",
            "publish_date": "2023-12-31",
            "content": "Full article text...",
            "images": [
                {
                "url": "https://example.com/image1.jpg",
                "description": "A group of people working in a modern office",
                "caption": "Our team collaborating on new projects"
                }
            ],
            "embeds": [
                {
                "platform": "youtube",
                "url": "https://youtube.com/watch?v=XYZ123",
                "embed_code": "<iframe...></iframe>",
                "description": "Video tutorial demonstrating the new features"
                }
            ]
        }
    """

    async def scrape_article(self, url: str) -> Dict[str, Any]:
        """Extract article content with proxy rotation and retries"""
        last_error = None

        while self.current_attempt < self.max_retries:
            self.current_attempt += 1
            proxy = self.proxy_manager.get_random_proxy()

            try:
                # Configure browser with extended timeout settings
                browser_config = BrowserConfig(
                    headless=True,
                    proxy=proxy,
                    java_script_enabled=True,
                    ignore_https_errors=True
                )

                extractor = LLMExtractionStrategy(
                    provider="deepseek/deepseek-chat",
                    api_token=self.api_key,
                    schema=self.article_schema,
                    extraction_type="schema",
                    verbose=False,
                    instruction="""
                    Extract structured article information as a SINGLE JSON OBJECT. Rules:
                    1. Main article title
                    2. Publish date in ISO 8601
                    3. Full content with paragraphs
                    4. Relevant image URLs only
                    """,
                    chunk_token_threshold=3000,
                    overlap_rate=0.1,
                    extra_args={
                        "temperature": 0.2,
                        "max_tokens":  8192
                    }
                )

                run_config = CrawlerRunConfig(
                    extraction_strategy=extractor,
                    remove_overlay_elements=True,
                    cache_mode="bypass",
                    page_timeout=120000,  # 2 minutes timeout
                    wait_until="domcontentloaded",  # Less strict than networkidle
                    wait_for="body"  # Wait for at least body to load
                )

                print(colored(
                    f"\n🌀 Attempt {self.current_attempt}/{self.max_retries}",
                    "cyan",
                    attrs=["bold"]
                ))
                print(
                    f"   {Fore.YELLOW}Proxy:{Style.RESET_ALL} {proxy or 'none'}")
                print(f"   {Fore.YELLOW}URL:{Style.RESET_ALL} {url}")

                async with AsyncWebCrawler(config=browser_config) as crawler:
                    result = await crawler.arun(url=url, config=run_config)

                    if not result.success:
                        raise PlaywrightError(result.error_message)

                    # Enhanced validation
                    try:
                        raw_data = json.loads(result.extracted_content)
                        if not isinstance(raw_data, (dict, list)):
                            raise ValueError(
                                f"Unexpected response type: {type(raw_data)}")

                        article_data = self._validate_data_structure(raw_data)
                        self._save_result(article_data, url)
                        return article_data
                    except (json.JSONDecodeError, ValueError, TypeError) as e:
                        raise ValueError(
                            f"Data validation failed: {str(e)}") from e

            except PlaywrightError as e:
                last_error = e
                error_msg = str(e).lower()
                proxy_error = any([
                    'err_timed_out' in error_msg,
                    'err_tunnel_connection_failed' in error_msg,
                    'proxy' in error_msg
                ])

                if proxy and proxy_error:
                    print(
                        f"\n{Fore.RED}⚠️  Removing faulty proxy: {proxy}{Style.RESET_ALL}")
                    self.proxy_manager.remove_proxy(proxy)

                print(
                    colored(f"\n❌ Attempt {self.current_attempt} failed:", "red"))
                print(
                    f"   {Fore.YELLOW}Error:{Style.RESET_ALL} {error_msg[:120]}...")

            except (json.JSONDecodeError, ValueError, TypeError) as e:
                last_error = e
                print(colored(f"\n⚠️  Data parsing error:", "yellow"))
                print(
                    f"   {Fore.YELLOW}Details:{Style.RESET_ALL} {str(e)[:120]}...")
            except Exception as e:
                last_error = e
                print(colored(f"\n⚠️  Unexpected error:", "yellow"))
                print(
                    f"   {Fore.YELLOW}Details:{Style.RESET_ALL} {str(e)[:120]}...")

        print(colored(
            f"\n⛔️ Failed after {self.max_retries} attempts",
            "red",
            attrs=["bold"]
        ))
        print(
            f"{Fore.YELLOW}Last error:{Style.RESET_ALL} {str(last_error)[:200]}...")
        return {"error": str(last_error)}

    def _validate_data_structure(self, raw_data: Any) -> Dict[str, Any]:
        """Validate and normalize the extracted data"""
        if isinstance(raw_data, bool):
            raise ValueError(f"Unexpected boolean response: {raw_data}")

        if isinstance(raw_data, list):
            if not raw_data:
                raise ValueError("Empty array received")
            return raw_data[0]

        if not isinstance(raw_data, dict):
            raise ValueError(f"Unexpected data type: {type(raw_data)}")

        return raw_data

    def _save_result(self, data: Dict[str, Any], url: str):
        """Save results with metadata"""
        if not isinstance(data, dict):
            raise ValueError(f"Cannot save non-dictionary data: {type(data)}")

        Path("articles").mkdir(exist_ok=True)
        timestamp = datetime.now().isoformat(timespec='seconds')
        filename = f"article_{timestamp}.json"

        output = {
            "metadata": {
                "url": url,
                "extracted_at": timestamp,
                "proxy_used": self.proxy_manager.get_random_proxy() or "none"
            },
            "article": data
        }

        path = Path("articles") / filename
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(colored(f"\n💾 Results saved to: {path}", "green"))


async def main():
    parser = argparse.ArgumentParser(description="Article Content Extractor")
    parser.add_argument("--url", required=True,
                        help="URL to extract content from")
    parser.add_argument(
        "--proxy_file", help="File with HTTP proxies (ip:port)")
    parser.add_argument("--retries", type=int, default=3,
                        help="Max retry attempts")
    args = parser.parse_args()

    print("\n" + colored(" ARTICLE SCRAPER ", "white", "on_blue", attrs=["bold"]))
    print(colored(f"🔗 Target URL: {args.url}", "cyan"))
    print(colored(f"♻️  Max retries: {args.retries}", "cyan"))
    print(colored(f"🔒 Proxy file: {args.proxy_file or 'none'}\n", "cyan"))

    scraper = ArticleScraper(
        proxy_file=args.proxy_file,
        max_retries=args.retries
    )

    try:
        result = await scraper.scrape_article(args.url)

        # Modified error handling
        if isinstance(result, dict):
            if "error" in result and isinstance(result["error"], str):
                print(colored("\n⛔️ Extraction Failed", "red", attrs=["bold"]))
                print(f"{Fore.YELLOW}Error:{Style.RESET_ALL} {result['error'][:200]}...")
            else:
                print_success(result)  # Changed from self._print_success
        else:
            print(colored("\n⚠️  Invalid Result Format", "yellow"))
            print(f"Received unexpected type: {type(result)}")

    except Exception as e:
        print(colored("\n💀 Fatal Error:", "red", attrs=["bold"]))
        print(f"{Fore.YELLOW}Details:{Style.RESET_ALL} {str(e)[:200]}...")


# Add this standalone function outside any class
def print_success(result: dict):
    print("\n" + colored(" SUCCESSFUL EXTRACTION ", "white", "on_green", attrs=["bold"]))
    print(colored(f"📌 Title: ", "cyan") + f"{result.get('title', 'N/A')}")
    print(colored(f"📅 Date: ", "cyan") + f"{result.get('publish_date', 'Unknown')}")
    print(colored(f"📝 Content Preview: ", "cyan") + f"{result.get('content', '')[:200]}...")
    print(colored(f"🖼 Images Found: ", "cyan") + f"{len(result.get('images', []))}")
    print("\n" + "━" * 50)


if __name__ == "__main__":
    asyncio.run(main())
