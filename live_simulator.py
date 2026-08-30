import requests
import datetime
from dataclasses import dataclass, asdict
from typing import Dict, List, Literal

TELEGRAM_BOT_TOKEN = "8849431477:AAEhJvZ9CK8lng3EEH3ujNgx5fhm6CD4_WQ"
TELEGRAM_CHAT_ID = "7106069536"

def send_telegram_alert(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception:
        pass

@dataclass
class SimulatedPosition:
    id: str
    symbol: str
    entry_price: float
    current_price: float
    units: float
    invested_capital: float
    stop_loss: float
    take_profit: float
    entry_time: str
    status: Literal["OPEN", "CLOSED_TP", "CLOSED_SL"] = "OPEN"
    pnl: float = 0.0

class LivePaperEngine:
    def __init__(self, initial_balance: float = 100.0, fee_pct: float = 0.001):
        self.initial_balance = initial_balance
        self.cash = initial_balance
        self.fee_pct = fee_pct
        self.positions: Dict[str, SimulatedPosition] = {}
        self.history: List[dict] = []

    def get_live_price(self, symbol: str) -> float:
        try:
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
            res = requests.get(url, timeout=5).json()
            return float(res['price'])
        except Exception:
            fallback = {"BTCUSDT": 78000.0, "PAXGUSDT": 2500.0}
            return fallback.get(symbol, 100.0)

    def get_portfolio_value(self) -> float:
        open_val = sum(pos.units * pos.current_price for pos in self.positions.values() if pos.status == "OPEN")
        return self.cash + open_val

    def open_trade(self, symbol: str, capital: float, sl: float, tp: float):
        entry_price = self.get_live_price(symbol)
        fee = capital * self.fee_pct
        total_req = capital + fee

        if total_req > self.cash:
            return False

        units = capital / entry_price
        self.cash -= total_req
        trade_id = f"POS_{len(self.positions) + len(self.history) + 1}_{symbol}"

        pos = SimulatedPosition(
            id=trade_id,
            symbol=symbol,
            entry_price=entry_price,
            current_price=entry_price,
            units=units,
            invested_capital=capital,
            stop_loss=sl,
            take_profit=tp,
            entry_time=datetime.datetime.now().strftime("%H:%M:%S")
        )
        self.positions[trade_id] = pos
        
        # إرسال إشعار فوري إلى تيليجرام
        alert_msg = (
            f"🟢 *فتح صفقة تجريبية جديدة ($100 Portfolio)*\n\n"
            f"🔹 *الأصل:* `{symbol}`\n"
            f"💵 *المبلغ المستثمر:* ${capital:.2f}\n"
            f"🎯 *سعر الدخول:* ${entry_price:.2f}\n"
            f"🛑 *وقف الخسارة:* ${sl:.2f}\n"
            f"🚀 *الهدف:* ${tp:.2f}\n"
            f"💰 *الكاش المتبقي:* ${self.cash:.2f}"
        )
        send_telegram_alert(alert_msg)
        print(f"✅ [Trade Opened]: {symbol} at ${entry_price:.2f}")
        return True

    def sync_market_and_check_exits(self):
        if not self.positions:
            return

        for pos_id, pos in list(self.positions.items()):
            current_price = self.get_live_price(pos.symbol)
            pos.current_price = current_price

            if current_price >= pos.take_profit:
                self._close(pos, current_price, "CLOSED_TP")
            elif current_price <= pos.stop_loss:
                self._close(pos, current_price, "CLOSED_SL")

    def _close(self, pos: SimulatedPosition, exit_price: float, reason: str):
        gross = pos.units * exit_price
        net = gross - (gross * self.fee_pct)
        pnl = net - pos.invested_capital
        pos.status = reason
        pos.pnl = pnl
        self.cash += net
        self.history.append(asdict(pos))
        del self.positions[pos.id]

        icon = "🎯 *تم تحقيق الهدف (Take Profit)*" if pnl > 0 else "🛑 *تم ضرب وقف الخسارة (Stop Loss)*"
        alert_msg = (
            f"{icon}\n\n"
            f"🔹 *الأصل:* `{pos.symbol}`\n"
            f"🚪 *سعر الخروج:* ${exit_price:.2f}\n"
            f"📊 *الربح/الخسارة:* ${pnl:+.2f}\n"
            f"💰 *قيمة المحفظة الكلية:* ${self.get_portfolio_value():.2f}"
        )
        send_telegram_alert(alert_msg)
        print(f"Closed {pos.symbol} | PnL: ${pnl:+.2f}")
