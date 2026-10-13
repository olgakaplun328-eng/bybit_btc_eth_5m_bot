import logging
import os
import time
from datetime import datetime, timezone

import requests

API_URL = "https://api.bybit.com/v5/market/kline"
TELEGRAM_URL = "https://api.telegram.org/bot{}/sendMessage"

SYMBOLS = [
    s.strip().upper()
    for s in os.getenv("BYBIT_SYMBOLS", "BTCUSDT,ETHUSDT").split(",")
    if s.strip()
]

POLL_SECONDS = max(5, int(os.getenv("POLL_SECONDS", "10")))
TIMEFRAME_SECONDS = 300
TEST_MODE = os.getenv("TEST_MODE", "false").lower() in (
    "1", "true", "yes"
)
STATE_DIR = os.getenv("STATE_DIR", "/tmp/bybit_bot_state")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("bybit-bot")

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "bybit-alert-bot/1.0"})


def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning(
            "Telegram is not configured. Set TELEGRAM_BOT_TOKEN "
            "and TELEGRAM_CHAT_ID in Railway Variables."
        )
        return False

    url = TELEGRAM_URL.format(TELEGRAM_BOT_TOKEN)

    try:
        response = SESSION.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
            },
            timeout=15,
        )

        if not response.ok:
            log.warning(
                "TELEGRAM HTTP %s | BODY=%s",
                response.status_code,
                response.text[:1000],
            )
            response.raise_for_status()

        data = response.json()

        if not data.get("ok"):
            log.warning("Telegram API error: %s", data)
            return False

        log.info("Telegram message sent.")
        return True

    except requests.RequestException as exc:
        log.warning("Telegram network/API error: %s", exc)
        return False


def fetch_candles(symbol, limit=200):
    params = {
        "category": "linear",
        "symbol": symbol.replace("_", ""),
        "interval": "5",
        "limit": min(max(int(limit), 1), 1000),
    }

    response = SESSION.get(
        API_URL,
        params=params,
        timeout=15,
    )

    # Correct indentation: log the HTTP response before raising an error.
    if not response.ok:
        log.warning(
            "BYBIT HTTP %s | URL=%s | BODY=%s",
            response.status_code,
            response.url,
            response.text[:1000],
        )
        response.raise_for_status()

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"Bybit returned non-JSON response: "
            f"{response.text[:500]}"
        ) from exc

    if payload.get("retCode") != 0:
        raise RuntimeError(
            f"Bybit API error: retCode={payload.get('retCode')} "
            f"retMsg={payload.get('retMsg')}"
        )

    raw_candles = payload.get("result", {}).get("list", [])
    candles = []

    for item in raw_candles:
        try:
            candles.append({
                "ts": int(item[0]) // 1000,
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
            })
        except (IndexError, TypeError, ValueError):
            continue

    candles.sort(key=lambda candle: candle["ts"])

    # Exclude any candle whose 5-minute interval has not closed yet.
    now_ts = int(time.time())
    return [
        candle for candle in candles
        if candle["ts"] + TIMEFRAME_SECONDS <= now_ts
    ]


def candle_color(candle):
    if candle["close"] > candle["open"]:
        return "GREEN"
    if candle["close"] < candle["open"]:
        return "RED"
    return "DOJI"


def detect_pattern(candles):
    """RRR-GG => SHORT; GGG-RR => LONG."""
    if len(candles) < 5:
        return None

    colors = [candle_color(c) for c in candles[-5:]]

    if colors == ["RED", "RED", "RED", "GREEN", "GREEN"]:
        return "SHORT"

    if colors == ["GREEN", "GREEN", "GREEN", "RED", "RED"]:
        return "LONG"

    return None


def candle_time(ts):
    return datetime.fromtimestamp(
        ts, timezone.utc
    ).strftime("%Y-%m-%d %H:%M UTC")


def load_state():
    os.makedirs(STATE_DIR, exist_ok=True)
    state = {}

    for symbol in SYMBOLS:
        filename = os.path.join(STATE_DIR, f"{symbol}.txt")

        try:
            with open(filename, "r", encoding="utf-8") as file:
                state[symbol] = int(file.read().strip() or "0")
        except (OSError, ValueError):
            state[symbol] = 0

    return state


def save_state(symbol, timestamp):
    os.makedirs(STATE_DIR, exist_ok=True)
    filename = os.path.join(STATE_DIR, f"{symbol}.txt")

    with open(filename, "w", encoding="utf-8") as file:
        file.write(str(int(timestamp)))


def process_symbol(symbol, last_signal_ts):
    candles = fetch_candles(symbol, limit=200)

    if len(candles) < 5:
        log.info("%s: not enough closed candles.", symbol)
        return last_signal_ts

    last_five = candles[-5:]
    pattern_end_ts = last_five[-1]["ts"]

    if pattern_end_ts <= last_signal_ts:
        return last_signal_ts

    direction = detect_pattern(last_five)

    if direction is None:
        return last_signal_ts

    colors = " ".join(
        "🟢" if candle_color(c) == "GREEN"
        else "🔴" if candle_color(c) == "RED"
        else "⚪"
        for c in last_five
    )

    emoji = "🔴" if direction == "SHORT" else "🟢"

    message = (
        f"{emoji} {direction} — {symbol}\n"
        f"Pattern: {colors}\n"
        f"Timeframe: 5 minutes\n"
        f"Last candle closed: {candle_time(pattern_end_ts)}\n"
        f"Close price: {last_five[-1]['close']}\n"
        f"Alert only — no orders placed."
    )

    log.info(
        "%s: detected %s pattern (%s)",
        symbol, direction, colors
    )

    if TEST_MODE:
        log.info("TEST MODE preview:\n%s", message)
        send_telegram("[TEST MODE]\n" + message)
    else:
        send_telegram(message)

    save_state(symbol, pattern_end_ts)
    return pattern_end_ts


def main():
    log.info(
        "Starting Bybit 5m bot | symbols=%s | poll=%ss | TEST_MODE=%s",
        ",".join(SYMBOLS),
        POLL_SECONDS,
        TEST_MODE,
    )

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning(
            "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID "
            "in Railway Variables."
        )

    state = load_state()

    while True:
        for symbol in SYMBOLS:
            try:
                state[symbol] = process_symbol(
                    symbol,
                    state.get(symbol, 0),
                )
            except requests.RequestException as exc:
                log.warning(
                    "%s network/API error: %s",
                    symbol, exc
                )
            except Exception:
                log.exception("%s processing error", symbol)

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
