import os
import json
import requests
import ccxt
import time
import threading
import xml.etree.ElementTree as ET
from flask import Flask
import google.generativeai as genai

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = "8849431477:AAGVNZett1gWBikPg6fWJ4p2CJhQJxWEaaw"
TELEGRAM_CHAT_ID = "7106069536"
GEMINI_API_KEY = "AIzaSyCnBcFQeiGJf8DovA6HcZjUoqlNud8kkU4"

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

WATCHLIST = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "SUI/USDT", "PEPE/USDT", "DOGE/USDT", "WIF/USDT", "RENDER/USDT"]

def send_telegram_msg(msg: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try: requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=5)
    except: pass

class FastTrader:
    def __init__(self):
        self.f = "wallet.json"
        if not os.path.exists(self.f):
            with open(self.f, "w") as file: json.dump({"balance": 100.0, "pos": {}}, file)
    
    def run(self):
        with open(self.f, "r") as file: return json.load(file)
        
    def save(self, d):
        with open(self.f, "w") as file: json.dump(d, file)

    def check_sells(self, prices):
        d = self.run()
        sold = []
        for sym, pos in list(d["pos"].items()):
            if sym not in prices: continue
            cp = prices[sym]
            ep = pos["entry"]
            profit = ((cp - ep) / ep) * 100
            
            tp = pos.get("tp_percent", 1.5)
            sl = pos.get("sl_percent", -1.0)
            
            if profit >= tp or profit <= sl:
                rev = pos["qty"] * cp
                d["balance"] += rev
                pnl = rev - (pos["qty"] * ep)
                icon = f"✅ ربح شامل (+{tp}%)" if pnl > 0 else f"❌ انسحاب تكتيكي ({sl}%)"
                sold.append(f"{icon} {sym}: {profit:.2f}% | ${pnl:.2f}")
                del d["pos"][sym]
        if sold:
            self.save(d)
            send_telegram_msg("🔔 [قرار جيميناي السيادي]\n" + "\n".join(sold) + f"\nالرصيد المتاح: ${d['balance']:.2f}")
        return d

    def buy(self, sym, price, reason, tp, sl):
        d = self.run()
        if sym in d["pos"] or d["balance"] < 15: return False
        
        amount = d["balance"] * 0.40 
        qty = amount / price
        d["balance"] -= amount
        d["pos"][sym] = {"entry": price, "qty": qty, "tp_percent": tp, "sl_percent": sl}
        self.save(d)
        send_telegram_msg(f"🌍 [جيميناي - شراء جيوسياسي]\nالعملة: {sym}\nالسعر: ${price:,.5f}\nالهدف: +{tp}%\nالوقف: {sl}%\nالتحليل الشامل: {reason}")
        return True

class GeminiBrain:
    def __init__(self):
        self.ex = ccxt.mexc({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
        self.trader = FastTrader()
        self.global_news = "لا توجد أخبار حالياً"
        self.last_news_update = 0

    def update_news_radar(self):
        if time.time() - self.last_news_update < 900: return
        try:
            resp = requests.get("https://cointelegraph.com/rss", timeout=5)
            root = ET.fromstring(resp.content)
            headlines = [item.find('title').text for item in root.findall('./channel/item')[:5]]
            self.global_news = " | ".join(headlines)
            self.last_news_update = time.time()
        except:
            pass

    def ask_gemini(self, coin, closes, volumes):
        prompt = f"""
        أنت مدير محفظة استثمارية كبرى (Hedge Fund Manager) وقارئ نهم للأحداث الجيوسياسية والاقتصادية.
        العملة: {coin}
        الأسعار الفنية (5 دقائق): {closes}
        رادار الأخبار العالمية الآن: {self.global_news}
        
        ادمج التحليل الفني مع الأخبار العالمية الحية. هل هناك فرصة شراء قوية الآن؟
        يجب أن ترد بصيغة JSON فقط كالتالي (بدون أي نصوص إضافية):
        {{"action": "BUY" or "HOLD", "reason": "سبب يدمج الفني بالأخبار", "tp": 2.0, "sl": -1.2}}
        """
        try:
            response = model.generate_content(prompt)
            text = response.text.strip().replace("```json", "").replace("```", "")
            return json.loads(text)
        except Exception:
            return {"action": "HOLD"}

    def scan(self):
        self.update_news_radar()
        intel = []
        current_prices = {}
        
        for sym in WATCHLIST:
            try:
                ohlcv = self.ex.fetch_ohlcv(sym, "5m", limit=5)
                if not ohlcv: continue
                closes = [float(k[4]) for k in ohlcv]
                volumes = [float(k[5]) for k in ohlcv]
                cp = closes[-1]
                clean = sym.replace("/", "")
                current_prices[clean] = cp
                
                decision = self.ask_gemini(clean, closes, volumes)
                
                if decision.get("action") == "BUY":
                    self.trader.buy(clean, cp, decision.get("reason", "اقتناص فرصة مؤكدة"), decision.get("tp", 1.5), decision.get("sl", -1.0))
                
                intel.append(f"🔹 {clean}: ${cp:,.4f}")
                time.sleep(1.5)
            except:
                continue
                
        state = self.trader.check_sells(current_prices)
        return intel, state

brain = GeminiBrain()
ping_count = 0

def background_trading_loop():
    global ping_count
    while True:
        try:
            intel, state = brain.scan()
            ping_count += 1
            if ping_count % 6 == 0:
                bal = state["balance"]
                pos = len(state["pos"])
                text = "\n".join(intel) if intel else "لا بيانات"
                send_telegram_msg(f"🌍 تقرير جيميناي الشامل (اقتصاد + فني):\nالرصيد المتاح: ${bal:.2f}\nالصفقات المفتوحة: {pos}\n\n{text}")
        except Exception:
            pass
        # ينتظر البوت 5 دقائق قبل المسح التالي ليتداول بشكل مستقل تماماً
        time.sleep(300) 

# تشغيل العقل المتداول في الخلفية بمجرد تشغيل السيرفر
threading.Thread(target=background_trading_loop, daemon=True).start()

@app.route('/')
def home():
    # هذه الواجهة ترد على UptimeRobot فوراً لمنع رسائل الخطأ
    return "Gemini Trading Agent is ACTIVE and scanning in the background!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
