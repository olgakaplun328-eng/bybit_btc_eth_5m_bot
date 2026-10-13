import os
import time
import json
import logging
from collections import OrderedDict
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

load_dotenv()
SYMBOLS = [s.strip().upper().replace("_", "").replace("USDT", "_USDT") for s in os.getenv("BYBIT_SYMBOLS", "BTCUSDT,ETHUSDT").split(",") if s.strip()]
POLL_SECONDS = max(5, int(os.getenv("POLL_SECONDS", "10")))
TEST_MODE = os.getenv("TEST_MODE", "false").strip().lower() in ("1", "true", "yes", "on")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_IDS = [x.strip() for x in os.getenv("TELEGRAM_CHAT_ID", "").split(",") if x.strip()]
STATE_DIR = os.getenv("STATE_DIR", "state")
API_URL = "https://api.bybit.com/v5/market/kline"
TIMEFRAME_SECONDS = 5 * 60
TIMEFRAME_LABEL = "5m"

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("bybit-signal-bot-5m")
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Bybit-BTC-ETH-5m-Signal-Bot/1.0", "Cache-Control": "no-cache"})


def color(c):
    return "GREEN" if c["close"] > c["open"] else "RED" if c["close"] < c["open"] else "DOJI"


def emoji(c):
    return {"GREEN": "🟢", "RED": "🔴", "DOJI": "➖"}.get(c, "➖")


def kyiv(ts):
    return datetime.fromtimestamp(ts, tz=ZoneInfo("Europe/Kyiv")).strftime("%Y-%m-%d %H:%M")


def display_symbol(symbol):
    return symbol.replace("_USDT", "USDT")


def send(text):
    if TEST_MODE:
        print("\n--- TEST MESSAGE ---\n" + text + "\n--------------------")
        return True
    if not TOKEN or not CHAT_IDS:
        log.warning("Telegram is not configured; message was not sent: %s", text.replace("\n", " | "))
        return False
    ok = True
    for chat in CHAT_IDS:
        try:
            r = SESSION.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": chat, "text": text}, timeout=15)
            data = r.json()
            if not r.ok or not data.get("ok"):
                ok = False
                log.error("Telegram error for %s: %s", chat, r.text[:300])
        except Exception:
            ok = False
            log.exception("Telegram send failed for %s", chat)
    return ok


def parse_bybit_ts(value):
    ts = int(float(value))
    return ts // 1000 if ts > 10_000_000_000 else ts


def fetch_candles(symbol, limit=200):
    """Fetch native Bybit V5 linear-futures 5-minute candles."""
    api_symbol = symbol.replace("_", "")
    r = SESSION.get(API_URL, params={"category": "linear", "symbol": api_symbol, "interval": "5", "limit": limit}, timeout=15)
    if not r.ok:
    log.warning(
        "BYBIT HTTP %s | URL=%s | BODY=%s",
        r.status_code,
        r.url,
        r.text[:1000]
    )
    r.raise_for_status()
    payload = r.json()
    if payload.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error {payload.get('retCode')}: {payload.get('retMsg')}")
    raw = (payload.get("result") or {}).get("list") or []
    if not raw:
        raise RuntimeError(f"Bybit returned no kline data for {api_symbol}")
    now = int(time.time())
    by_ts = {}
    for row in raw:
        try:
            ts = parse_bybit_ts(row[0])
            by_ts[ts] = {"ts": ts, "open": float(row[1]), "close": float(row[4])}
        except (IndexError, TypeError, ValueError):
            continue
    rows = [by_ts[k] for k in sorted(by_ts)]
    closed = [c for c in rows if c["ts"] + TIMEFRAME_SECONDS <= now]
    live_rows = [c for c in rows if c["ts"] <= now < c["ts"] + TIMEFRAME_SECONDS]
    return closed[-150:], (live_rows[-1] if live_rows else None)


