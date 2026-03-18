import asyncio
import logging
import pandas as pd
import datetime
from core.auth import UpstoxAuth
from strategy.trend_logic import TrendLogic
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
        # According to Upstox API v2, historical data endpoint:
        # GET /historical-candle/{instrumentKey}/{interval}/{to_date}/{from_date}
        # interval: 1minute, 30minute, day, etc. For 15 minute, it might be 15minute or 15m.
        # Here we use the history api via the client.
        api_instance = upstox_client.HistoryApi(api_client)

        # We need enough data to calculate a 200-day EMA.
        # A day has ~25 15-min candles (6 hours 15 mins). 200 days * 25 = 5000 candles.
        # The API may have limits, so we would normally fetch a large range or loop.
        # For demonstration of the loop, let's fetch the maximum allowed history.

        # Format dates
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
            # Format: [timestamp, open, high, low, close, volume, oi]
            df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
            df['datetime'] = pd.to_datetime(df['timestamp'])
            df.set_index('datetime', inplace=True)
            df.sort_index(inplace=True)

            # Convert to float
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)

            return df

        else:
            logging.error(f"Failed to fetch data for {instrument_key}: {api_response}")
            return pd.DataFrame()

    except Exception as e:
        logging.error(f"Error fetching data for {instrument_key}: {e}")
        return pd.DataFrame()

async def execute_trade(api_client: upstox_client.ApiClient, instrument_key: str, quantity: int, transaction_type: str):
    """Executes a MARKET order."""
    try:
        api_instance = upstox_client.OrderApi(api_client)
        body = upstox_client.PlaceOrderRequest(
            quantity=int(quantity),
            product="D",  # Delivery
            validity="DAY",
            price=0.0,  # 0 for MARKET order
            tag="string",
            instrument_token=instrument_key,
            order_type="MARKET",
            transaction_type=transaction_type,
            disclosed_quantity=0,
            trigger_price=0.0,
            is_amo=False
        )
        api_response = api_instance.place_order(body)
        logging.info(f"Order executed successfully: {instrument_key} - {transaction_type} {quantity} units. Response: {api_response}")
    except upstox_client.rest.ApiException as e:
        logging.error(f"Exception when calling OrderApi->place_order: {e}")
    except Exception as e:
        logging.error(f"Failed to execute trade for {instrument_key}: {e}")

async def run_bot(api_client: upstox_client.ApiClient):
    """Main asynchronous trading loop."""
    strategy_engine = TrendLogic(account_size=100000.0, risk_percentage=0.01)
    logging.info("Starting trading bot loop...")

    while True:
        try:
            for ticker in TICKERS:
                logging.info(f"Fetching data and evaluating strategy for {ticker}...")

                # Fetch data
                df = await fetch_historical_data(api_client, ticker)

                if df.empty:
                    logging.warning(f"No data received for {ticker}. Skipping.")
                    continue

                # Evaluate strategy
                signal = strategy_engine.generate_signal(df)
                logging.info(f"Signal for {ticker}: {signal}")

                if signal == 'BUY':
                    # Calculate position size
                    position_size = strategy_engine.calculate_position_size(df)
                    quantity = max(1, int(position_size))

                    logging.info(f"BUY signal confirmed for {ticker}. Executing MARKET order for {quantity} shares.")
                    await execute_trade(api_client, ticker, quantity, "BUY")

                elif signal == 'SELL':
                    logging.info(f"SELL signal generated for {ticker}. Executing MARKET order to exit.")
                    # Implement logic to check current holding and sell
                    # For demonstration, executing a sell of 1 unit.
                    await execute_trade(api_client, ticker, 1, "SELL")

        except Exception as e:
            logging.error(f"Unexpected error in trading loop: {e}")

        logging.info(f"Sleeping for {POLL_INTERVAL} seconds...")
        await asyncio.sleep(POLL_INTERVAL)

def main():
    try:
        # Initialize Authentication
        # These should securely come from environment variables in a real scenario
        # Using placeholders for demonstration
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

        # Run async loop
        asyncio.run(run_bot(api_client))

    except Exception as e:
        logging.critical(f"Critical failure in main application: {e}")

if __name__ == "__main__":
    main()
