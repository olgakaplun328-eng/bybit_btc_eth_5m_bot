MEXC FUTURES 5m TELEGRAM SIGNAL BOT

Data source: MEXC perpetual futures public K-line API (Min5).
Endpoint: https://api.mexc.com/api/v1/contract/kline/{symbol}
No exchange API key is needed for public candles. This bot sends alerts only; it does not place orders.

Railway setup
1. Upload this ZIP / place the five files in your Railway project.
2. Start command: python bot.py
3. Add variables:
   TELEGRAM_BOT_TOKEN = your Telegram bot token
   TELEGRAM_CHAT_ID = your chat ID (multiple IDs may be comma-separated)
   MEXC_SYMBOLS = BTCUSDT,ETHUSDT
   TEST_MODE = false
   POLL_SECONDS = 10   (optional)

Symbol names are automatically converted to MEXC contract format (BTC_USDT, ETH_USDT).

Rules
- 🔴🔴🔴🟢🟢 => SHORT
- 🟢🟢🟢🔴🔴 => LONG
- PRE-ALERT during the final minute of candle #5
- SIGNAL after candle #5 closes
- WIN if the expected-color candle appears in candles #6–#11; otherwise LOSS after #11 closes
- Display times use Europe/Kyiv

For offline logic checks set TEST_MODE=true and run: python bot.py
Note: endpoint access must be confirmed from your Railway deployment; access may vary by hosting region/network.
