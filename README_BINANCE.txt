BINANCE USDⓈ-M FUTURES 5m TELEGRAM SIGNAL BOT

Included files (5):
1. bot.py — bot source code
2. requirements.txt — Python dependencies
3. Procfile — process start command
4. railway.json — Railway build/deploy configuration
5. README_BINANCE.txt — setup instructions

DATA SOURCE
Public Binance USDⓈ-M Futures REST klines: https://fapi.binance.com/fapi/v1/klines
Native 5-minute candles (interval=5m); public candles do not require a Binance API key.

RAILWAY SETUP
1. Upload/extract these five files into your project/repository.
2. Railway will use the Procfile command `python bot.py`; alternatively set Start Command to `python bot.py`.
3. Add these Railway Variables:
   TELEGRAM_BOT_TOKEN = your Telegram bot token
   TELEGRAM_CHAT_ID = your Telegram chat ID (or comma-separated IDs)
   BINANCE_SYMBOLS = BTCUSDT,ETHUSDT
   TEST_MODE = false
   POLL_SECONDS = 10 (optional)
4. Deploy and inspect logs for startup/errors.

SIGNAL RULES
- 🔴🔴🔴🟢🟢 => SHORT
- 🟢🟢🟢🔴🔴 => LONG
- PRE-ALERT during the last 60 seconds of candle #5, if the pattern is present.
- SIGNAL after candle #5 closes.
- WIN if the expected-color candle appears in candles #6–#11; otherwise LOSS after #11 closes.
- Telegram alerts only; the bot does not place orders.
- Timestamps are displayed in Europe/Kyiv time.

TEST
Set TEST_MODE=true and run `python bot.py` to run offline rule tests and exit. This test does not contact Binance or Telegram. Set TEST_MODE=false for live monitoring.

Optional: BINANCE_FUTURES_API_URL can override the public kline endpoint.
