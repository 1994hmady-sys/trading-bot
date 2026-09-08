import os, json, requests, ccxt, time, threading
from flask import Flask
import google.generativeai as genai

app = Flask(__name__)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = "7106069536" 
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if GEMINI_API_KEY: genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

WATCHLIST = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "SUI/USDT", "PEPE/USDT", "WIF/USDT"]

def send_telegram_msg(msg: str):
    if not TELEGRAM_BOT_TOKEN: return
    try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=5)
    except: pass

class MarketBrain:
    def __init__(self): self.ex = ccxt.mexc({'enableRateLimit': True})
    def scan(self, sym):
        try:
            ohlcv = self.ex.fetch_ohlcv(sym, "5m", limit=15)
            if not ohlcv: return None
            closes = [float(k[4]) for k in ohlcv]
            return {"closes": closes, "trend": "صاعد" if closes[-1] > closes[0] else "هابط"}
        except: return None

class ExecutionBrain:
    def __init__(self):
        self.f = "wallet_v4.json"
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
                icon = "✅ ربح" if pnl > 0 else "❌ انسحاب"
                sold.append(f"{icon} {sym}: {profit_pct:.2f}% | ${pnl:.2f}")
                del d["pos"][sym]
        if sold:
            self.save(d)
            send_telegram_msg(f"🔔 [إغلاق الصفقات بقرار العقل]\n" + "\n".join(sold) + f"\nالرصيد: ${d['balance']:.2f}")
        return d
    def execute_trade(self, sym, price, size, tp, sl, strategy, reason):
        d = self.run()
        qty = size / price
        d["balance"] -= size
        d["pos"][sym] = {"entry": price, "qty": qty, "tp": tp, "sl": sl, "strategy": strategy}
        self.save(d)
        send_telegram_msg(f"🧠 [جيميناي يتخذ القرار]\nالعملة: {sym}\nالاستراتيجية: {strategy}\nالمبرر: {reason}\nالحجم: ${size:.2f}\nالهدف: +{tp}%\nالوقف: {sl}%")

class AI_System:
    def __init__(self):
        self.market = MarketBrain()
        self.executor = ExecutionBrain()
    def decide(self, coin, data):
        prompt = f"""أنت العقل المتحكم تماماً في محفظة تداول. السوق الآن {data['trend']} لعملة {coin}. أسعارها: {data['closes']}.
        لا توجد قيود. قرر استراتيجية تناسب اللحظة (مثلاً قناص سريع، صائد قيعان، الخ). 
        رد بـ JSON فقط: {{"action": "BUY", "strategy": "اسم الاستراتيجية", "reason": "سبب الدخول باختصار", "tp": 1.5, "sl": -1.0, "risk_pct": 5.0}}
        إذا لم يكن هناك أي فرصة منطقية، اجعل action: HOLD."""
        try:
            resp = model.generate_content(prompt).text.strip().replace("```json", "").replace("```", "")
            return json.loads(resp)
        except: return {"action": "HOLD"}
    def scan(self):
        state = self.executor.run()
        prices = {}
        for sym in WATCHLIST:
            data = self.market.scan(sym)
            if not data: continue
            cp = data['closes'][-1]
            clean = sym.replace("/", "")
            prices[clean] = cp
            if clean not in state["pos"] and state["balance"] > 15:
                decision = self.decide(clean, data)
                if decision.get("action") == "BUY":
                    risk_pct = float(decision.get("risk_pct", 5.0)) / 100.0
                    size = state["balance"] * risk_pct
                    if size > 5:
                        self.executor.execute_trade(clean, cp, size, float(decision.get("tp", 1.5)), float(decision.get("sl", -1.0)), decision.get("strategy", "Dynamic"), decision.get("reason", "قرار ديناميكي"))
            time.sleep(2)
        self.executor.update_positions(prices)
        return state

sys = AI_System()
ping = 0
def run_bot():
    global ping
    while True:
        try:
            state = sys.scan()
            ping += 1
            if ping % 10 == 0: send_telegram_msg(f"📊 تقرير V4 (القيادة لجيميناي):\nالرصيد: ${state['balance']:.2f}\nالصفقات المفتوحة: {len(state['pos'])}")
        except: pass
        time.sleep(120)

threading.Thread(target=run_bot, daemon=True).start()
@app.route('/')
def home(): return "V4 Unchained is Running!", 200
if __name__ == "__main__": app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
