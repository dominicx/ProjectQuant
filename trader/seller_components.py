import pandas as pd
import talib as ta
from typing import Dict, Optional

from xtquant.xttype import XtPosition

from tools.utils_basic import get_limit_up_price
from trader.seller import BaseSeller


# ================================
# 根据建仓价的下跌比例严格绝对止损
# ================================
class HardSeller(BaseSeller):
    def __init__(self, strategy_name, delegate, parameters):
        BaseSeller.__init__(self, strategy_name, delegate, parameters)

        print('硬性卖出策略', end=' ')
        self.earn_limit = parameters.earn_limit
        self.risk_limit = parameters.risk_limit
        self.risk_tight = parameters.risk_tight

    def check_sell(self, code: str, quote: Dict, curr_date: str, curr_time: str, position: XtPosition,
                   held_day: int, max_price: Optional[float], history: Optional[pd.DataFrame]) -> bool:

        if held_day > 0:
            curr_price = quote['lastPrice']
            cost_price = position.open_price
            sell_volume = position.can_use_volume
            switch_lower = cost_price * (self.risk_limit + held_day * self.risk_tight)

            if curr_price <= switch_lower:
                self.order_sell(code, quote, sell_volume, '绝对止损')
                return True
            elif curr_price >= cost_price * self.earn_limit:
                self.order_sell(code, quote, sell_volume, '绝对止盈')
                return True


# ================================
# 盈利未达预期则卖出换仓
# ================================
class SwitchSeller(BaseSeller):
    def __init__(self, strategy_name, delegate, parameters):
        BaseSeller.__init__(self, strategy_name, delegate, parameters)

        print('换仓卖出策略', end=' ')
        self.switch_hold_days = parameters.switch_hold_days
        self.switch_begin_time = parameters.switch_begin_time
        self.switch_demand_daily_up = parameters.switch_demand_daily_up

    def check_sell(self, code: str, quote: Dict, curr_date: str, curr_time: str, position: XtPosition,
                   held_day: int, max_price: Optional[float], history: Optional[pd.DataFrame]) -> bool:

        if held_day > self.switch_hold_days and curr_time >= self.switch_begin_time:
            curr_price = quote['lastPrice']
            cost_price = position.open_price
            sell_volume = position.can_use_volume
            switch_upper = cost_price * (1 + held_day * self.switch_demand_daily_up)

            if curr_price < switch_upper:  # 未满足盈利目标的仓位
                self.order_sell(code, quote, sell_volume, '换仓卖单')
                return True

        return False


# ================================
# 历史最高价回落比例止盈
# ================================
class FallSeller(BaseSeller):
    def __init__(self, strategy_name, delegate, parameters):
        BaseSeller.__init__(self, strategy_name, delegate, parameters)

        print('回落卖出策略', end=' ')
        self.fall_from_top = parameters.fall_from_top

    def check_sell(self, code: str, quote: Dict, curr_date: str, curr_time: str, position: XtPosition,
                   held_day: int, max_price: Optional[float], history: Optional[pd.DataFrame]) -> bool:

        if max_price is not None:
            if held_day > 0:
                curr_price = quote['lastPrice']
                cost_price = position.open_price
                sell_volume = position.can_use_volume

                for inc_min, inc_max, fall_threshold in self.fall_from_top:  # 逐级回落卖出
                    if (cost_price * inc_min <= max_price < cost_price * inc_max) \
                            and curr_price < max_price * (1 - fall_threshold):
                        self.order_sell(code, quote, sell_volume, f'涨{int((inc_min - 1) * 100)}%回落')
                        return True

        return False


# ================================
# 涨幅回撤百分止盈
# ================================
class ReturnSeller(BaseSeller):
    def __init__(self, strategy_name, delegate, parameters):
        BaseSeller.__init__(self, strategy_name, delegate, parameters)

        print('回撤卖出策略', end=' ')
        self.return_of_profit = parameters.return_of_profit

    def check_sell(self, code: str, quote: Dict, curr_date: str, curr_time: str, position: XtPosition,
                   held_day: int, max_price: Optional[float], history: Optional[pd.DataFrame]) -> bool:

        if max_price is not None:
            if held_day > 0:
                curr_price = quote['lastPrice']
                cost_price = position.open_price
                sell_volume = position.can_use_volume

                for inc_min, inc_max, fall_percentage in self.return_of_profit:  # 逐级回落止盈
                    if (cost_price * inc_min <= max_price < cost_price * inc_max) \
                            and curr_price < max_price - (max_price - cost_price) * fall_percentage:
                        self.order_sell(code, quote, sell_volume, f'涨{int((inc_min - 1) * 100)}%止盈')
                        return True

        return False


# ================================
# 尾盘涨停卖出
# ================================
class TailCapSeller(BaseSeller):
    def __init__(self, strategy_name, delegate, parameters):
        BaseSeller.__init__(self, strategy_name, delegate, parameters)

        print('回撤卖出策略', end=' ')
        self.tail_start_minute = '14:30'

    def check_sell(self, code: str, quote: Dict, curr_date: str, curr_time: str, position: XtPosition,
                   held_day: int, max_price: Optional[float], history: Optional[pd.DataFrame]) -> bool:

        if history is not None:
            if held_day > 0 and curr_time >= self.tail_start_minute:
                sell_volume = position.can_use_volume
                curr_price = quote['lastPrice']
                last_close = history['close'].values[-1]

                if curr_price >= get_limit_up_price(code, last_close):
                    self.order_sell(code, quote, sell_volume, '尾盘涨停')
                    return True

        return False


