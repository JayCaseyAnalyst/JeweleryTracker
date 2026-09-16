import asyncio
import json
import os
import re
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

URL = "https://www.jared.com/p/V-282350507"
DATA_FILE = "price_history.json"


async def fetch_page_html(url: str) -> str:
    """Fetch product page using Playwright to bypass Akamai blocking."""
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

        response = await page.goto(
            url, wait_until="domcontentloaded", timeout=60000
        )
        await page.wait_for_timeout(3000)

        html_content = await page.content()
        await browser.close()
        return html_content


def extract_price(html: str) -> float | None:
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
                    price = offers.get("price") or (
                        offers[0].get("price")
                        if isinstance(offers, list)
                        else None
                    )
                    if price:
                        return float(price)
            except (json.JSONDecodeError, TypeError, KeyError):
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


def load_history(filename: str) -> list[dict]:
    """Load existing price history from JSON file."""
    if os.path.exists(filename):
        try:
            with open(filename, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("Warning: JSON log file corrupted. Starting fresh history.")
    return []


def save_history(filename: str, history: list[dict]) -> None:
    """Save updated price history to JSON file."""
    with open(filename, "w") as f:
        json.dump(history, f, indent=4)


async def main():
    print(f"Fetching price for ring ({URL})...")
    html = await fetch_page_html(URL)
    current_price = extract_price(html)

    if current_price is None:
        print("Scraping failed.")
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    history = load_history(DATA_FILE)

    if history:
        last_entry = history[-1]
        previous_price = last_entry.get("price")
        lowest_price = previous_price

        # Search history for all-time lowest price
        for entry in history:
            entry_price = entry.get("price")
            if entry_price is not None and entry_price < lowest_price:
                lowest_price = entry_price

        print(f"\nPrevious recorded price: ${previous_price:,.2f}")
        print(f"Previous lowest price:   ${lowest_price:,.2f}")
        print(f"\nCurrent price:           ${current_price:,.2f}")

        # Your custom logic branch
        if current_price < lowest_price:
            difference = lowest_price - current_price
            print(
                f" BEST PRICE! The price is the best we've seen by ${difference:,.2f}. Now is the best time to buy!"
            )
        elif current_price < previous_price:
            difference = previous_price - current_price
            print(f" PRICE DROP! The price decreased by ${difference:,.2f}.")
        elif current_price > previous_price:
            difference = current_price - previous_price
            print(
                f" PRICE INCREASE! The price increased by ${difference:,.2f}."
            )
        else:
            print(" NO CHANGE: Price remains unchanged since last check.")
    else:
        print(f"\nInitial price recorded: ${current_price:,.2f}")

    # Append new entry to history log
    new_entry = {"timestamp": timestamp, "price": current_price}
    history.append(new_entry)
    save_history(DATA_FILE, history)
    print(f"Entry saved to {DATA_FILE}.\n")


if __name__ == "__main__":
    asyncio.run(main())