import argparse
import asyncio
import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup

URL = "https://www.jared.com/p/"
DATA_FILE = "price_history.json"
DEFAULT_DELAY = 3.0

# Create default sku list from .txt
DEFAULT_SKUS: list = []
with open("Default_Skus.txt", "r", encoding="utf-8") as f:
            DEFAULT_SKUS.extend(line.strip() for line in f if line.strip())

# Webhook color values (Discord decimal RGB)
COLOR_ALL_TIME_LOW = 15844367  # Gold
COLOR_PRICE_DROP = 3066993     # Green
COLOR_PRICE_UP = 16711680      # Red
COLOR_NO_CHANGE = 808080       # Grey


def send_discord_alert(title: str, sku: str, description: str, color: int) -> None:
    """Sends a rich embed message to a Discord Webhook."""
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    url = URL + sku

    if not webhook_url:
        print(
            "Skipping Discord notification: DISCORD_WEBHOOK_URL environment variable missing."
        )
        return

    payload = {
        "username": "Jared Ring Tracker",
        "embeds": [
            {
                "title": title,
                "description": description,
                "url": url,
                "color": color,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }

    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
    )

    try:
        with urllib.request.urlopen(req) as response:
            if response.status in (200, 204):
                print("Discord notification sent successfully!")
    except Exception as e:
        print(f"Failed to send Discord alert: {e}")


async def fetch_page_html(url: str) -> str:
    """Fetch product page using Playwright to bypass Akamai blocking.

    Playwright is imported lazily so that the rest of the module (price
    extraction, history, alert logic) can be used and tested without a browser.
    """
    from playwright.async_api import async_playwright  # lazy: heavy optional dep

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
        )

        page = await context.new_page()

        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3000)

        html_content = await page.content()
        await browser.close()
        return html_content


def extract_price(html: str) -> Optional[float]:
    """Extract current price from rendered HTML using BeautifulSoup."""
    soup = BeautifulSoup(html, "html.parser")

    # Strategy 1: JSON-LD Structured Metadata
    scripts = soup.find_all("script", type="application/ld+json")
    for script in scripts:
        if script.string and '"price"' in script.string:
            try:
                data = json.loads(script.string)
                if isinstance(data, list):
                    data = data[0]

                if "offers" in data:
                    offers = data["offers"]
                    if isinstance(offers, list):
                        for offer in offers:
                            price = offer.get("price")
                            if price:
                                return float(price)
                    else:
                        price = offers.get("price")
                        if price:
                            return float(price)
            except (json.JSONDecodeError, TypeError, KeyError, ValueError):
                pass

    # Strategy 2: CSS / Regex Fallback
    price_tags = soup.find_all(class_=re.compile(r"price", re.I))
    for tag in price_tags:
        text = tag.get_text(strip=True)
        match = re.search(r"\$([\d,]+\.\d{2})", text)
        if match:
            return float(match.group(1).replace(",", ""))

    print("Could not locate price element on page.")
    return None


def load_history(filename: str) -> list:
    """Load existing price history from JSON file."""
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("Warning: JSON log file corrupted. Starting fresh history.")
    return []


def save_history(filename: str, history: list) -> None:
    """Save updated price history to JSON file."""
    parent = os.path.dirname(filename)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=4, ensure_ascii=False)


