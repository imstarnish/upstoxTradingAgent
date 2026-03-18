import pandas as pd
import pandas_ta as ta

class TrendLogic:
    """
    Professional-grade trend following class.
    Accepts a historical DataFrame (15-minute timeframe) and generates BUY, SELL, or HOLD signals
    based on 15m EMA, VWAP, Supertrend, and ADX. Also provides dynamic, capital-aware position sizing.
    """

    def __init__(self, account_size: float = 100000.0, risk_percentage: float = 0.01):
        self.account_size = account_size
        self.risk_percentage = risk_percentage

    def generate_signal(self, df_15m: pd.DataFrame) -> str:
        if df_15m is None or df_15m.empty or len(df_15m) < 200:
            return 'HOLD'

        df = df_15m.copy()

        # 1. Calculate 200 EMA on the 15-minute timeframe (Requires ~8 days of data)
        df['EMA_200'] = ta.ema(df['close'], length=200)

        # 2. Calculate Intraday VWAP (Anchored daily natively by pandas-ta for datetime index)
        df['VWAP'] = ta.vwap(high=df['high'], low=df['low'], close=df['close'], volume=df['volume'])

        # 3. Calculate Supertrend on 15m timeframe
        st = ta.supertrend(high=df['high'], low=df['low'], close=df['close'], length=10, multiplier=3.0)
        st_dir_col = [col for col in st.columns if 'SUPERTd' in col][0]
        df['Supertrend_Dir'] = st[st_dir_col]

        # 4. Calculate ADX on 15m timeframe
        adx_res = ta.adx(high=df['high'], low=df['low'], close=df['close'], length=14)
        adx_col = [col for col in adx_res.columns if col.startswith('ADX_')][0]
        df['ADX'] = adx_res[adx_col]

        # Use the last FULLY CLOSED candle to avoid repainting, and the one before it for crossovers
        closed_candle = df.iloc[-2]
        prev_candle = df.iloc[-3]
        
        # We check the current price against the established indicators
        current_price = df.iloc[-1]['close']

        if pd.isna(closed_candle['EMA_200']) or pd.isna(closed_candle['VWAP']) or pd.isna(closed_candle['Supertrend_Dir']) or pd.isna(closed_candle['ADX']):
            return 'HOLD'

        # Conditions based on the closed candle metrics to prevent false signals
        cond_ema = current_price > closed_candle['EMA_200']
        cond_vwap = current_price > closed_candle['VWAP']
        cond_adx = closed_candle['ADX'] > 25
        
        # Supertrend flip must be locked in on closed candles
        cond_supertrend_flip = (closed_candle['Supertrend_Dir'] > 0) and (prev_candle['Supertrend_Dir'] <= 0)

        if cond_ema and cond_vwap and cond_supertrend_flip and cond_adx:
            return 'BUY'

        # SELL condition: Supertrend flips bearish on a closed candle
        elif (closed_candle['Supertrend_Dir'] < 0) and (prev_candle['Supertrend_Dir'] >= 0):
            return 'SELL'

        return 'HOLD'

    def calculate_position_size(self, df: pd.DataFrame) -> float:
        """
        Calculates dynamic position sizing based on a 14-period ATR.
        Strictly caps the size so it does not exceed total account capital.
        """
        if df is None or df.empty or len(df) < 14:
            return 0.0

        atr_res = ta.atr(high=df['high'], low=df['low'], close=df['close'], length=14)
        latest_atr = atr_res.iloc[-2] # Use closed candle ATR

        if pd.isna(latest_atr) or latest_atr <= 0:
            return 0.0

        current_price = df.iloc[-1]['close']
        risk_amount = self.account_size * self.risk_percentage
        
        # Calculate how many shares we can buy based on risk
        risk_based_shares = risk_amount / latest_atr
        
        # Calculate the absolute maximum shares we can afford
        max_affordable_shares = self.account_size / current_price

        # The position size is the smaller of the two
        final_position_size = min(risk_based_shares, max_affordable_shares)

        return final_position_size
