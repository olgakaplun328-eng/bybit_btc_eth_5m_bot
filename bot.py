import json
import logging
import os
import time
from collections import OrderedDict
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

load_dotenv()


def normalize_symbol(value):
    value = value.strip().upper().replace("/", "").replace("_", "").replace("-", "")
    if not value:
        return ""
    if not value.endswith("USDT"):
        value += "USDT"
    return value


SYMBOLS = [normalize_symbol(s) for s in os.getenv("BINANCE_SYMBOLS", "BTCUSDT,ETHUSDT").split(",")]
SYMBOLS = list(dict.fromkeys(s for s in SYMBOLS if s))
POLL_SECONDS = max(5, int(os.getenv("POLL_SECONDS", "10")))
TEST_MODE = os.getenv("TEST_MODE", "false").strip().lower() in ("1", "true", "yes", "on")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_IDS = [x.strip() for x in os.getenv("TELEGRAM_CHAT_ID", "").split(",") if x.strip()]
STATE_DIR = os.getenv("STATE_DIR", "state")
TIMEFRAME_SECONDS = 300
TIMEFRAME_LABEL = "5m"

API_URL = os.getenv("BINANCE_FUTURES_API_URL", "https://fapi.binance.com/fapi/v1/klines").strip()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("binance-futures-signal-bot-5m")
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; BinanceFuturesSignalBot/1.0)",
    "Accept": "application/json",
    "Cache-Control": "no-cache",
})


def candle_color(candle):
    if candle["close"] > candle["open"]:
        return "GREEN"
    if candle["close"] < candle["open"]:
        return "RED"
    return "DOJI"


def emoji(value):
    return {"GREEN": "🟢", "RED": "🔴", "DOJI": "➖"}.get(value, "➖")


def kyiv(ts):
    return datetime.fromtimestamp(ts, tz=ZoneInfo("Europe/Kyiv")).strftime("%Y-%m-%d %H:%M")


def display_symbol(symbol):
    return symbol


def send(message):
    if TEST_MODE:
        print("\n--- TEST MESSAGE ---\n" + message + "\n--------------------")
        return True
    if not TOKEN or not CHAT_IDS:
        log.warning("Telegram is not configured; message not sent: %s", message.replace("\n", " | "))
        return False
    success = True
    for chat_id in CHAT_IDS:
        try:
            response = SESSION.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": message},
                timeout=15,
            )
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            if not response.ok or not payload.get("ok"):
                success = False
                log.error("Telegram HTTP %s for chat %s: %s", response.status_code, chat_id, response.text[:300])
        except requests.RequestException:
            success = False
            log.exception("Telegram request failed for chat %s", chat_id)
    return success


def parse_binance_ts(value):
    """Binance kline open times are Unix timestamps in milliseconds."""
    return int(value) // 1000


