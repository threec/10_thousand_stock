"""
Stock scoring engine following 直到一万点's methodology.
Weights: 多头排列(40) + 突破新高(25) + 趋势加速(15) + 量价配合(10) + 基本面(10) = 100
"""


def compute_mas(closes):
    """Compute moving averages from closing prices."""
    if len(closes) < 60:
        return None
    return {
        'ma5': sum(closes[-5:]) / 5,
        'ma10': sum(closes[-10:]) / 10,
        'ma20': sum(closes[-20:]) / 20,
        'ma60': sum(closes[-60:]) / 60,
    }


def compute_returns(closes):
    """Compute multi-period returns."""
    if len(closes) < 61:
        return None
    c = closes[-1]
    return {
        'ret5': (c / closes[-6] - 1) * 100 if len(closes) >= 6 else 0,
        'ret10': (c / closes[-11] - 1) * 100 if len(closes) >= 11 else 0,
        'ret20': (c / closes[-21] - 1) * 100 if len(closes) >= 21 else 0,
        'ret60': (c / closes[-61] - 1) * 100 if len(closes) >= 61 else 0,
    }


def analyze_trend(klines, name=''):
    """Classify index/stock trend: 多头/短多/空头/交织."""
    if not klines or len(klines.get('closes', [])) < 60:
        return None

    c = klines['closes']
    current = c[-1]
    mas = compute_mas(c)
    rets = compute_returns(c)

    if not mas or not rets:
        return None

    arrangement = (
        '多头' if (mas['ma5'] > mas['ma10'] > mas['ma20'] and mas['ma20'] > mas['ma60'])
        else '短多' if (mas['ma5'] > mas['ma10'] > mas['ma20'])
        else '空头' if (mas['ma5'] < mas['ma10'] < mas['ma20'] and mas['ma20'] < mas['ma60'])
        else '交织'
    )

    if rets['ret60'] > 5 and arrangement in ('多头', '短多'):
        market_state = '牛市/上升趋势'
    elif rets['ret60'] < -10 and arrangement == '空头':
        market_state = '熊市/下降趋势'
    else:
        market_state = '震荡市'

    return {
        'name': name,
        'current': current,
        'date': klines['dates'][-1],
        **rets,
        **mas,
        'arrangement': arrangement,
        'market_state': market_state,
    }


