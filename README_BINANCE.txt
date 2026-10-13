BINANCE FUTURES 5m TELEGRAM SIGNAL BOT

Files:
- bot.py
- requirements.txt

Railway setup:
1. Upload these files to your project/repository.
2. Set Start Command to: python bot.py
3. Set Railway Variables:
   TELEGRAM_BOT_TOKEN = your Telegram bot token
   TELEGRAM_CHAT_ID = your chat ID (or comma-separated IDs)
   BINANCE_SYMBOLS = BTCUSDT,ETHUSDT
   TEST_MODE = false
   POLL_SECONDS = 10   (optional)

Data source:
Public Binance USDⓈ-M Futures REST klines endpoint:
https://fapi.binance.com/fapi/v1/klines
Uses native 5m candles; no Binance API key is needed for public candle data.
Optional variable BINANCE_FUTURES_API_URL can override the endpoint.

Rules:
- RED RED RED GREEN GREEN => SHORT
- GREEN GREEN GREEN RED RED => LONG
- PRE alert during the final 60 seconds of candle #5, when the pattern is present.
- SIGNAL after candle #5 closes.
- WIN if expected-color candle appears in candles #6-#11; otherwise LOSS after #11 closes.
- Telegram alerts only; no orders are placed.
- Display times use Europe/Kyiv.

Offline rule test:
Set TEST_MODE=true and run `python bot.py`. This runs local logic tests and exits; it does not contact Binance or Telegram.
