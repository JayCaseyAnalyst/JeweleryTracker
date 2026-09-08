import asyncio
from decimal import Decimal
from datetime import datetime
from playwright.async_api import async_playwright
from database import init_db, Product, PriceSnapshot
from parser import CatalogParser
from config import DATABASE_URL

TARGET_URL = "https://www.jared.com/wedding/c/7000001087?icid=SP_WED:HERO:ALL"

async def run_scraper():
    SessionLocal = init_db()
    db = SessionLocal()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        scraped_products = []

        async def handle_response(response):
            if "search" in response.url or "products" in response.url:
                if "application/json" in response.headers.get("content-type", ""):
                    try:
                        data = await response.json()
                        extracted = CatalogParser.parse_api_response(data)
                        scraped_products.extend(extracted)
                    except Exception:
                        pass

        page.on("response", handle_response)

        print(f"Navigating to target page...")
        await page.goto(TARGET_URL, wait_until="networkidle")

        for _ in range(3):
            await page.mouse.wheel(0, 1000)
            await page.wait_for_timeout(2000)

        if not scraped_products:
            html = await page.content()
            scraped_products = CatalogParser.parse_html_fallback(html)

        print(f"Extracted {len(scraped_products)} records. Committing to PostgreSQL...")

        # Bulk upsert and snapshot insertion
        try:
            for prod_data in scraped_products:
                # Upsert base product metadata if missing
                existing_product = db.query(Product).filter_by(sku=prod_data.sku).first()
                if not existing_product:
                    existing_product = Product(
                        sku=prod_data.sku,
                        title=prod_data.title,
                        url=prod_data.url,
                        description=prod_data.description
                    )
                    db.add(existing_product)
                
                # Convert floats to Decimal for PostgreSQL Numeric types
                price_decimal = Decimal(str(prod_data.current_price))
                orig_price_decimal = Decimal(str(prod_data.original_price)) if prod_data.original_price else None

                # Create time-series price point snapshot
                snapshot = PriceSnapshot(
                    sku=prod_data.sku,
                    price=price_decimal,
                    original_price=orig_price_decimal,
                    currency=prod_data.currency,
                    recorded_at=datetime.utcnow()
                )
                db.add(snapshot)

            db.commit()
            print("Successfully saved data to Postgres.")
        except Exception as e:
            db.rollback()
            print(f"Error during DB write: {e}")
        finally:
            db.close()

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_scraper())