# ================================
# 开仓日当天指标尾盘止损
# ================================
class OpenDaySeller(BaseSeller):
    def __init__(self, strategy_name, delegate, parameters):
        BaseSeller.__init__(self, strategy_name, delegate, parameters)
        print('开仓日K线止损策略', end=' ')
        self.open_low_rate = parameters.open_low_rate
        self.open_vol_rate = parameters.open_vol_rate
        self.tail_vol_time = parameters.tail_vol_time

    def check_sell(self, code: str, quote: Dict, curr_date: str, curr_time: str, position: XtPosition,
                   held_day: int, max_price: Optional[float], history: Optional[pd.DataFrame]) -> bool:

        if history is not None:
            if 0 < held_day < len(history):
                sell_volume = position.can_use_volume
                curr_price = quote['lastPrice']
                open_day_low = history['low'].values[-held_day] * self.open_low_rate

                # 建仓日新低破掉卖
                if curr_price < open_day_low:
                    self.order_sell(code, quote, sell_volume, '建日破低')
                    return True

                # 建仓日尾盘缩量卖出
                if curr_time >= self.tail_vol_time and curr_price < get_limit_up_price(code, quote['lastClose']):
                    curr_volume = quote['volume']
                    open_day_volume = history['volume'].values[-held_day] * self.open_vol_rate
                    if curr_volume < open_day_volume:
                        self.order_sell(code, quote, sell_volume, '建日缩量')
                        return True

# ================================
# 跌破均线卖出
# ================================
class MASeller(BaseSeller):
    def __init__(self, strategy_name, delegate, parameters):
        BaseSeller.__init__(self, strategy_name, delegate, parameters)

        print(f'跌破{parameters.ma_above}日均线卖出策略', end=' ')
        self.ma_above = parameters.ma_above

    def check_sell(self, code: str, quote: Dict, curr_date: str, curr_time: str, position: XtPosition,
                   held_day: int, max_price: Optional[float], history: Optional[pd.DataFrame]) -> bool:

        if history is not None:
            if held_day > 0:
                sell_volume = position.can_use_volume

                curr_price = quote['lastPrice']
                curr_vol = quote['volume']

                df = history._append({
                    'datetime': curr_date,
                    'open': quote['open'],
                    'high': quote['high'],
                    'low': quote['low'],
                    'close': curr_price,
                    'volume': curr_vol,
                    'amount': quote['amount'],
                }, ignore_index=True)

                ma_values = ta.MA(df.close.tail(self.ma_above + 1), timeperiod=self.ma_above)
                ma_value = ma_values.values[-1]

                if curr_price < ma_value - 0.01:
                    self.order_sell(code, quote, sell_volume, '破均卖单')
                    return True

        return False


# ================================
# CCI 冲高回落卖出
# ================================
class CCISeller(BaseSeller):
    def __init__(self, strategy_name, delegate, parameters):
        BaseSeller.__init__(self, strategy_name, delegate, parameters)

        print('CCI卖出策略', end=' ')
        self.cci_upper = parameters.cci_upper
        self.cci_lower = parameters.cci_lower

    def check_sell(self, code: str, quote: Dict, curr_date: str, curr_time: str, position: XtPosition,
                   held_day: int, max_price: Optional[float], history: Optional[pd.DataFrame]) -> bool:

        if history is not None:
            if held_day > 0 and int(curr_time[-2:]) % 5 == 0:  # 每隔5分钟 CCI 卖出
                sell_volume = position.can_use_volume

                curr_price = quote['lastPrice']
                curr_vol = quote['volume']

                df = history._append({
                    'datetime': curr_date,
                    'open': quote['open'],
                    'high': quote['high'],
                    'low': quote['low'],
                    'close': curr_price,
                    'volume': curr_vol,
                    'amount': quote['amount'],
                }, ignore_index=True)

                df['CCI'] = ta.CCI(df['high'], df['low'], df['close'], timeperiod=14)
                cci = df['CCI'].tail(2).values

                if cci[0] > self.cci_lower > cci[1]:  # CCI 下穿
                    self.order_sell(code, quote, sell_volume, '低CCI卖')
                    return True

                if cci[0] < self.cci_upper < cci[1]:  # CCI 上穿
                    self.order_sell(code, quote, sell_volume, '高CCI卖')
                    return True

        return False


# ================================
# 次日成交量萎缩卖出
# ================================
class VolumeDropSeller(BaseSeller):
    def __init__(self, strategy_name, delegate, parameters):
        BaseSeller.__init__(self, strategy_name, delegate, parameters)

        print('次缩卖出策略', end=' ')
        self.next_volume_dec_threshold = parameters.vol_dec_thre
        self.next_volume_dec_minute = parameters.vol_dec_time
        self.next_volume_dec_limit = parameters.vol_dec_limit

    def check_sell(self, code: str, quote: Dict, curr_date: str, curr_time: str, position: XtPosition,
                   held_day: int, max_price: Optional[float], history: Optional[pd.DataFrame]) -> bool:

        if history is not None:
            cost_price = position.open_price
            sell_volume = position.can_use_volume

            prev_close = quote['lastClose']
            curr_price = quote['lastPrice']
            curr_vol = quote['volume']

            # 次缩止盈：开盘至今成交量相比买入当日总成交量，缩量达标盈利则卖出，除非涨停
            if held_day > 0 and curr_time == self.next_volume_dec_minute:
                open_vol = history['volume'].values[-held_day]
                if curr_vol < open_vol * self.next_volume_dec_threshold \
                        and cost_price < curr_price < prev_close * self.next_volume_dec_limit:
                    self.order_sell(code, quote, sell_volume, '次日缩量')
                    return True

        return False


# ================================
# 三倍量当天最低止损
# ================================
# TODO


