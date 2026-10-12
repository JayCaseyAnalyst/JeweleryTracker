# Jared Ring Price Tracker 💍📉

An automated Python tool that monitors price changes for rings and jewelry on [Jared.com](https://www.jared.com/). It tracks historical prices in a local database (`price_history.json`) and sends formatted price drop or all-time low alerts via a **Discord Webhook**.

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

## 🛠️ Installation

### Requirements
* **Python 3.10+**
* **Pip**

### 1. Clone the Repository
```bash
git clone https://github.com/JayCaseyAnalyst/JeweleryTracker.git
cd JeweleryTracker
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Install Playwright Browsers
```bash
playwright install chromium
```

---

## 🚀 Usage

Run the tracker with the default SKU list:

```bash
python ring_tracker.py
```

### Command-line options

| Flag | Description |
| :--- | :--- |
| `--sku SKUS` | Comma-separated SKUs to track (overrides the default list). |
| `--sku-file PATH` | Read SKUs from a file, one per line. |
| `--data-file PATH` | History JSON to read/write (default: `price_history.json`). |
| `--no-notify` | Print price comparisons to the console only — do not send Discord alerts. |
| `--delay SECONDS` | Seconds to wait between SKUs (default: `3`). |
| `--version` | Print the version and exit. |

Examples:

```bash
# Track a specific SKU, no Discord alerts
python ring_tracker.py --sku V-282350507 --no-notify

# Track a batch of SKUs from a file, into a separate history
python ring_tracker.py --sku-file skus.txt --data-file my_history.json

# Installable console script (same flags)
jared-tracker --sku V-930843608 --no-notify
```

Set your webhook in the environment to enable alerts:

```bash
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
```

Run once a day with cron to catch price changes automatically.

---

## 🧪 Testing

Run the offline test suite (no browser or network required):

```bash
pip install pytest
pytest -v
```

The core logic — price extraction, price-history comparison (`compute_decision`), alert message generation, and history I/O — is extracted from the scraping code so it can be tested without a browser.

---

## 🤝 Contributing

Feel free to open issues or pull requests. The project is MIT licensed.

📜 License
This project is open-source and distributed under the MIT License.