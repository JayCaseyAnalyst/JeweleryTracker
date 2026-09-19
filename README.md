# Jared Ring Price Tracker 💍📉

An automated Python tool that monitors price changes for rings and jewelry on [Jared.com](https://www.jared.com/). It tracks historical prices in a local database (`price_history.json`) and instantly sends formatted price drop or all-time low alerts via a **Discord Webhook**.

---

## 🌟 Key Features

* **Anti-Bot Bypass:** Uses **Playwright** (Chromium) to execute JavaScript and bypass anti-bot protection.
* **Smart Parsing:** Leverages JSON-LD structured metadata fallback strategies with **BeautifulSoup** for precise price extraction.
* **Historical Tracking:** Tracks every price check in a JSON database and identifies:
  * 🥇 **All-Time Lowest Recorded Price**
  * 📉 Price Drops
  * 📈 Price Increases
  * 😶 Price Stability
* **Discord Alerts:** Sends clean, color-coded rich embeds directly to your Discord server via Webhooks.
* **Multi-SKU Support:** Scrapes multiple product SKUs sequentially with rate-limit delays.

---

## 🛠️ Prerequisites & Installation

### 1. Requirements
* **Python 3.10+**
* **Pip**

### 2. Clone the Repository
```bash
git clone [https://github.com/your-username/jared-price-tracker.git](https://github.com/your-username/jared-price-tracker.git)
cd jared-price-tracker
