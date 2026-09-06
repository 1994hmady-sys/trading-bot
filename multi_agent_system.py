import os
import json
import requests
import ccxt
from flask import Flask

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = "8849431477:AAGVNZett1gWBikPg6fWJ4p2CJhQJxWEaaw"
TELEGRAM_CHAT_ID = "7106069536"

# قائمة الوحش: عملات ثقيلة + عملات سريعة الحركة جداً (Meme & AI)
WATCHLIST = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "SUI/USDT", 
             "PEPE/USDT", "WIF/USDT", "DOGE/USDT", "RENDER/USDT", "XRP/USDT"]

def send_telegram_msg(msg: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try: requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=5)
    except: pass

class FastTrader:
    def __init__(self):
        self.f = "wallet.json"
        # إنشاء محفظة جديدة خالية من قيود المحرك القديم
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
            
            # عقلية جني الأرباح: يبيع عند ربح سريع (+0.7%) أو يوقف الخسارة مبكراً (-1.5%)
            if profit >= 0.7 or profit <= -1.5:
                rev = pos["qty"] * cp
                d["balance"] += rev
                pnl = rev - (pos["qty"] * ep)
                icon = "✅ ربح سريع" if pnl > 0 else "❌ وقف خسارة"
                sold.append(f"{icon} {sym}: {profit:.2f}% | ${pnl:.2f}")
                del d["pos"][sym]
        if sold:
            self.save(d)
            send_telegram_msg("🔔 [إغلاق صفقات آلي]\n" + "\n".join(sold) + f"\nالرصيد المحدث: ${d['balance']:.2f}")
        return d

    def buy(self, sym, price, reason):
        d = self.run()
        # لا تشتري إذا كنا نملك العملة أو الرصيد غير كافي
        if sym in d["pos"] or d["balance"] < 15: return False
        
        # يدخل بـ 35% من الرصيد في كل فرصة لزيادة سرعة الربح
        amount = d["balance"] * 0.35 
        qty = amount / price
        d["balance"] -= amount
        d["pos"][sym] = {"entry": price, "qty": qty}
        self.save(d)
        send_telegram_msg(f"🟢 [هجوم - شراء فوري]\nالعملة: {sym}\nالسعر: ${price:,.5f}\nالسبب: {reason}")
        return True

class HyperAIBrain:
    def __init__(self):
        self.ex = ccxt.mexc({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
        self.trader = FastTrader()

    def scan(self):
        intel = []
        current_prices = {}
        
        for sym in WATCHLIST:
            try:
                # يقرأ آخر 5 حركات (كل شمعة 5 دقائق)
                ohlcv = self.ex.fetch_ohlcv(sym, "5m", limit=5)
                if not ohlcv: continue
                closes = [float(k[4]) for k in ohlcv]
                cp = closes[-1]
                clean = sym.replace("/", "")
                current_prices[clean] = cp
                
                if len(closes) >= 3:
                    # عقلية الهجوم 1: الشراء عند التفاؤل والزخم (شمعتين صعود)
                    if closes[-1] > closes[-2] and closes[-2] > closes[-3]:
                        self.trader.buy(clean, cp, "🚀 صعود قوي وتفاؤل بالسوق (ركوب الموجة)")
                    
                    # عقلية الهجوم 2: الشراء من الانخفاض عند أول ارتداد
                    elif closes[-1] > closes[-2] and closes[-2] < closes[-3]:
                        self.trader.buy(clean, cp, "🎯 اصطياد قاع سريع (ارتداد إيجابي)")
                        
                intel.append(f"🔹 {clean}: ${cp:,.4f}")
            except:
                continue
                
        # تفقد المبيعات
        state = self.trader.check_sells(current_prices)
        return intel, state

brain = HyperAIBrain()
ping = 0

@app.route('/')
def home():
    global ping
    try:
        intel, state = brain.scan()
        ping += 1
        if ping % 6 == 0:
            bal = state["balance"]
            pos = len(state["pos"])
            text = "\n".join(intel) if intel else "لا بيانات"
            send_telegram_msg(f"🔥 تقرير الذكاء ההجومي:\nالرصيد المتاح: ${bal:.2f}\nالصفقات المفتوحة: {pos}\n\n{text}")
        return "OK", 200
    except Exception as e:
        return "Err", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
