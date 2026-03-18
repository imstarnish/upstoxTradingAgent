import pandas as pd
import pandas_ta as ta

class TrendLogic:
    """
    Professional-grade trend following class.
    Accepts a historical DataFrame (15-minute timeframe) and generates BUY, SELL, or HOLD signals
    based on EMA, VWAP, Supertrend, and ADX. Also provides dynamic position sizing.
    """

    def __init__(self, account_size: float = 100000.0, risk_percentage: float = 0.01):
        self.account_size = account_size
        self.risk_percentage = risk_percentage

    def generate_signal(self, df_15m: pd.DataFrame) -> str:
        """
        Generates a signal based on the following logic:
        1. Only allow BUY if the current price is above the 200-day EMA.
        2. Intraday price must be above the daily VWAP.
        3. The 15-minute Supertrend indicator must flip to bullish.
        4. The ADX (Average Directional Index) must be greater than 25 to confirm trend strength.

        Assumes df_15m has a pandas DatetimeIndex.
        """
        if df_15m is None or df_15m.empty or len(df_15m) < 14:
            return 'HOLD'

        # Make a copy to avoid SettingWithCopyWarning
        df = df_15m.copy()

        # Resample to daily to calculate the 200-day EMA
        daily_df = df.resample('D').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()

        if len(daily_df) < 200:
            return 'HOLD'

        # Calculate 200-day EMA on the daily dataframe
        daily_df['EMA_200'] = ta.ema(daily_df['close'], length=200)

        # Forward fill the daily 200 EMA to the 15-minute timeframe
        df['EMA_200'] = df.index.map(lambda x: daily_df['EMA_200'].reindex([x.floor('D')], method='ffill').iloc[0] if x.floor('D') in daily_df.index else pd.NA)
        df['EMA_200'] = df['EMA_200'].ffill()

        # Calculate daily VWAP
        df['VWAP'] = ta.vwap(high=df['high'], low=df['low'], close=df['close'], volume=df['volume'], anchor="D")

        # Calculate Supertrend on 15m timeframe
        st = ta.supertrend(high=df['high'], low=df['low'], close=df['close'], length=10, multiplier=3.0)
        st_dir_col = [col for col in st.columns if 'SUPERTd' in col][0]
        df['Supertrend_Dir'] = st[st_dir_col]

        # Calculate ADX on 15m timeframe
        adx_res = ta.adx(high=df['high'], low=df['low'], close=df['close'], length=14)
        adx_col = [col for col in adx_res.columns if col.startswith('ADX_')][0]
        df['ADX'] = adx_res[adx_col]

        # Get latest data points
        current_row = df.iloc[-1]
        prev_row = df.iloc[-2]

        # Check if values are NaN
        if pd.isna(current_row['EMA_200']) or pd.isna(current_row['VWAP']) or pd.isna(current_row['Supertrend_Dir']) or pd.isna(current_row['ADX']):
            return 'HOLD'

        current_price = current_row['close']

        # 1. Current price is above the 200-day EMA
        cond_ema = current_price > current_row['EMA_200']

        # 2. Intraday price must be above the daily VWAP
        cond_vwap = current_price > current_row['VWAP']

        # 3. The 15-minute Supertrend indicator must flip to bullish
        cond_supertrend_flip = (current_row['Supertrend_Dir'] > 0) and (prev_row['Supertrend_Dir'] <= 0)

        # 4. The ADX must be greater than 25
        cond_adx = current_row['ADX'] > 25

        if cond_ema and cond_vwap and cond_supertrend_flip and cond_adx:
            return 'BUY'

        elif (current_row['Supertrend_Dir'] < 0) and (prev_row['Supertrend_Dir'] >= 0):
            return 'SELL'

        return 'HOLD'

    def calculate_position_size(self, df: pd.DataFrame) -> float:
        """
        Calculates dynamic position sizing based on a 14-period ATR.
        Ensures risk does not exceed the initialized percentage of the account size.
        """
        if df is None or df.empty or len(df) < 14:
            return 0.0

        # Calculate 14-period ATR
        atr_res = ta.atr(high=df['high'], low=df['low'], close=df['close'], length=14)

        if atr_res is None or atr_res.empty:
            return 0.0

        latest_atr = atr_res.iloc[-1]

        if pd.isna(latest_atr) or latest_atr <= 0:
            return 0.0

        risk_amount = self.account_size * self.risk_percentage

        position_size = risk_amount / latest_atr

        return position_size