def score_stock(klines, current_data, sector_name=''):
    """
    Score a stock 0-100 according to the methodology.

    Returns dict with score, reasons, and all computed metrics,
    or None if insufficient data.
    """
    if not klines or len(klines.get('closes', [])) < 60:
        return None

    c = klines['closes']
    h = klines['highs']
    l = klines['lows']
    v = klines['volumes']

    current = current_data.get('current', c[-1]) if current_data else c[-1]
    prev_close = current_data.get('prev_close', c[-2]) if current_data else c[-2]
    chg_pct = (current - prev_close) / prev_close * 100 if prev_close else 0

    # Moving averages
    mas = compute_mas(c)
    if not mas:
        return None

    # Returns
    rets = compute_returns(c)
    if not rets:
        return None

    # Volume
    avg_vol20 = sum(v[-21:-1]) / 20 if len(v) >= 21 else 0
    today_vol = v[-1] if v else 0
    vol_ratio = today_vol / avg_vol20 if avg_vol20 > 0 else 1

    reasons = []
    score = 0

    # --- Category 1: 多头排列 (40 pts max) ---
    is_bullish_full = mas['ma5'] > mas['ma10'] > mas['ma20'] > mas['ma60']
    is_bullish_short = mas['ma5'] > mas['ma10'] > mas['ma20']
    above_ma20 = current > mas['ma20']
    above_ma60 = current > mas['ma60']

    if is_bullish_full:
        score += 40
        reasons.append("完全多头排列")
    elif is_bullish_short and above_ma60:
        score += 32
        reasons.append("短期多头(>MA60)")
    elif is_bullish_short:
        score += 24
        reasons.append("短中期多头排列")
    elif above_ma20 and above_ma60:
        score += 12
        reasons.append("站上20/60日线")
    elif above_ma20:
        score += 6
        reasons.append("站上20日线")

    # --- Category 2: 突破/新高 (25 pts max) ---
    high20 = max(h[-20:])
    high60 = max(h[-60:])
    near_20high = current >= high20 * 0.95
    near_60high = current >= high60 * 0.95
    is_20high_today = current >= high20 and current >= h[-2] * 1.00 if len(h) >= 2 else False
    is_breakout_today = is_20high_today and chg_pct > 1

    if is_breakout_today:
        score += 25
        reasons.append("当日突破20日新高")
    elif near_60high and is_bullish_short:
        score += 20
        reasons.append("接近60日新高+多头")
    elif near_20high:
        score += 15
        reasons.append("接近20日新高")
    elif above_ma20:
        score += 8
        reasons.append("20日线上方")

    # --- Category 3: 趋势加速 (15 pts max) ---
    momentum_score = 0
    if rets['ret5'] > 0:
        momentum_score += 5
    if rets['ret10'] > 0:
        momentum_score += 4
    if rets['ret20'] > 0:
        momentum_score += 3
    if rets['ret60'] > 0:
        momentum_score += 3
    if rets['ret5'] > rets['ret10'] > rets['ret20']:
        momentum_score += 3
        reasons.append("趋势加速中")
    score += min(momentum_score, 15)

    # --- Category 4: 量价配合 (10 pts max) ---
    if vol_ratio > 2.0 and chg_pct > 1:
        score += 10
        reasons.append(f"放量突破(量比{vol_ratio:.1f})")
    elif vol_ratio > 1.5 and chg_pct > 0:
        score += 7
        reasons.append(f"温和放量({vol_ratio:.1f}x)")
    elif vol_ratio > 0.8:
        score += 4
    else:
        score += 1

    # --- Category 5: 基本面代理 (10 pts max) ---
    price = current
    if price > 0:
        if price <= 100:
            score += 5
        low60 = min(l[-60:])
        if current < low60 * 1.3 and rets['ret60'] > 0:
            score += 5
            reasons.append("低位启动")
        elif rets['ret60'] > 20:
            score += 3

    return {
        'code': current_data.get('code', '?'),
        'name': current_data.get('name', '?'),
        'sector': sector_name,
        'price': current,
        'daily_chg': chg_pct,
        **rets,
        **mas,
        'is_bullish': is_bullish_full or is_bullish_short,
        'near_high20': near_20high,
        'vol_ratio': vol_ratio,
        'score': score,
        'reasons': reasons,
        'dates': klines['dates'][-1] if klines.get('dates') else '',
    }


def determine_strategy(score, is_bullish, is_full_bullish, above_ma20, reasons, ret5):
    """
    Determine strategy and action for a holding based on its current data.

    Returns (strategy_text, action) where action is: hold / warn / watch / stop / unknown
    """
    if is_full_bullish and score >= 80:
        return ('完全多头+高分, 继续持有', 'hold')
    elif is_bullish and score >= 70:
        return ('多头排列, 持有观察', 'hold')
    elif is_bullish and score >= 50:
        return ('短期多头但评分一般, 密切关注', 'warn')
    elif not is_bullish and score > 0 and ('站上20日线' in reasons or '站上20/60日线' in reasons):
        return ('非多头但站上20日线, 暂持观望', 'watch')
    elif ret5 < -5:
        return (f'短期走弱(5日{ret5:+.1f}%), 考虑减仓', 'stop')
    elif score == 0:
        return ('该股票不在今日选股范围', 'unknown')
    else:
        return ('趋势不明, 建议观望', 'watch')


def score_sector(stocks_in_sector):
    """Compute weighted sector score from constituent stocks."""
    if not stocks_in_sector:
        return {'score': 0, 'avg_ret5': 0, 'avg_ret10': 0, 'avg_ret20': 0,
                'bull_count': 0, 'breakout_count': 0, 'total_count': 0}

    n = len(stocks_in_sector)
    avg_ret5 = sum(s['ret5'] for s in stocks_in_sector) / n
    avg_ret10 = sum(s['ret10'] for s in stocks_in_sector) / n
    avg_ret20 = sum(s['ret20'] for s in stocks_in_sector) / n
    bull_count = sum(1 for s in stocks_in_sector if s.get('is_bullish'))
    breakout_count = sum(1 for s in stocks_in_sector if s.get('near_high20'))

    score = avg_ret5 * 0.4 + avg_ret10 * 0.3 + avg_ret20 * 0.2

    return {
        'score': score,
        'avg_ret5': avg_ret5, 'avg_ret10': avg_ret10, 'avg_ret20': avg_ret20,
        'bull_count': bull_count, 'breakout_count': breakout_count, 'total_count': n,
    }