class Engine:
    def __init__(self, symbol):
        self.symbol = symbol
        os.makedirs(STATE_DIR, exist_ok=True)
        self.path = os.path.join(STATE_DIR, symbol + ".json")
        self.candles = OrderedDict()
        self.pre_sent = set()
        self.pending = []
        self.initialized = False

    def seed(self, history):
        self.candles = OrderedDict((c["ts"], c) for c in history[-150:])
        self.candles = OrderedDict(sorted(self.candles.items()))
        self.pending = []  # Avoid creating alerts for patterns that happened before startup.
        self.initialized = True
        self.save()
        log.info("%s initialized with %d closed 5m candles", self.symbol, len(self.candles))

    def save(self):
        state = {"last_closed_ts": next(reversed(self.candles), None) if self.candles else None, "pending": self.pending}
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, self.path)

    def pattern(self, block):
        cs = [color(c) for c in block]
        if cs == ["RED", "RED", "RED", "GREEN", "GREEN"]:
            return "SHORT"
        if cs == ["GREEN", "GREEN", "GREEN", "RED", "RED"]:
            return "LONG"
        return None

    def check_pre(self, live):
        if not self.initialized or live is None:
            return
        elapsed = time.time() - live["ts"]
        # PRE-ALERT during the final 60 seconds of candle #5.
        if elapsed < TIMEFRAME_SECONDS - 60 or elapsed >= TIMEFRAME_SECONDS:
            return
        ts = live["ts"]
        if ts in self.pre_sent:
            return
        first_ts = ts - 4 * TIMEFRAME_SECONDS
        block = [self.candles.get(first_ts + i * TIMEFRAME_SECONDS) for i in range(4)]
        if any(c is None for c in block):
            return
        direction = self.pattern(block + [live])
        if not direction:
            return
        self.pre_sent.add(ts)
        patt = "🔴🔴🔴🟢🟢" if direction == "SHORT" else "🟢🟢🟢🔴🔴"
        send(f"⚠️ PRE-ALERT\n{display_symbol(self.symbol)} Bybit Futures | 5m\n{patt}\nPotential: {direction}\nCandle #5 closes at {kyiv(ts + TIMEFRAME_SECONDS)} Kyiv time.")

    def add_closed(self, c):
        ts = c["ts"]
        self.candles[ts] = c
        self.candles = OrderedDict(sorted(self.candles.items()))
        keys = list(self.candles)
        if len(keys) >= 5 and keys[-1] == ts:
            block = [self.candles[k] for k in keys[-5:]]
            direction = self.pattern(block)
            if direction:
                self.pending.append({"start_ts": block[0]["ts"], "signal_ts": ts, "direction": direction})
                patt = "🔴🔴🔴🟢🟢" if direction == "SHORT" else "🟢🟢🟢🔴🔴"
                send(f"🔔 SIGNAL {direction}\n{display_symbol(self.symbol)} Bybit Futures | 5m\n{patt}\nPattern closed: {kyiv(ts + TIMEFRAME_SECONDS)} Kyiv time\nChecking candles #6–#11.")
                log.info("%s SIGNAL %s at %s", self.symbol, direction, kyiv(ts))

        keep = []
        for p in self.pending:
            if ts <= p["signal_ts"]:
                keep.append(p)
                continue
            rel = int((ts - p["signal_ts"]) // TIMEFRAME_SECONDS)  # rel=1 is candle #6; rel=6 is #11
            if rel < 1:
                keep.append(p)
                continue
            # Match the original strategy's outcome rule: SHORT wins on RED; LONG wins on GREEN.
            want = "RED" if p["direction"] == "SHORT" else "GREEN"
            if rel <= 6 and color(c) == want:
                send(f"✅ WIN\n{display_symbol(self.symbol)} Bybit Futures | 5m\nDirection: {p['direction']}\nMatching candle: #{rel + 5} {emoji(color(c))}\nSignal: {kyiv(p['start_ts'])} Kyiv time.")
                continue
            if rel >= 6:
                send(f"❌ LOSS\n{display_symbol(self.symbol)} Bybit Futures | 5m\nDirection: {p['direction']}\nNo matching candle appeared in candles #6–#11.")
                continue
            keep.append(p)
        self.pending = keep
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
            return
        last = next(reversed(self.candles), None) if self.candles else None
        new = [c for c in history if last is None or c["ts"] > last]
        if new:
            for c in new:
                self.add_closed(c)
        if live:
            self.check_pre(live)


def test():
    for seq in [
        ["RED", "RED", "RED", "GREEN", "GREEN", "RED", "GREEN", "GREEN", "GREEN", "GREEN"],
        ["GREEN", "GREEN", "GREEN", "RED", "RED", "GREEN", "RED", "RED", "RED", "RED"],
    ]:
        block = [{"open": 1.0, "close": 0.0 if x == "RED" else 2.0} for x in seq[:5]]
        e = Engine.__new__(Engine)
        direction = e.pattern(block)
        assert direction in ("SHORT", "LONG")
        want = "RED" if direction == "SHORT" else "GREEN"
        assert want in seq[5:10]
        print("PASS:", direction, "pattern", " ".join(emoji(x) for x in seq[:5]), "-> WIN")
    print("Offline pattern tests passed.")


def main():
    if TEST_MODE:
        test()
        return
    if not SYMBOLS:
        raise RuntimeError("BYBIT_SYMBOLS is empty; set it to BTCUSDT,ETHUSDT")
    engines = [Engine(s) for s in SYMBOLS]
    log.info("Started Bybit Futures signal bot for %s on 5m", ", ".join(SYMBOLS))
    log.info("Patterns: RRR-GG => SHORT; GGG-RR => LONG. Results: candles #6-#11.")
    if TOKEN and CHAT_IDS:
        send("🤖 Bybit 5m signal bot online\nSymbols: " + ", ".join(display_symbol(s) for s in SYMBOLS) + "\nSignal alerts only; no automatic orders.")
    while True:
        for engine in engines:
            try:
                engine.run_once()
            except requests.RequestException as ex:
                log.warning("%s network/API error: %s", engine.symbol, ex)
            except Exception:
                log.exception("%s error", engine.symbol)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
