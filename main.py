import asyncio
import logging
import pandas as pd
import datetime
import pytz
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
TICKERS = [
    "NSE_EQ|INE171A01029",  # Federal Bank
    "NSE_EQ|INE040A01034",  # HDFC Bank
    "NSE_EQ|INE002A01018",  # Reliance Industries
    "NSE_EQ|INE090A01021",  # ICICI Bank
    "NSE_EQ|INE009A01021",  # Infosys
    "NSE_EQ|INE018A01030",  # Larsen & Toubro (L&T)
    "NSE_EQ|INE154A01025",  # ITC
    "NSE_EQ|INE467B01029",  # Tata Consultancy Services (TCS)
    "NSE_EQ|INE397D01024",  # Bharti Airtel
    "NSE_EQ|INE238A01034",  # Axis Bank
    "NSE_EQ|INE062A01020"   # State Bank of India (SBI)
]
POLL_INTERVAL = 15 * 60  # 15 minutes in seconds

def is_market_open():
    """Checks if the current time is within NSE trading hours (9:15 AM - 3:30 PM IST Mon-Fri)."""
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.datetime.now(ist)
    
    # Check if it's weekend (5 = Saturday, 6 = Sunday)
    if now.weekday() >= 5:
        return False
        
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    
    return market_open <= now <= market_close

async def fetch_historical_data(api_client: upstox_client.ApiClient, instrument_key: str) -> pd.DataFrame:
    """Fetches historical 15-minute candle data (Optimized Payload)."""
    try:
        api_instance = upstox_client.HistoryApi(api_client)
        to_date = datetime.datetime.now().strftime("%Y-%m-%d")
        # Reduced from 365 days to 60 days to prevent API payload rejection while keeping enough data for EMAs
        from_date = (datetime.datetime.now() - datetime.timedelta(days=60)).strftime("%Y-%m-%d")
        interval = "15minute"

        # Running the synchronous Upstox SDK call in an executor to prevent blocking the async loop
        loop = asyncio.get_running_loop()
        api_response = await loop.run_in_executor(
            None, 
            lambda: api_instance.get_historical_candle_data(instrument_key, interval, to_date, from_date)
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
    """Main asynchronous trading loop with Market Hour safety."""
    strategy_engine = TrendLogic(account_size=100000.0, risk_percentage=0.01)
    paper_trader = PaperTrader(starting_capital=100000.0)

    logging.info("Starting trading bot loop...")
    print("Starting trading bot loop...")

    while True:
        if not is_market_open():
            print(f"[{datetime.datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M:%S')}] Market Closed. Sleeping for 5 minutes...")
            await asyncio.sleep(300) # Check again in 5 minutes
            continue

        try:
            for ticker in TICKERS:
                logging.info(f"Fetching data and evaluating strategy for {ticker}...")
                
                df = await fetch_historical_data(api_client, ticker)

                if df.empty:
                    logging.warning(f"No data received for {ticker}. Skipping.")
                    continue

                signal = strategy_engine.generate_signal(df)
                
                current_price = df.iloc[-1]['close']
                timestamp = df.index[-1]

                if signal == 'BUY':
                    position_size = strategy_engine.calculate_position_size(df)
                    quantity = max(1, int(position_size))

                    logging.info(f"BUY signal confirmed for {ticker}.")
                    print(f"[{timestamp}] PAPER TRADE: Initiating BUY for {quantity} of {ticker} at ₹{current_price}")
                    paper_trader.process_signal(ticker, signal, current_price, quantity, timestamp)

                elif signal == 'SELL':
                    logging.info(f"SELL signal generated for {ticker}.")
                    print(f"[{timestamp}] PAPER TRADE: Initiating SELL for {ticker} at ₹{current_price}")
                    paper_trader.process_signal(ticker, signal, current_price, 0, timestamp)

                # CRITICAL: 1-second delay between stocks to prevent Upstox API ban
                await asyncio.sleep(1)

        except Exception as e:
            logging.error(f"Unexpected error in trading loop: {e}")

        logging.info(f"Cycle complete. Sleeping for {POLL_INTERVAL} seconds...")
        print(f"Cycle complete. Waiting 15 minutes for next candle...")
        await asyncio.sleep(POLL_INTERVAL)

def main():
    try:
        # Note: Ensure these are securely loaded via environment variables in production
        API_KEY = "your_api_key"
        API_SECRET = "your_api_secret"
        REDIRECT_URI = "https://127.0.0.1"
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