def _as_float(value) -> Optional[float]:
    """Coerce a history price to float, returning None for missing/invalid values."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class PriceDecision:
    """Result of comparing a current price against prior history."""

    kind: str  # one of: "new", "record_low", "drop", "increase", "stable"
    previous_price: Optional[float]
    lowest_price: Optional[float]
    current_price: float


def compute_decision(
    history: list, current_price: float, sku: str
) -> PriceDecision:
    """Compare a fresh price against an SKU's recorded history.

    Pure and synchronous — extracts the decision logic so it can be unit tested
    without network or browser access. Returns a PriceDecision describing
    whether this observation is a record low, a drop, an increase, unchanged,
    or the first record for the SKU.
    """
    sku_history = [e for e in history if e.get("sku") == sku]

    previous_price: Optional[float] = None
    lowest_price: Optional[float] = None

    if sku_history:
        previous_price = _as_float(sku_history[-1].get("price"))
        prices = [
            p
            for e in sku_history
            if (p := _as_float(e.get("price"))) is not None
        ]
        if prices:
            lowest_price = min(prices)

    if previous_price is None:
        return PriceDecision("new", previous_price, lowest_price, current_price)

    lowest = lowest_price if lowest_price is not None else previous_price
    if current_price < lowest:
        return PriceDecision("record_low", previous_price, lowest, current_price)
    if current_price < previous_price:
        return PriceDecision("drop", previous_price, lowest_price, current_price)
    if current_price > previous_price:
        return PriceDecision("increase", previous_price, lowest_price, current_price)
    return PriceDecision("stable", previous_price, lowest_price, current_price)


def build_alert_message(decision: PriceDecision, url: str) -> tuple:
    """Return a (title, description, color) Discord embed for a decision."""
    current = decision.current_price
    if decision.kind == "record_low":
        title = "🔥 All-Time Record Price Drop!"
        diff = decision.lowest_price - current
        desc = (
            f"**BEST PRICE EVER RECORDED!**\n\n"
            f"• **New Price:** `${current:,.2f}`\n"
            f"• **Savings Below Record Low:** `${diff:,.2f}`\n"
            f"• **Previous Record Low:** `${decision.lowest_price:,.2f}`\n\n"
            f"[Click here to buy on Jared]({url})"
        )
        return title, desc, COLOR_ALL_TIME_LOW
    if decision.kind == "drop":
        title = "📉 Ring Price Dropped!"
        diff = decision.previous_price - current
        desc = (
            f"**PRICE DROP DETECTED!**\n\n"
            f"• **New Price:** `${current:,.2f}`\n"
            f"• **Price Decreased By:** `${diff:,.2f}`\n"
            f"• **Previous Check Price:** `${decision.previous_price:,.2f}`\n"
            f"• **Record Low:** `${decision.lowest_price:,.2f}`\n\n"
            f"[Click here to view on Jared]({url})"
        )
        return title, desc, COLOR_PRICE_DROP
    if decision.kind == "increase":
        title = "😱 Ring Price Increase!"
        diff = current - decision.previous_price
        desc = (
            f"**PRICE INCREASE DETECTED!**\n\n"
            f"• **New Price:** `${current:,.2f}`\n"
            f"• **Price Increased By:** `${diff:,.2f}`\n"
            f"• **Previous Check Price:** `${decision.previous_price:,.2f}`\n"
            f"• **Record Low:** `${decision.lowest_price:,.2f}`\n\n"
            f"[Click here to view on Jared]({url})"
        )
        return title, desc, COLOR_PRICE_UP
    # stable
    title = "😶 Ring Price Stable."
    desc = (
        f"**NO CHANGE**\n\n"
        f"• **Current Price:** `${current:,.2f}`\n"
        f"• **Previous Record Low:** `${decision.lowest_price:,.2f}`\n\n"
        f"[Click here to buy on Jared]({url})"
    )
    return title, desc, COLOR_NO_CHANGE


async def compare_price(sku: str, notify: bool = True) -> None:
    """Fetch one SKU, compare against history, alert (optionally), and record it."""
    url = URL + sku
    print(f"Fetching price for ring ({url})...")
    html = await fetch_page_html(url)
    current_price = extract_price(html)

    if current_price is None:
        print("Scraping failed.")
        return

    full_history = load_history(DATA_FILE)
    decision = compute_decision(full_history, current_price, sku)

    if decision.kind == "new":
        print(f"\nInitial price recorded: ${current_price:,.2f}")
    else:
        print(f"\nPrevious recorded price: ${decision.previous_price:,.2f}")
        print(f"Previous lowest price:   ${decision.lowest_price:,.2f}")
        print(f"\nCurrent price:           ${current_price:,.2f}")

        if notify:
            title, desc, color = build_alert_message(decision, url)
            send_discord_alert(title, sku, desc, color)

    # Append new entry to history log
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_history.append({"timestamp": timestamp, "sku": sku, "price": current_price})
    save_history(DATA_FILE, full_history)
    print(f"Entry saved to {DATA_FILE}.\n")


def parse_skus(models_str: Optional[str], sku_file: Optional[str]) -> list:
    """Combine SKUs from --sku args and an optional --sku-file (one per line)."""
    skus: list = []
    if models_str:
        skus.extend(s.strip() for s in models_str.split(",") if s.strip())
    if sku_file:
        with open(sku_file, "r", encoding="utf-8") as f:
            skus.extend(line.strip() for line in f if line.strip())
    return skus


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jared-tracker",
        description="Monitor Jared.com ring prices and alert on drops, "
        "increases, and all-time record lows via Discord.",
    )
    parser.add_argument(
        "--sku",
        dest="models",
        help="Comma-separated SKUs to track (overrides the default list if brief).",
    )
    parser.add_argument(
        "--sku-file",
        help="Path to a file with one SKU per line.",
    )
    parser.add_argument(
        "--data-file",
        default=DATA_FILE,
        help=f"History JSON file (default: {DATA_FILE}).",
    )
    parser.add_argument(
        "--no-notify",
        action="store_true",
        help="Do not send Discord alerts; print comparisons to the console only.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help=f"Seconds to wait between SKUs (default: {DEFAULT_DELAY}).",
    )
    parser.add_argument(
        "--version", action="version", version="jared-tracker 1.1.0"
    )
    return parser


async def main(argv: Optional[list] = None) -> int:
    global DATA_FILE
    parser = build_parser()
    args = parser.parse_args(argv)

    skus = parse_skus(args.models, args.sku_file) or list(DEFAULT_SKUS)
    DATA_FILE = args.data_file

    for index, sku in enumerate(skus, 1):
        print(f"[{index}/{len(skus)}] Processing SKU: {sku}")
        try:
            await compare_price(sku=sku, notify=not args.no_notify)
        except Exception as e:
            print(f"Error processing SKU {sku}: {e}")

        # Wait between requests to avoid rate limits
        if index < len(skus):
            await asyncio.sleep(args.delay)

    print("All products processed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))


def cli() -> None:
    """Synchronous console-script entrypoint (wraps the async main)."""
    sys.exit(asyncio.run(main()))