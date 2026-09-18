import asyncio
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

URL = "https://www.jared.com/p/"
DATA_FILE = "price_history.json"

def send_discord_alert(title: str, sku: str, description: str, color: int):
    """Sends a rich embed message to a Discord Webhook."""
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    
    if not webhook_url:
        print("Skipping Discord notification: DISCORD_WEBHOOK_URL environment variable missing.")
        return

    payload = {
        "username": "Jared Ring Tracker",
        "embeds": [
            {
                "title": title,
                "description": description,
                "url": sku,
                "color": color,  # Integer color value (e.g., Green = 3066993, Gold = 15844367)
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

async def compare_price(sku: str, notify: bool = True) -> None:
    if sku is None: 
        return
    URL = "https://www.jared.com/p/" + sku
    print(f"Fetching price for ring ({URL})...")
    html = await fetch_page_html(URL)
    current_price = extract_price(html)

    if current_price is None:
        print("Scraping failed.")
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_history = load_history(DATA_FILE)

    history = [
        entry for entry in full_history if entry.get("sku") == sku
    ]

    if history:
        last_entry = history[-1]
        previous_price = last_entry.get("price")
        lowest_price = previous_price

        # Search history for all-time lowest price
        for entry in history:
            entry_price = entry.get("price")
            if entry_price is not None and entry_price < lowest_price:
                lowest_price = entry_price


        if notify:
            # Your custom logic branch
            if current_price < lowest_price:
                difference = lowest_price - current_price
                desc = (
                    f"**BEST PRICE EVER RECORDED!**\n\n"
                    f"• **New Price:** `${current_price:,.2f}`\n"
                    f"• **Savings Below Record Low:** `${difference:,.2f}`\n"
                    f"• **Previous Record Low:** `${lowest_price:,.2f}`\n\n"
                    f"[Click here to buy on Jared]({URL})"
                )
                send_discord_alert("🔥 All-Time Record Price Drop!", URL, desc, color=15844367)  # Gold
            elif current_price < previous_price:
                difference = previous_price - current_price
                desc = (
                    f"**PRICE DROP DETECTED!**\n\n"
                    f"• **New Price:** `${current_price:,.2f}`\n"
                    f"• **Price Decreased By:** `${difference:,.2f}`\n"
                    f"• **Previous Check Price:** `${previous_price:,.2f}`\n"
                    f"• **Record Low:** `${lowest_price:,.2f}`\n\n"
                    f"[Click here to view on Jared]({URL})"
                )
                send_discord_alert("📉 Ring Price Dropped!", URL, desc, color=3066993)  # Green
            elif current_price > previous_price:
                difference = (current_price - previous_price)
                desc = (
                    f"**PRICE INCREASE DETECTED!**\n\n"
                    f"• **New Price:** `${current_price:,.2f}`\n"
                    f"• **Price Increased By:** `${difference:,.2f}`\n"
                    f"• **Previous Check Price:** `${previous_price:,.2f}`\n"
                    f"• **Record Low:** `${lowest_price:,.2f}`\n\n"
                    f"[Click here to view on Jared]({URL})"
                )
                send_discord_alert("😱 Ring Price Increase!", URL, desc, color=16711680)  # Red
            elif current_price == previous_price:
                desc = (
                    f"**NO CHANGE**\n\n"
                    f"• **Current Price:** `${current_price:,.2f}`\n"
                    f"• **Previous Record Low:** `${lowest_price:,.2f}`\n\n"
                    f"[Click here to buy on Jared]({URL})"
                )
                send_discord_alert("😶 Ring Price Stable.", URL, desc, color=808080)  # Grey
            else:
                print(" NO CHANGE: Price remains unchanged since last check.")
        else:
            print(f"\nPrevious recorded price: ${previous_price:,.2f}")
            print(f"Previous lowest price:   ${lowest_price:,.2f}")
            print(f"\nCurrent price:           ${current_price:,.2f}")

        
    else:
        print(f"\nInitial price recorded: ${current_price:,.2f}")

    # Append new entry to history log
    new_entry = {"timestamp": timestamp, "sku": sku, "price": current_price}
    full_history.append(new_entry)
    save_history(DATA_FILE, full_history)
    print(f"Entry saved to {DATA_FILE}.\n")


async def main():
    PRODUCTS = [
    "V-282350507",
    "V-930843608",  # Add additional SKUs here
    "V-780031009",
    ]

    for index, sku in enumerate(PRODUCTS, 1):
        print(f"[{index}/{len(PRODUCTS)}] Processing SKU: {sku}")
        try:
            await compare_price(sku=sku, notify=True)
        except Exception as e:
            print(f"Error processing SKU {sku}: {e}")

        # Wait 3 seconds between requests to avoid rate limits
        if index < len(PRODUCTS):
            await asyncio.sleep(3)

    print("All products processed successfully.")
        


if __name__ == "__main__":
    asyncio.run(main())