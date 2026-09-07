import os
import json
import requests
import ccxt
import time
import threading
from flask import Flask
import google.generativeai as genai

app = Flask(__name__)

# الأمان الصارم: جلب المفاتيح من بيئة النظام فقط
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = "7106069536" 
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

WATCHLIST = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "SUI/USDT", "PEPE/USDT", "WIF/USDT"]

def send_telegram_msg(msg: str):
    if not TELEGRAM_BOT_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try: requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=5)
    except: pass

class TradeMemory:
    def __init__(self):
        self.f = "memory.json"
        if not os.path.exists(self.f):
            with open(self.f, "w") as file: json.dump({"trades": [], "win_rate": 0.0, "total_pnl": 0.0}, file)
            
    def log_trade(self, coin, strategy, profit_pct, pnl_usd):
        with open(self.f, "r") as file: data = json.load(file)
        data["trades"].append({"coin": coin, "strategy": strategy, "profit_pct": profit_pct, "pnl_usd": pnl_usd})
        wins = sum(1 for t in data["trades"] if t["pnl_usd"] > 0)
        data["win_rate"] = (wins / len(data["trades"])) * 100
        data["total_pnl"] += pnl_usd
        with open(self.f, "w") as file: json.dump(data, file)
        return data

class RiskBrain:
    def __init__(self, risk_per_trade_pct=1.0):
        self.risk_pct = risk_per_trade_pct / 100.0

    def calculate_position(self, balance, sl_pct):
        if sl_pct >= 0: return 0
        risk_amount = balance * self.risk_pct
        position_size = risk_amount / abs(sl_pct / 100.0)
        return min(position_size, balance * 0.50) # حماية قصوى: لا تتجاوز 50% من المحفظة أبداً

class MarketBrain:
    def __init__(self):
        self.ex = ccxt.mexc({'enableRateLimit': True})
        
    def scan_momentum(self, sym):
        try:
            ohlcv = self.ex.fetch_ohlcv(sym, "5m", limit=15)
            if not ohlcv: return None
            closes = [float(k[4]) for k in ohlcv]
            volumes = [float(k[5]) for k in ohlcv]
            
            avg_vol = sum(volumes[:-1]) / len(volumes[:-1]) if len(volumes)>1 else 1
            vol_spike = volumes[-1] > (avg_vol * 1.5)
            trend = "صاعد" if closes[-1] > closes[0] else "هابط"
            
            return {"closes": closes, "vol_spike": vol_spike, "trend": trend}
        except: return None

class ExecutionBrain:
    def __init__(self):
        self.f = "wallet_v3.json"
        self.memory = TradeMemory()
        if not os.path.exists(self.f):
            with open(self.f, "w") as file: json.dump({"balance": 100.0, "pos": {}}, file)
            
    def run(self):
        with open(self.f, "r") as file: return json.load(file)
    def save(self, d):
        with open(self.f, "w") as file: json.dump(d, file)

    def update_positions(self, current_prices):
        d = self.run()
        sold = []
        for sym, pos in list(d["pos"].items()):
            if sym not in current_prices: continue
            cp = current_prices[sym]
            ep = pos["entry"]
            profit_pct = ((cp - ep) / ep) * 100
            
            if profit_pct >= pos["tp"] or profit_pct <= pos["sl"]:
                rev = pos["qty"] * cp
                d["balance"] += rev
                pnl = rev - (pos["qty"] * ep)
                self.memory.log_trade(sym, pos["strategy"], profit_pct, pnl)
                
                icon = "✅ ربح" if pnl > 0 else "❌ وقف خسارة"
                sold.append(f"{icon} {sym}: {profit_pct:.2f}% | ${pnl:.2f}")
                del d["pos"][sym]
        if sold:
            self.save(d)
            mem_data = self.memory.log_trade("","",0,0) # جلب الإحصائيات
            send_telegram_msg(f"🔔 [إغلاق الصفقات]\n" + "\n".join(sold) + f"\nالرصيد: ${d['balance']:.2f}\nمعدل النجاح: {mem_data['win_rate']:.1f}%")
        return d

    def execute_trade(self, sym, price, size, tp, sl, strategy):
        d = self.run()
        qty = size / price
        d["balance"] -= size
        d["pos"][sym] = {"entry": price, "qty": qty, "tp": tp, "sl": sl, "strategy": strategy}
        self.save(d)
        send_telegram_msg(f"⚡ [دخول Paper Trading]\nالعملة: {sym}\nالاستراتيجية: {strategy}\nالحجم: ${size:.2f}\nالهدف: +{tp}%\nالوقف: {sl}%")

class AI_System:
    def __init__(self):
        self.market = MarketBrain()
        self.risk = RiskBrain(risk_per_trade_pct=1.0) # المخاطرة 1% من الرصيد
        self.executor = ExecutionBrain()

    def decide(self, coin, data):
        prompt = f"""
        أنت عقل كمي (Quant AI). 
        العملة: {coin}
        الأسعار (15 شمعة): {data['closes']}
        الزخم: {data['trend']} | اختراق سيولة: {data['vol_spike']}
        
        حلل بناءً على Price Action والزخم.
        الرد JSON فقط: {{"action": "BUY", "strategy": "Breakout", "tp": 2.5, "sl": -1.0, "score": 85}}
        الـ score من 100. لا تشتري إلا إذا كان الـ score أعلى من 80.
        """
        try:
            resp = model.generate_content(prompt).text.strip().replace("```json", "").replace("```", "")
            return json.loads(resp)
        except: return {"action": "HOLD"}

    def scan(self):
        state = self.executor.run()
        prices = {}
        reports = []
        
        for sym in WATCHLIST:
            data = self.market.scan_momentum(sym)
            if not data: continue
            
            cp = data['closes'][-1]
            clean = sym.replace("/", "")
            prices[clean] = cp
            
            if clean not in state["pos"] and state["balance"] > 10:
                decision = self.decide(clean, data)
                if decision.get("action") == "BUY" and decision.get("score", 0) >= 80:
                    tp = float(decision.get("tp", 2.0))
                    sl = float(decision.get("sl", -1.0))
                    if tp > abs(sl): # تأكيد العائد مقابل المخاطرة
                        size = self.risk.calculate_position(state["balance"], sl)
                        if size > 5:
                            self.executor.execute_trade(clean, cp, size, tp, sl, decision.get("strategy", "Momentum"))
            
            reports.append(f"🔹 {clean}: ${cp:,.4f}")
            time.sleep(1.5)
            
        self.executor.update_positions(prices)
        return reports, state

sys = AI_System()
ping = 0

def run_bot():
    global ping
    while True:
        try:
            reports, state = sys.scan()
            ping += 1
            if ping % 10 == 0:
                send_telegram_msg(f"📊 تقرير V3 (Paper Trading):\nالرصيد: ${state['balance']:.2f}\nالصفقات: {len(state['pos'])}\n\n" + "\n".join(reports))
        except: pass
        time.sleep(180)

threading.Thread(target=run_bot, daemon=True).start()

@app.route('/')
def home(): return "V3 Paper Trading System is Running!", 200
if __name__ == "__main__": app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
