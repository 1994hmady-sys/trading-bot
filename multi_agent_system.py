import os
import requests
import ccxt
from flask import Flask
from live_simulator import LivePaperEngine

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = "8849431477:AAGVNZett1gWBikPg6fWJ4p2CJhQJxWEaaw"
TELEGRAM_CHAT_ID = "7106069536"
WATCHLIST = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]

def send_telegram_msg(msg: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
    try:
        requests.post(url, json=payload, timeout=5)
    except:
        pass

class FreeMindAIBrain:
    def __init__(self):
        self.exchange = ccxt.mexc({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })

    def get_klines(self, symbol, timeframe="15m", limit=50):
        # استخدام فريم 15 دقيقة للحصول على صفقات أصلب وأكثر استقراراً للـ 100$
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            if not ohlcv: return [], []
            closes = [float(candle[4]) for candle in ohlcv]
            volumes = [float(candle[5]) for candle in ohlcv]
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

    def calculate_bollinger_bands(self, prices, period=20):
        if len(prices) < period:
            return prices[-1], prices[-1], prices[-1]
        sma = sum(prices[-period:]) / period
        variance = sum([(p - sma) ** 2 for p in prices[-period:]]) / period
        std_dev = variance ** 0.5
        upper_band = sma + (2 * std_dev)
        lower_band = sma - (2 * std_dev)
        return lower_band, sma, upper_band

    def scan_market(self):
        opportunities = []
        market_intel = []
        
        for symbol in WATCHLIST:
            clean_symbol = symbol.replace("/", "")
            closes, volumes = self.get_klines(symbol)
            
            if len(closes) < 25:
                market_intel.append(f"⚠️ {clean_symbol}: جاري الانتظار")
                continue
            
            current_price = closes[-1]
            rsi = self.calculate_rsi(closes, period=14)
            lower_band, sma, upper_band = self.calculate_bollinger_bands(closes)
            
            # ---------------------------------------------------------
            # نظام التقييم الديناميكي (AI Scoring System) من 0 إلى 100
            # ---------------------------------------------------------
            ai_score = 0
            reasoning = []

            # 1. تحليل القاع والقمة (حماية رأس المال من الشراء في الأعلى)
            if current_price <= lower_band * 1.01:
                ai_score += 40
                reasoning.append("سعر رخيص جداً (قاع البولينجر)")
            elif current_price >= upper_band * 0.99:
                ai_score -= 50 # عقاب شديد: لا تشتري القمة أبداً
                reasoning.append("تحذير: السعر في القمة")
            elif current_price < sma:
                ai_score += 20
                reasoning.append("السعر تحت المتوسط (فرصة تجميع)")

            # 2. تحليل زخم الارتداد (هل توقف النزيف؟)
            if rsi < 30:
                ai_score += 10
                reasoning.append("تشبع بيعي عميق")
            elif 30 <= rsi <= 45 and closes[-1] > closes[-2]:
                ai_score += 35
                reasoning.append("تأكيد بدء الارتداد للأعلى")
            elif rsi > 65:
                ai_score -= 40 # عقاب: لا تشتري والناس تطمع
                reasoning.append("تحذير: تشبع شرائي")

            # 3. تحليل تأكيد السيولة
            vol_avg = sum(volumes[-10:]) / 10 if volumes else 1.0
            if volumes[-1] > vol_avg * 1.5:
                ai_score += 15
                reasoning.append("دخول سيولة قوية للسوق")

            # تسجيل حالة السوق في التقرير
            market_intel.append(f"🔹 {clean_symbol}: ${current_price:,.2f} | التقييم: {ai_score}/100")

            # اتخاذ القرار الحر: الدخول فقط إذا كانت الفرصة ذهبية (أكبر من 75 نقطة)
            if ai_score >= 75:
                # تقسيم الرهان: يدخل بوزن بسيط ليسمح بالتنويع
                opportunities.append({
                    "asset": clean_symbol, 
                    "direction": "BUY",
                    "catalyst": f"🧠 قرار ذكي ({ai_score} نقطة): " + " + ".join(reasoning[:2]), 
                    "weight": 0.25 # يستخدم 25% من الـ 100$ لكل فرصة ممتازة
                })

        return opportunities, market_intel

try:
    engine = LivePaperEngine(initial_balance=100.0)
except Exception:
    engine = None

ai_brain = FreeMindAIBrain()
ping_count = 0

@app.route('/')
def home():
    global ping_count, engine
    if not engine: return "Engine Error", 500

    try:
        # إدارة الصفقات المفتوحة (البيع عند الهدف أو وقف الخسارة)
        if hasattr(engine, 'check_open_positions'):
            engine.check_open_positions(send_telegram_msg)
        elif hasattr(engine, 'update_positions'):
            engine.update_positions(send_telegram_msg)

        # البحث عن الفرص الجديدة
        setups, intel = ai_brain.scan_market()
        for setup in setups:
            if hasattr(engine, 'execute_simulated_trade'):
                engine.execute_simulated_trade(
                    asset=setup["asset"], weight=setup["weight"],
                    catalyst=setup["catalyst"], notifier=send_telegram_msg
                )

        ping_count += 1
        if ping_count % 6 == 0:
            text = "\n".join([f"{x}" for x in intel])
            if not text.strip(): text = "لا توجد بيانات متاحة حالياً"
            
            bal = engine.balance if hasattr(engine, 'balance') else 100.0
            pos_len = len(engine.open_positions) if hasattr(engine, 'open_positions') else 0
            
            send_telegram_msg(
                f"🧠 تقرير العقل الحر (نظام التقييم):\n"
                f"الرصيد: ${bal:.2f}\n"
                f"الصفقات المفتوحة: {pos_len}\n\n"
                f"📊 تحليل الذكاء الاصطناعي (من 100):\n{text}"
            )
        return "OK", 200
    except Exception as e:
        send_telegram_msg(f"⚠️ خطأ غير متوقع: {str(e)}")
        return "Error", 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
