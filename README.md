# Bybit BTC/ETH 5m Telegram Signal Bot

Alerts only; this bot does not place orders.

- Source: Bybit V5 linear futures API
- Symbols: BTCUSDT and ETHUSDT
- Native timeframe: 5m
- Pattern: RRR → GG = SHORT; GGG → RR = LONG
- PRE-ALERT: during the last minute of candle #5 if the live pattern still matches
- SIGNAL: after candle #5 closes and confirms
- Result check: candles #6–#11 (inclusive)
- Telegram only; no automatic trades

## Railway variables
Set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `BYBIT_SYMBOLS=BTCUSDT,ETHUSDT`, `POLL_SECONDS=10`, `TEST_MODE=false`.
Start command: `python bot.py`.

Security: if a Telegram token was pasted into a chat, revoke it using @BotFather `/revoke` and use the replacement token as a Railway variable. Do not hard-code secrets in the source or ZIP.
