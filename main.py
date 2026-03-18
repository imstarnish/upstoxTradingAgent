import asyncio
import logging
import pandas as pd
import datetime
from core.auth import UpstoxAuth
from strategy.trend_logic import TrendLogic
from execution.paper_trader import PaperTrader
import upstox_client

# Configure logging
logging.basicConfig(
    filename='trades.log',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Constants
TICKERS = ["NSE_EQ|INE171A01029", "NSE_EQ|INE040A01034"]
POLL_INTERVAL = 15 * 60  # 15 minutes in seconds

async def fetch_historical_data(api_client: upstox_client.ApiClient, instrument_key: str) -> pd.DataFrame:
    """Fetches historical 15-minute candle data."""
    try:
        api_instance = upstox_client.HistoryApi(api_client)
        to_date = datetime.datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.datetime.now() - datetime.timedelta(days=365)).strftime("%Y-%m-%d")
        interval = "15minute"

        api_response = api_instance.get_historical_candle_data(
            instrument_key,
            interval,
            to_date,
            from_date
        )

        if api_response and api_response.status == 'success' and api_response.data:
            candles = api_response.data.candles
            df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
            df['datetime'] = pd.to_datetime(df['timestamp'])
            df.set_index('datetime', inplace=True)
            df.sort_index(inplace=True)
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            return df
        else:
            logging.error(f"Failed to fetch data for {instrument_key}: {api_response}")
            return pd.DataFrame()

    except Exception as e:
        logging.error(f"Error fetching data for {instrument_key}: {e}")
        return pd.DataFrame()

async def run_bot(api_client: upstox_client.ApiClient):
    """Main asynchronous trading loop using PaperTrader."""
    strategy_engine = TrendLogic(account_size=100000.0, risk_percentage=0.01)
    paper_trader = PaperTrader(starting_capital=100000.0)

    logging.info("Starting trading bot loop...")
    print("Starting trading bot loop...")

    while True:
        try:
            for ticker in TICKERS:
                logging.info(f"Fetching data and evaluating strategy for {ticker}...")
                print(f"Fetching data and evaluating strategy for {ticker}...")

                df = await fetch_historical_data(api_client, ticker)

                if df.empty:
                    logging.warning(f"No data received for {ticker}. Skipping.")
                    continue

                signal = strategy_engine.generate_signal(df)
                logging.info(f"Signal for {ticker}: {signal}")

                current_price = df.iloc[-1]['close']
                timestamp = df.index[-1]

                if signal == 'BUY':
                    position_size = strategy_engine.calculate_position_size(df)
                    quantity = max(1, int(position_size))

                    logging.info(f"BUY signal confirmed for {ticker}.")
                    print(f"[PAPER TRADE] Initiating BUY for {quantity} of {ticker} at {current_price}")
                    paper_trader.process_signal(ticker, signal, current_price, quantity, timestamp)

                elif signal == 'SELL':
                    logging.info(f"SELL signal generated for {ticker}.")
                    print(f"[PAPER TRADE] Initiating SELL for {ticker} at {current_price}")
                    # PaperTrader will look up the held quantity itself based on ticker
                    # We pass 0 for quantity as it sells all held units in this simple impl
                    paper_trader.process_signal(ticker, signal, current_price, 0, timestamp)

        except Exception as e:
            logging.error(f"Unexpected error in trading loop: {e}")

        logging.info(f"Sleeping for {POLL_INTERVAL} seconds...")
        await asyncio.sleep(POLL_INTERVAL)

def main():
    try:
        # Placeholders
        API_KEY = "your_api_key"
        API_SECRET = "your_api_secret"
        REDIRECT_URI = "https://your.redirect.uri"
        TOTP_SECRET = "your_totp_secret"
        MOBILE_NUMBER = "your_mobile"
        PIN = "your_pin"

        logging.info("Initializing Upstox Authentication...")
        auth = UpstoxAuth(API_KEY, API_SECRET, REDIRECT_URI, TOTP_SECRET, MOBILE_NUMBER, PIN)

        api_client = auth.get_api_client()
        logging.info("Authentication successful. Starting async loop.")

        asyncio.run(run_bot(api_client))

    except Exception as e:
        logging.critical(f"Critical failure in main application: {e}")

if __name__ == "__main__":
    main()
