import os
import requests
from flask import Flask
from live_simulator import LivePaperEngine

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = "8849431477:AAGVNZett1gWBikPg6fWJ4p2CJhQJxWEaaw"
TELEGRAM_CHAT_ID = "7106069536"
WATCHLIST = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "PAXGUSDT"]

def send_telegram_msg(msg: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception:
        pass

class PrecisionSniperBrain:
    def get_klines(self, symbol, interval="15m", limit=35):
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        try:
            res = requests.get(url, timeout=5).json()
            closes = [float(k[4]) for k in res]
            volumes = [float(k[5]) for k in res]
            return closes, volumes
        except Exception:
            return [], []

    def calculate_rsi(self, prices, period=14):
        if len(prices) < period + 1: return 50.0
        gains, losses = [], []
        for i in range(1, len(prices)):
            diff = prices[i] - prices[i - 1]
            gains.append(diff if diff > 0 else 0)
            losses.append(abs(diff) if diff < 0 else 0)
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0: return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def calculate_ema(self, prices, period):
        if len(prices) < period: return prices[-1]
        k = 2 / (period + 1)
        ema = prices[0]
        for p in prices[1:]:
            ema = (p * k) + (ema * (1 - k))
        return ema

    def scan_sniper_setups(self):
        opportunities = []
        market_intel = []
        for symbol in WATCHLIST:
            closes, volumes = self.get_klines(symbol)
            if len(closes) < 20: continue
            
            current_price = closes[-1]
            rsi = self.calculate_rsi(closes, period=14)
            ema_fast = self.calculate_ema(closes, period=9)
            ema_slow = self.calculate_ema(closes, period=21)
            vol_avg = sum(volumes[-10:]) / 10 if volumes else 1.0
            vol_spike = volumes[-1] > (vol_avg * 1.2) if volumes else False

            market_intel.append(f"{symbol}: ${current_price:,.2f} (RSI: {rsi:.1f})")

            if rsi < 35 and current_price > closes[-2]:
                opportunities.append({
                    "asset": symbol, "direction": "BUY",
                    "catalyst": f"🎯 اقتناص ارتداد (RSI={rsi:.1f})", "weight": 0.12
                })
            elif ema_fast > ema_slow and closes[-2] <= ema_slow and (vol_spike or rsi > 50):
                opportunities.append({
                    "asset": symbol, "direction": "BUY",
                    "catalyst": f"⚡ اختراق صاعد (RSI={rsi:.1f})", "weight": 0.15
                })
        return opportunities, market_intel

try:
    engine = LivePaperEngine(initial_balance=100.0)
except Exception:
    engine = None

sniper = PrecisionSniperBrain()
ping_count = 0

@app.route('/')
def home():
    global ping_count, engine
    if not engine: return "Engine Error", 500

    try:
        # حماية من الخطأ: التأكد من وجود الدالة قبل استدعائها
        if hasattr(engine, 'check_open_positions'):
            engine.check_open_positions(send_telegram_msg)
        elif hasattr(engine, 'update_positions'):
            engine.update_positions(send_telegram_msg)

        setups, intel = sniper.scan_sniper_setups()
        for setup in setups:
            if hasattr(engine, 'execute_simulated_trade'):
                engine.execute_simulated_trade(
                    asset=setup["asset"], weight=setup["weight"],
                    catalyst=setup["catalyst"], notifier=send_telegram_msg
                )

        ping_count += 1
        if ping_count % 6 == 0:
            text = "\n".join([f"• {x}" for x in intel])
            # حماية قراءة الرصيد
            bal = engine.balance if hasattr(engine, 'balance') else 100.0
            pos_len = len(engine.open_positions) if hasattr(engine, 'open_positions') else 0
            
            send_telegram_msg(
                f"⏱️ تقرير القناص (كل 30 دقيقة):\n"
                f"الرصيد: ${bal:.2f}\n"
                f"الصفقات المفتوحة: {pos_len}\n\n"
                f"📊 نبض الأسواق:\n{text}"
            )
        return "OK", 200
    except Exception as e:
        send_telegram_msg(f"⚠️ خطأ غير متوقع: {str(e)}")
        return "Error", 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