def fetch_candles(symbol, limit=200):
    """Fetch public Binance USDⓈ-M Futures 5m klines (no API key required)."""
    try:
        response = SESSION.get(
            API_URL,
            params={"symbol": symbol, "interval": "5m", "limit": limit},
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        body = getattr(getattr(exc, "response", None), "text", "")[:500]
        raise RuntimeError(f"Binance Futures request failed for {symbol}: {exc}; body={body}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"Binance returned non-JSON for {symbol}: {response.text[:250]}") from exc
    if not isinstance(payload, list) or not payload:
        raise RuntimeError(f"Binance returned no klines for {symbol}: {str(payload)[:250]}")

    now = int(time.time())
    rows = []
    for row in payload:
        try:
            rows.append({"ts": parse_binance_ts(row[0]), "open": float(row[1]), "close": float(row[4])})
        except (IndexError, TypeError, ValueError):
            continue
    rows.sort(key=lambda candle: candle["ts"])
    closed = [c for c in rows if c["ts"] + TIMEFRAME_SECONDS <= now]
    live_rows = [c for c in rows if c["ts"] <= now < c["ts"] + TIMEFRAME_SECONDS]
    log.debug("Fetched %d closed Binance Futures candles for %s", len(closed), symbol)
    return closed[-150:], (live_rows[-1] if live_rows else None)


class Engine:
    def __init__(self, symbol):
        self.symbol = symbol
        os.makedirs(STATE_DIR, exist_ok=True)
        self.path = os.path.join(STATE_DIR, f"{symbol}.json")
        self.candles = OrderedDict()
        self.pre_sent = set()
        self.pending = []
        self.initialized = False

    def load_state(self):
        try:
            with open(self.path, "r", encoding="utf-8") as file:
                state = json.load(file)
            pending = state.get("pending", [])
            if isinstance(pending, list):
                self.pending = [p for p in pending if p.get("direction") in ("LONG", "SHORT") and "signal_ts" in p]
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError) as exc:
            log.warning("Could not read state for %s; starting clean: %s", self.symbol, exc)

    def save(self):
        state = {
            "last_closed_ts": next(reversed(self.candles), None) if self.candles else None,
            "pending": self.pending,
        }
        temporary_path = self.path + ".tmp"
        with open(temporary_path, "w", encoding="utf-8") as file:
            json.dump(state, file, indent=2)
        os.replace(temporary_path, self.path)

    @staticmethod
    def pattern(block):
        colors = [candle_color(c) for c in block]
        if colors == ["RED", "RED", "RED", "GREEN", "GREEN"]:
            return "SHORT"
        if colors == ["GREEN", "GREEN", "GREEN", "RED", "RED"]:
            return "LONG"
        return None

    def seed(self, history):
        self.load_state()
        self.candles = OrderedDict((c["ts"], c) for c in history[-150:])
        self.candles = OrderedDict(sorted(self.candles.items()))
        self.initialized = True
        self.save()
        log.info("%s initialized with %d closed 5m candles; restored %d pending result(s)", self.symbol, len(self.candles), len(self.pending))

    def check_pre(self, live):
        if not self.initialized or live is None:
            return
        elapsed = time.time() - live["ts"]
        # PRE-ALERT is eligible only in the final 60 seconds of candle #5.
        if elapsed < TIMEFRAME_SECONDS - 60 or elapsed >= TIMEFRAME_SECONDS:
            return
        candle_ts = live["ts"]
        if candle_ts in self.pre_sent:
            return
        first_ts = candle_ts - 4 * TIMEFRAME_SECONDS
        previous = [self.candles.get(first_ts + i * TIMEFRAME_SECONDS) for i in range(4)]
        if any(c is None for c in previous):
            return
        direction = self.pattern(previous + [live])
        if direction is None:
            return
        self.pre_sent.add(candle_ts)
        pattern_text = "🔴🔴🔴🟢🟢" if direction == "SHORT" else "🟢🟢🟢🔴🔴"
        send(
            f"⚠️ PRE-ALERT\n{self.symbol} Binance Futures | 5m\n{pattern_text}\n"
            f"Potential: {direction}\nCandle #5 closes at {kyiv(candle_ts + TIMEFRAME_SECONDS)} Kyiv time."
        )

    def add_closed(self, candle):
        ts = candle["ts"]
        if ts in self.candles:
            return
        self.candles[ts] = candle
        self.candles = OrderedDict(sorted(self.candles.items()))
        keys = list(self.candles)

        # Signal only after candle #5 has fully closed.
        if len(keys) >= 5 and keys[-1] == ts:
            block = [self.candles[k] for k in keys[-5:]]
            direction = self.pattern(block)
            if direction:
                self.pending.append({"start_ts": block[0]["ts"], "signal_ts": ts, "direction": direction})
                pattern_text = "🔴🔴🔴🟢🟢" if direction == "SHORT" else "🟢🟢🟢🔴🔴"
                send(
                    f"🔔 SIGNAL {direction}\n{self.symbol} Binance Futures | 5m\n{pattern_text}\n"
                    f"Pattern closed: {kyiv(ts + TIMEFRAME_SECONDS)} Kyiv time\nChecking candles #6–#11."
                )
                log.info("%s SIGNAL %s at %s", self.symbol, direction, kyiv(ts))

        remaining = []
        for pending in self.pending:
            if ts <= pending["signal_ts"]:
                remaining.append(pending)
                continue
            elapsed_candles = (ts - pending["signal_ts"]) // TIMEFRAME_SECONDS
            if elapsed_candles < 1:
                remaining.append(pending)
                continue
            expected = "RED" if pending["direction"] == "SHORT" else "GREEN"
            actual = candle_color(candle)
            # Evaluate #6 through #11 inclusive; a matching #11 is still a WIN.
            if actual == expected:
                send(
                    f"✅ WIN\n{self.symbol} Binance Futures | 5m\nDirection: {pending['direction']}\n"
                    f"Matching candle: #{elapsed_candles + 5} {emoji(actual)}\n"
                    f"Signal: {kyiv(pending.get('start_ts', pending['signal_ts']))} Kyiv time."
                )
                continue
            if elapsed_candles >= 6:
                send(
                    f"❌ LOSS\n{self.symbol} Binance Futures | 5m\nDirection: {pending['direction']}\n"
                    "No matching candle appeared in candles #6–#11."
                )
                continue
            remaining.append(pending)
        self.pending = remaining
        while len(self.candles) > 150:
            self.candles.popitem(last=False)
        self.save()

    def run_once(self):
        history, live = fetch_candles(self.symbol)
        if not history:
            log.warning("%s: no complete closed 5m candles received", self.symbol)
            return
        if not self.initialized:
            self.seed(history)
            if live:
                self.check_pre(live)
            return
        last_ts = next(reversed(self.candles), None) if self.candles else None
        new_candles = [c for c in history if last_ts is None or c["ts"] > last_ts]
        for candle in new_candles:
            self.add_closed(candle)
        if live:
            self.check_pre(live)


def test():
    cases = [
        (["RED", "RED", "RED", "GREEN", "GREEN"], "SHORT"),
        (["GREEN", "GREEN", "GREEN", "RED", "RED"], "LONG"),
        (["RED", "RED", "GREEN", "GREEN", "GREEN"], None),
        (["GREEN", "GREEN", "GREEN", "RED", "DOJI"], None),
    ]
    for colors, expected in cases:
        candles = [{"open": 1.0, "close": (0.0 if color == "RED" else 2.0 if color == "GREEN" else 1.0)} for color in colors]
        actual = Engine.pattern(candles)
        assert actual == expected, (colors, expected, actual)
        print("PASS pattern", "".join(emoji(c) for c in colors), "->", actual)

    def outcome(direction, colors):
        wanted = "RED" if direction == "SHORT" else "GREEN"
        for index, actual in enumerate(colors, start=6):
            if actual == wanted:
                return "WIN", index
        return "LOSS", 11

    assert outcome("SHORT", ["GREEN"] * 5 + ["RED"]) == ("WIN", 11)
    assert outcome("LONG", ["RED"] * 6) == ("LOSS", 11)
    assert outcome("LONG", ["GREEN"] + ["RED"] * 5) == ("WIN", 6)
    assert outcome("SHORT", ["RED"] + ["GREEN"] * 5) == ("WIN", 6)
    print("PASS result window: checks #6–#11, WIN on #11, LOSS only after #11")
    print("All offline tests passed.")


def main():
    if TEST_MODE:
        test()
        return
    if not SYMBOLS:
        raise RuntimeError("BINANCE_SYMBOLS is empty; set it to BTCUSDT,ETHUSDT")
    engines = [Engine(symbol) for symbol in SYMBOLS]
    log.info("Started Binance Futures signal bot for %s on native 5m candles", ", ".join(SYMBOLS))
    log.info("Patterns: 🔴🔴🔴🟢🟢 => SHORT; 🟢🟢🟢🔴🔴 => LONG; result window #6–#11")
    if TOKEN and CHAT_IDS:
        send("🤖 Binance Futures 5m signal bot online\nSymbols: " + ", ".join(SYMBOLS) + "\nAlerts only — no automatic orders.")
    while True:
        for engine in engines:
            try:
                engine.run_once()
            except Exception as exc:
                log.error("%s loop error: %s", engine.symbol, exc, exc_info=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
