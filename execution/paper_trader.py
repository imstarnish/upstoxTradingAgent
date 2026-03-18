import csv
import logging
import os

class PaperTrader:
    def __init__(self, starting_capital: float = 100000.0):
        self.current_capital = starting_capital
        self.active_positions = {}
        self.trade_history = []
        self.log_file = 'paper_trade_log.csv'

        # Initialize CSV if it doesn't exist
        if not os.path.exists(self.log_file):
            with open(self.log_file, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(['Symbol', 'Entry_Price', 'Exit_Price', 'Quantity', 'Entry_Time', 'Exit_Time', 'PnL', 'Capital'])

    def process_signal(self, symbol: str, signal: str, current_price: float, quantity: int, timestamp):
        if signal == 'BUY' and symbol not in self.active_positions:
            # Factor in 0.1% for slippage and taxes on buy
            slippage_tax_rate = 0.001
            cost_per_share = current_price * (1 + slippage_tax_rate)
            total_cost = cost_per_share * quantity

            if total_cost <= self.current_capital:
                self.current_capital -= total_cost
                self.active_positions[symbol] = {
                    'entry_price': current_price,
                    'cost_per_share': cost_per_share,
                    'quantity': quantity,
                    'entry_time': timestamp
                }
                logging.info(f"[PAPER TRADE] BUY Executed: {quantity} of {symbol} at {current_price:.2f}. Capital remaining: {self.current_capital:.2f}")
            else:
                logging.warning(f"[PAPER TRADE] Insufficient capital to buy {quantity} of {symbol}. Cost: {total_cost:.2f}, Capital: {self.current_capital:.2f}")

        elif signal == 'SELL' and symbol in self.active_positions:
            position = self.active_positions[symbol]
            entry_price = position['entry_price']
            buy_quantity = position['quantity']
            entry_time = position['entry_time']

            # Factor in 0.1% for slippage and taxes on sell
            slippage_tax_rate = 0.001
            exit_price_net = current_price * (1 - slippage_tax_rate)
            total_revenue = exit_price_net * buy_quantity

            # PnL Calculation
            pnl = total_revenue - (position['cost_per_share'] * buy_quantity)

            # Update capital
            self.current_capital += total_revenue

            # Log Trade
            trade_details = [
                symbol,
                round(entry_price, 2),
                round(current_price, 2),
                buy_quantity,
                entry_time,
                timestamp,
                round(pnl, 2),
                round(self.current_capital, 2)
            ]
            self.trade_history.append(trade_details)

            with open(self.log_file, mode='a', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(trade_details)

            del self.active_positions[symbol]
            logging.info(f"[PAPER TRADE] SELL Executed: {buy_quantity} of {symbol} at {current_price:.2f}. PnL: {pnl:.2f}. Capital: {self.current_capital:.2f}")
