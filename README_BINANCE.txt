Binance USDⓈ-M Futures 5m signal bot (alerts only)

Railway Variables:
- TELEGRAM_BOT_TOKEN = your Telegram bot token
- TELEGRAM_CHAT_ID = your Telegram chat ID (or comma-separated IDs)
- BINANCE_SYMBOLS = BTCUSDT,ETHUSDT
- POLL_SECONDS = 10 (optional)
- TEST_MODE = false

Start command: python bot.py

Market data source:
https://fapi.binance.com/fapi/v1/klines
Public candles only; no Binance API key is needed for this endpoint.

Rules unchanged:
- RED RED RED GREEN GREEN => SHORT
- GREEN GREEN GREEN RED RED => LONG
- PRE alert during the last 60 seconds of candle #5
- SIGNAL after candle #5 closes
- WIN/LOSS evaluated over candles #6 through #11
- No orders are placed.

Set TEST_MODE=true to run offline logic tests only. It exits after tests and does not run the bot loop.
