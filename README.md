# Bybit BTC/ETH 5m Telegram Signal Bot

Telegram alerts only. This project does **not** place or manage orders.

## Rules implemented
- Market data: Bybit V5 **linear futures** API, native 5-minute candles.
- Symbols by default: `BTCUSDT` and `ETHUSDT`.
- `🔴🔴🔴🟢🟢` → `SIGNAL SHORT` after candle #5 closes.
- `🟢🟢🟢🔴🔴` → `SIGNAL LONG` after candle #5 closes.
- `PRE-ALERT` can be sent during the last 60 seconds of candle #5 if the pattern currently matches. The live candle can change before close, so PRE-ALERT is not a confirmed signal.
- Outcome window: candles #6 through #11 inclusive. SHORT wins on a red candle; LONG wins on a green candle. A matching candle #11 is a WIN; otherwise LOSS is sent after #11 closes.
- Uses Kyiv local time in messages.
- Logs HTTP status and response snippets, and tries `api.bytick.com` first and falls back to `api.bybit.com`. This fallback may not overcome every hosting-region/network restriction.
- Saves pending signal outcomes in `state/` so they can survive process restarts.

## Run locally
1. Install Python 3.10+.
2. Install dependencies: `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and enter your Telegram bot token and chat ID.
4. Run tests: `TEST_MODE=true python bot.py` (Windows PowerShell: `$env:TEST_MODE='true'; python bot.py`).
5. For live alerts, set `TEST_MODE=false` and run `python bot.py`.

## Deploy to Railway
1. Upload the project to your own GitHub repository and connect it to Railway, or deploy the ZIP contents using your usual Railway workflow.
2. Set these Railway Variables:
   - `TELEGRAM_BOT_TOKEN` = token from BotFather
   - `TELEGRAM_CHAT_ID` = target chat/group ID (comma-separated IDs are supported)
   - `BYBIT_SYMBOLS` = `BTCUSDT,ETHUSDT`
   - `POLL_SECONDS` = `10`
   - `TEST_MODE` = `false`
3. Start command: `python bot.py`.
4. Check Railway logs. The bot tries `api.bytick.com` first and then `api.bybit.com`; it logs each endpoint, request URL, HTTP status, and response body snippet. You can override the first endpoint using `BYBIT_API_URL`. If both return 403, the Railway network/region may be blocked; changing code alone cannot guarantee access.

## Security
- Never hard-code Telegram tokens in `bot.py` or commit `.env`.
- If a token has ever been pasted into a chat or public log, revoke it with `@BotFather` and set the replacement only in Railway Variables.
