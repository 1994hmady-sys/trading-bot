import os
import time
import threading
import requests
from flask import Flask
from live_simulator import LivePaperEngine

app = Flask(__name__)

# استخدام متغير البيئة إن وجد أو التوكن المباشر
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8849431477:AAGVNZett1gWBikPg6fWJ4p2CJhQJxWEaaw")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "6176503816")

WATCHLIST = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "PAXGUSDT"]

def send_telegram_msg(msg: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
    try:
        r = requests.post(url, json=payload, timeout=10)
        print(f"[Telegram] Sent status: {r.status_code}")
    except Exception as e:
        print(f"[Telegram Error] {e}")

class PrecisionSniperBrain:
    def get_klines(self, symbol, interval="15m", limit=35):
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        try:
            res = requests.get(url, timeout=6).json()
            closes = [float(k[4]) for k in res]
            highs = [float(k[2]) for k in res]
            lows = [float(k[3]) for k in res]
            volumes = [float(k[5]) for k in res]
            return closes, highs, lows, volumes
        except Exception:
            return [], [], [], []

    def calculate_rsi(self, prices, period=14):
        if len(prices) < period + 1:
            return 50.0
        gains, losses = [], []
        for i in range(1, len(prices)):
            diff = prices[i] - prices[i - 1]
            gains.append(diff if diff > 0 else 0)
            losses.append(abs(diff) if diff < 0 else 0)
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def calculate_ema(self, prices, period):
        if len(prices) < period:
            return prices[-1]
        k = 2 / (period + 1)
        ema = prices[0]
        for price in prices[1:]:
            ema = (price * k) + (ema * (1 - k))
        return ema

    def scan_sniper_setups(self):
        opportunities = []
        market_intel = []

        for symbol in WATCHLIST:
            closes, highs, lows, volumes = self.get_klines(symbol)
            if len(closes) < 25:
                continue

            current_price = closes[-1]
            rsi = self.calculate_rsi(closes, period=14)
            ema_fast = self.calculate_ema(closes, period=9)
            ema_slow = self.calculate_ema(closes, period=21)
            vol_avg = sum(volumes[-10:]) / 10
            vol_spike = volumes[-1] > (vol_avg * 1.3)

            market_intel.append(f"{symbol}: ${current_price:,.2f} | RSI: {rsi:.1f}")

            # 1. ارتداد من تشبع بيعي حاد
            if rsi < 32 and current_price > closes[-2]:
                opportunities.append({
                    "asset": symbol,
                    "direction": "BUY",
                    "catalyst": f"🎯 قنص تشبع بيعي عميق (RSI={rsi:.1f}) مع ارتداد",
                    "weight": 0.12
                })

            # 2. اختراق صاعد مع سيولة حيتان
            elif ema_fast > ema_slow and closes[-2] <= ema_slow and vol_spike and rsi > 52:
                opportunities.append({
                    "asset": symbol,
                    "direction": "BUY",
                    "catalyst": f"⚡ اختراق تريند مؤسسي صاعد مع سيولة قوية (RSI={rsi:.1f})",
                    "weight": 0.15
                })

        return opportunities, market_intel

def bot_worker_loop():
    time.sleep(5)
    send_telegram_msg("🚀 تم استعادة الاتصال وتفعيل محرك القناص المؤسسي الذكي!\nالبوت الآن يتربص بالفرص عالية الدقة وسيرسل التقرير الفني بانتظام.")

    try:
        engine = LivePaperEngine(initial_balance=100.0)
    except Exception as e:
        print(f"[Init Error] {e}")
        return

    sniper = PrecisionSniperBrain()
    loop_count = 0

    while True:
        try:
            # 1. متابعة الصفقات المفتوحة
            engine.check_open_positions(send_telegram_msg)

            # 2. البحث عن صفقات دقيقة
            setups, intel = sniper.scan_sniper_setups()
            for setup in setups:
                engine.execute_simulated_trade(
                    asset=setup["asset"],
                    weight=setup["weight"],
                    catalyst=setup["catalyst"],
                    notifier=send_telegram_msg
                )

            # 3. تقرير دوري كل 30 دقيقة
            loop_count += 1
            if loop_count % 30 == 0:
                summary_text = "\n".join([f"• {line}" for line in intel])
                send_telegram_msg(
                    f"🎯 تقرير القناص الدوري:\n"
                    f"السيولة: ${engine.balance:.2f}\n"
                    f"الصفقات المفتوحة: {len(engine.open_positions)}\n\n"
                    f"📊 نبض السوق:\n{summary_text}\n\n"
                    f"الحالة: قيد المراقبة اللحظية 24/7."
                )

            time.sleep(60)
        except Exception as e:
            print(f"[Loop Exception] {e}")
            time.sleep(60)

@app.route('/')
def home():
    return "Institutional Sniper AI Active 24/7", 200

worker_thread = threading.Thread(target=bot_worker_loop, daemon=True)
worker_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
