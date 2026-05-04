"""
Daily A-share screener following 直到一万点's methodology.
Steps: Index → Sector → Individual stocks
Data: Sina Finance API (works during holidays for historical data)
"""
import json, os, re, time, urllib.request, sqlite3
from datetime import datetime, timedelta

DATA_DIR = r"D:\stock\data\screener"
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "screener.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS index_daily (
            date TEXT NOT NULL, name TEXT NOT NULL,
            close REAL, ret5 REAL, ret10 REAL, ret20 REAL, ret60 REAL,
            arrangement TEXT, market_state TEXT,
            PRIMARY KEY (date, name)
        );
        CREATE TABLE IF NOT EXISTS sector_daily (
            date TEXT NOT NULL, name TEXT NOT NULL,
            rank INTEGER, score REAL,
            avg_ret5 REAL, avg_ret10 REAL, avg_ret20 REAL,
            bull_count INTEGER, breakout_count INTEGER, total_count INTEGER,
            PRIMARY KEY (date, name)
        );
        CREATE TABLE IF NOT EXISTS stock_daily (
            date TEXT NOT NULL, code TEXT NOT NULL, sector TEXT NOT NULL,
            name TEXT, score INTEGER, price REAL, daily_chg REAL,
            ret5 REAL, ret10 REAL, ret20 REAL, ret60 REAL,
            reasons TEXT, is_bullish INTEGER,
            PRIMARY KEY (date, code, sector)
        );
        CREATE TABLE IF NOT EXISTS kline_cache (
            code TEXT PRIMARY KEY,
            data TEXT, updated_at TEXT
        );
    """)
    conn.commit()
    return conn

def save_to_db(conn, date_str, index_trends, ranked_sectors, all_stocks):
    """Save all screener results to SQLite."""
    c = conn.cursor()
    # Index data
    c.execute("DELETE FROM index_daily WHERE date=?", (date_str,))
    for name, t in index_trends.items():
        c.execute("INSERT INTO index_daily VALUES (?,?,?,?,?,?,?,?,?)",
                  (date_str, name, t['current'], t['ret5'], t['ret10'], t['ret20'], t['ret60'],
                   t['arrangement'], t['market_state']))
    # Sector data
    c.execute("DELETE FROM sector_daily WHERE date=?", (date_str,))
    for rank, (name, s) in enumerate(ranked_sectors, 1):
        c.execute("INSERT INTO sector_daily VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (date_str, name, rank, s['score'],
                   s['avg_ret5'], s['avg_ret10'], s['avg_ret20'],
                   s['bull_count'], s['breakout_count'], s['total']))
    # Stock data
    c.execute("DELETE FROM stock_daily WHERE date=?", (date_str,))
    for s in all_stocks:
        c.execute("INSERT INTO stock_daily VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (date_str, s['code'], s['sector'], s['name'], s['score'],
                   s['price'], s['daily_chg'], s['ret5'], s['ret10'], s['ret20'], s['ret60'],
                   ', '.join(s['reasons']), 1 if s['is_bullish'] else 0))
    conn.commit()

def get_cached_kline(conn, code):
    c = conn.cursor()
    row = c.execute("SELECT data, updated_at FROM kline_cache WHERE code=?", (code,)).fetchone()
    if row:
        try:
            data = json.loads(row[0])
            return {k: v for k, v in data.items()}
        except:
            pass
    return None

def set_cached_kline(conn, code, data):
    conn.execute("INSERT OR REPLACE INTO kline_cache VALUES (?,?,?)",
                 (code, json.dumps(data), datetime.now().strftime('%Y-%m-%d %H:%M')))
    conn.commit()

def fetch(url, headers=None, retries=3, encoding='gbk'):
    if headers is None:
        headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn'}
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read().decode(encoding, errors='replace')
        except:
            if i == retries - 1:
                return None
            time.sleep(1.5)

today = datetime.now()
date_str = today.strftime('%Y-%m-%d')
out = []
conn = init_db()

def w(s):
    out.append(s)
    print(s)

w("=" * 80)
w(f"每日A股选股 — 直到一万点方法论")
w(f"执行时间: {today.strftime('%Y-%m-%d %H:%M')}")
w("=" * 80)

# ================================================================
# STEP 1: 指数定向
# ================================================================
w("\n" + "=" * 60)
w("第一步：指数环境判断")
w("=" * 60)

INDEX_CODES = {
    '上证指数': 'sh000001', '深证成指': 'sz399001', '创业板指': 'sz399006',
    '科创50': 'sh000688', '沪深300': 'sh000300', '上证50': 'sh000016',
    '中证1000': 'sh000852', '中证500': 'sh000905',
}

def get_index_klines(code, count=120):
    """Get index daily K-lines from Sina"""
    url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={code}&scale=240&ma=no&datalen={count}"
    text = fetch(url, encoding='utf-8')
    if not text:
        return None
    try:
        data = json.loads(text)
    except:
        return None
    if not data:
        return None
    result = {'dates': [], 'opens': [], 'closes': [], 'highs': [], 'lows': [], 'volumes': []}
    for d in data:
        result['dates'].append(d['day'])
        result['opens'].append(float(d['open']))
        result['closes'].append(float(d['close']))
        result['highs'].append(float(d['high']))
        result['lows'].append(float(d['low']))
        result['volumes'].append(float(d['volume']))
    return result

def analyze_trend(klines, name):
    if not klines or len(klines['closes']) < 60:
        return None
    c = klines['closes']
    current = c[-1]
    ma5 = sum(c[-5:]) / 5
    ma10 = sum(c[-10:]) / 10
    ma20 = sum(c[-20:]) / 20
    ma60 = sum(c[-60:]) / 60 if len(c) >= 60 else None

    ret5 = (current / c[-6] - 1) * 100 if len(c) >= 6 else 0
    ret10 = (current / c[-11] - 1) * 100 if len(c) >= 11 else 0
    ret20 = (current / c[-21] - 1) * 100 if len(c) >= 21 else 0
    ret60 = (current / c[-61] - 1) * 100 if len(c) >= 61 else 0

    # Trend classification for his methodology
    arrangement = '多头' if (ma5 > ma10 > ma20 and ma60 and ma20 > ma60) else \
                  '短多' if (ma5 > ma10 > ma20) else \
                  '空头' if (ma5 < ma10 < ma20 and ma60 and ma20 < ma60) else '交织'

    # Bull/bear market assessment
    if ret60 > 5 and arrangement in ('多头', '短多'):
        market_state = '牛市/上升趋势'
    elif ret60 < -10 and arrangement == '空头':
        market_state = '熊市/下降趋势'
    else:
        market_state = '震荡市'

    return {
        'name': name, 'current': current, 'date': klines['dates'][-1],
        'ret5': ret5, 'ret10': ret10, 'ret20': ret20, 'ret60': ret60,
        'ma5': ma5, 'ma10': ma10, 'ma20': ma20, 'ma60': ma60,
        'arrangement': arrangement, 'market_state': market_state,
    }

index_trends = {}
for name, code in INDEX_CODES.items():
    k = get_index_klines(code, 120)
    if k:
        t = analyze_trend(k, name)
        if t:
            index_trends[name] = t
            w(f"  {name:8s} 收盘{t['current']:.2f}  {t['ret5']:+.1f}%/{t['ret10']:+.1f}%/{t['ret20']:+.1f}%/{t['ret60']:+.1f}%  "
              f"均线:{t['arrangement']}  状态:{t['market_state']}")
    time.sleep(0.2)

# Overall market verdict
strong_count = sum(1 for t in index_trends.values() if t['ret20'] > 0)
total = len(index_trends)
w(f"\n  综合判断: {strong_count}/{total} 指数20日线上方, 市场整体偏{'强' if strong_count > total/2 else '弱'}")

# ================================================================
# STEP 2: 板块筛选
# ================================================================
w("\n" + "=" * 60)
w("第二步：板块强度筛选")
w("=" * 60)

# Use predefined major sector ETFs as sector proxies
# Each sector = name + list of representative stocks
SECTORS = {
    '半导体': ['sh688981', 'sz002371', 'sh688012', 'sh688072', 'sz300604', 'sz300672',
               'sh600703', 'sh688256', 'sz002049', 'sz002156', 'sh688396', 'sz300661'],
    '光模块/算力': ['sz300308', 'sz300502', 'sz300394', 'sz300570', 'sz002916',
                   'sz300548', 'sh601138', 'sz300638', 'sz300620'],
    '存储/芯片': ['sz300857', 'sz300474', 'sh688525', 'sh688110', 'sz300672',
                 'sh688256', 'sh603986', 'sz002049', 'sz301308'],
    '机器人/智造': ['sz300124', 'sz002396', 'sz300007', 'sz300228', 'sz300354',
                   'sz002527', 'sz300024', 'sh688017', 'sz300660', 'sz300161'],
    '医药/创新药': ['sz300759', 'sh688180', 'sh688266', 'sz000963', 'sz300347',
                   'sh688276', 'sh688235', 'sz002653', 'sh600276'],
    'AI/软件': ['sz300033', 'sh688111', 'sz002230', 'sh688981', 'sz300474',
                'sz300502', 'sh600536', 'sz300624'],
    '新能源/光伏': ['sz300274', 'sh601012', 'sz300750', 'sz002459', 'sz300763',
                   'sz300118', 'sh688599', 'sz300724'],
    '消费/白酒': ['sh600519', 'sz000858', 'sz000568', 'sh600809', 'sz002304',
                 'sh600887', 'sz000895'],
    '金融/券商': ['sz300059', 'sh600030', 'sh601688', 'sz300033', 'sz002673',
                 'sh601211'],
    '国防军工': ['sh600760', 'sh600893', 'sz002013', 'sh688122', 'sz300034',
                'sz300722'],
    '汽车/零部件': ['sh601238', 'sz002594', 'sh600104', 'sz300750', 'sz000625',
                   'sh601633'],
}

def get_stock_current(code):
    """Get current stock price from Sina real-time"""
    url = f"https://hq.sinajs.cn/list={code}"
    text = fetch(url)
    if not text:
        return None
    try:
        parts = text.split('"')[1].split(',')
        if len(parts) > 5:
            return {
                'code': code, 'name': parts[0],
                'open': float(parts[1]), 'prev_close': float(parts[2]),
                'current': float(parts[3]), 'high': float(parts[4]), 'low': float(parts[5]),
                'volume': float(parts[7]) if parts[7] else 0,
                'amount': float(parts[8]) if parts[8] else 0,
            }
    except:
        pass
    return None

def get_stock_klines(code, count=120):
    """Get stock daily K-lines from Sina (code format: sh600519 or sz000858)"""
    url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={code}&scale=240&ma=no&datalen={count}"
    text = fetch(url, encoding='utf-8')
    if not text:
        return None
    try:
        data = json.loads(text)
    except:
        return None
    if not data:
        return None
    result = {'dates': [], 'opens': [], 'closes': [], 'highs': [], 'lows': [], 'volumes': []}
    for d in data:
        result['dates'].append(d['day'])
        result['opens'].append(float(d['open']))
        result['closes'].append(float(d['close']))
        result['highs'].append(float(d['high']))
        result['lows'].append(float(d['low']))
        result['volumes'].append(float(d['volume']))
    return result

def score_stock(klines, current_data, sector_name):
    """Score a stock according to 直到一万点's criteria.
    Key factors (weighted):
    1. 多头排列 (均线向上发散): 40%
    2. 接近新高 / 突破形态: 25%
    3. 短期强于长期 (趋势加速): 15%
    4. 量价配合 (放量上涨): 10%
    5. 基本面辅助 (PE): 10%
    """
    if not klines or len(klines['closes']) < 60:
        return None

    c = klines['closes']
    h = klines['highs']
    l = klines['lows']
    v = klines['volumes']
    current = current_data['current'] if current_data else c[-1]
    prev_close = current_data['prev_close'] if current_data else c[-2]

    chg_pct = (current - prev_close) / prev_close * 100

    # Moving averages
    ma5 = sum(c[-5:]) / 5
    ma10 = sum(c[-10:]) / 10
    ma20 = sum(c[-20:]) / 20
    ma60 = sum(c[-60:]) / 60

    # Returns over multiple periods
    ret5 = (current / c[-6] - 1) * 100 if len(c) >= 6 else 0
    ret10 = (current / c[-11] - 1) * 100 if len(c) >= 11 else 0
    ret20 = (current / c[-21] - 1) * 100 if len(c) >= 21 else 0
    ret60 = (current / c[-61] - 1) * 100 if len(c) >= 61 else 0

    # Volume analysis
    avg_vol20 = sum(v[-21:-1]) / 20 if len(v) >= 21 else 0
    today_vol = v[-1] if len(v) > 0 else 0
    vol_ratio = today_vol / avg_vol20 if avg_vol20 > 0 else 1

    # Daily change
    daily_chg = chg_pct

    reasons = []
    score = 0

    # --- 1. 多头排列 (40 points max) ---
    is_bullish_full = ma5 > ma10 > ma20 > ma60  # 完全多头排列
    is_bullish_short = ma5 > ma10 > ma20  # 短期多头
    above_ma20 = current > ma20
    above_ma60 = current > ma60

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

    # --- 2. 突破/新高 (25 points max) ---
    high20 = max(h[-20:])
    high60 = max(h[-60:])
    near_20high = current >= high20 * 0.95
    near_60high = current >= high60 * 0.95
    is_20high_today = current >= high20 and current >= h[-2] * 1.00
    is_breakout_today = is_20high_today and daily_chg > 1

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

    # --- 3. 趋势加速 (15 points max) ---
    momentum_score = 0
    if ret5 > 0:
        momentum_score += 5
    if ret10 > 0:
        momentum_score += 4
    if ret20 > 0:
        momentum_score += 3
    if ret60 > 0:
        momentum_score += 3
    # Bonus for acceleration (short > longer)
    if ret5 > ret10 > ret20 :
        momentum_score += 3
        reasons.append("趋势加速中")
    score += min(momentum_score, 15)

    # --- 4. 量价配合 (10 points max) ---
    if vol_ratio > 2.0 and daily_chg > 1:
        score += 10
        reasons.append(f"放量突破(量比{vol_ratio:.1f})")
    elif vol_ratio > 1.5 and daily_chg > 0:
        score += 7
        reasons.append(f"温和放量({vol_ratio:.1f}x)")
    elif vol_ratio > 0.8:
        score += 4
    else:
        score += 1

    # --- 5. 基本面 (10 points max) ---
    # Since we don't have PE easily, use price position as proxy
    # Lower price stocks in uptrend = potentially more room
    price = current
    if price > 0:
        is_high_price = price > 100  # arbitrary threshold
        if not is_high_price:
            score += 5
        # Check if it's near 52-week or historical lows (value)
        low60 = min(l[-60:])
        if current < low60 * 1.3 and ret60 > 0:
            score += 5
            reasons.append("低位启动")
        elif ret60 > 20:
            score += 3

    return {
        'code': current_data['code'],
        'name': current_data.get('name', '?'),
        'sector': sector_name,
        'price': current,
        'daily_chg': daily_chg,
        'ret5': ret5, 'ret10': ret10, 'ret20': ret20, 'ret60': ret60,
        'ma5': ma5, 'ma10': ma10, 'ma20': ma20, 'ma60': ma60,
        'is_bullish': is_bullish_full or is_bullish_short,
        'near_high20': near_20high,
        'vol_ratio': vol_ratio,
        'score': score,
        'reasons': reasons,
        'dates': klines['dates'][-1],
    }

# ================================================================
# RUN THE SCREEN
# ================================================================
w("\n正在扫描各板块...\n")

all_stocks = []
sector_scores = {}

for sector_name, codes in SECTORS.items():
    w(f"  [{sector_name}] 扫描 {len(codes)} 只...")
    sector_stocks = []
    sector_ret5, sector_ret10, sector_ret20 = [], [], []

    for code in codes:
        current = get_stock_current(code)
        if not current:
            continue
        klines = get_stock_klines(code, 120)
        if not klines:
            continue
        result = score_stock(klines, current, sector_name)
        if result:
            sector_stocks.append(result)
            sector_ret5.append(result['ret5'])
            sector_ret10.append(result['ret10'])
            sector_ret20.append(result['ret20'])
        time.sleep(0.15)

    if sector_stocks:
        # Sector average performance
        avg_ret5 = sum(sector_ret5) / len(sector_ret5)
        avg_ret10 = sum(sector_ret10) / len(sector_ret10)
        avg_ret20 = sum(sector_ret20) / len(sector_ret20)
        sector_score = avg_ret5 * 0.4 + avg_ret10 * 0.3 + avg_ret20 * 0.2

        bull_count = sum(1 for s in sector_stocks if s['is_bullish'])
        breakout_count = sum(1 for s in sector_stocks if s['near_high20'])

        sector_scores[sector_name] = {
            'score': sector_score,
            'avg_ret5': avg_ret5, 'avg_ret10': avg_ret10, 'avg_ret20': avg_ret20,
            'stocks': sector_stocks,
            'bull_count': bull_count, 'breakout_count': breakout_count,
            'total': len(sector_stocks),
        }
        all_stocks.extend(sector_stocks)
        w(f"    均涨{avg_ret5:+.1f}%/{avg_ret10:+.1f}%/{avg_ret20:+.1f}%  "
          f"多头{bull_count}只 近高{breakout_count}只 共{len(sector_stocks)}只")
    time.sleep(0.3)

# ---- Display Results ----

# 1. Sector Ranking
w("\n" + "=" * 60)
w("【板块强度排名 (加权: 5日40%+10日30%+20日20%)】")
w("=" * 60)

ranked_sectors = sorted(sector_scores.items(), key=lambda x: -x[1]['score'])
for i, (name, s) in enumerate(ranked_sectors):
    bar = "█" * max(1, int(s['score'] * 2) if s['score'] > 0 else 0)
    w(f"  {i+1:2d}. {name:12s} 得分{s['score']:+6.1f}  "
      f"5日{s['avg_ret5']:+.1f}% 10日{s['avg_ret10']:+.1f}% 20日{s['avg_ret20']:+.1f}%  "
      f"多头{s['bull_count']}/{s['total']}  {bar}")

# 2. Individual Stock Ranking
w("\n" + "=" * 60)
w("【个股综合评分 TOP 40】")
w("=" * 60)

all_stocks.sort(key=lambda x: -x['score'])

w(f"  {'排名':<4s} {'名称':<10s} {'代码':<8s} {'板块':<12s} {'得分':>4s} "
  f"{'涨跌':>7s} {'5日':>7s} {'10日':>7s} {'20日':>7s} {'价格':>7s}  入选理由")
w("  " + "-" * 120)

for i, s in enumerate(all_stocks[:40]):
    w(f"  {i+1:<4d} {s['name']:<10s} {s['code']:<8s} {s['sector']:<12s} {s['score']:>4d} "
      f"{s['daily_chg']:>+6.1f}% {s['ret5']:>+6.1f}% {s['ret10']:>+6.1f}% {s['ret20']:>+6.1f}% "
      f"{s['price']:>7.2f}  {', '.join(s['reasons'][:4])}")

# 3. Strongest sector's top picks (his "主线")
w("\n" + "=" * 60)
w("【主线方向精选 — 最强3个板块的前5名】")
w("=" * 60)

for i, (sector_name, s) in enumerate(ranked_sectors[:3]):
    w(f"\n  [{sector_name}] — 板块得分{s['score']:+.1f}")
    top = sorted(s['stocks'], key=lambda x: -x['score'])[:5]
    for j, st in enumerate(top):
        w(f"    {j+1}. {st['name']}({st['code']}) 得分{st['score']} "
          f"日{st['daily_chg']:+.1f}% 周{st['ret5']:+.1f}% | {', '.join(st['reasons'][:3])}")

# 4. Market summary & recommended action
w("\n" + "=" * 60)
w("【每日总结 & 操作建议】")
w("=" * 60)

# Market state
up_indices = sum(1 for t in index_trends.values() if t['ret20'] > 0)
w(f"\n  市场状态: {up_indices}/{len(index_trends)} 指数在20日线上方")

top3_sectors = [name for name, _ in ranked_sectors[:3]]
w(f"  主线方向: {' > '.join(top3_sectors)}")

w(f"  最强个股: {all_stocks[0]['name']}({all_stocks[0]['code']}) "
  f"得分{all_stocks[0]['score']} | {', '.join(all_stocks[0]['reasons'][:3])}")

# Count high-scoring stocks
high_score = [s for s in all_stocks if s['score'] >= 60]
w(f"  高分个股(≥60): {len(high_score)}只")
if high_score:
    for s in high_score[:10]:
        w(f"    {s['name']}({s['code']}) [{s['sector']}] {s['score']}分")

# His style recommendation
bull_period = any(t['market_state'] == '牛市/上升趋势' for t in index_trends.values())
if bull_period and len(high_score) >= 5:
    w(f"\n  操作建议: 市场处于上升趋势，{len(high_score)}只个股符合买入条件。")
    w(f"  可重点关注 {', '.join(top3_sectors)} 方向的强势个股。")
    w(f"  按方法论: 在指数做好准备的条件下买入最强板块的突破个股。")
elif len(high_score) >= 3:
    w(f"\n  操作建议: 市场中性偏强，结构性机会存在。重点关注 {top3_sectors[0]} 方向。")
else:
    w(f"\n  操作建议: 市场信号不够明确，高分个股不多。建议等待更好的机会或降低仓位。")

# ================================================================
# SAVE RESULTS
# ================================================================

# Daily result
result = {
    'date': date_str,
    'market_state': {name: t['market_state'] for name, t in index_trends.items()},
    'sector_ranking': [(name, s['score'], s['avg_ret5'], s['avg_ret10'], s['avg_ret20'])
                       for name, s in ranked_sectors],
    'top_stocks': [{
        'name': s['name'], 'code': s['code'], 'sector': s['sector'],
        'score': s['score'], 'price': s['price'],
        'daily_chg': s['daily_chg'], 'ret5': s['ret5'], 'ret10': s['ret10'],
        'ret20': s['ret20'], 'reasons': s['reasons'],
    } for s in all_stocks[:30]],
    'index_data': {name: {'close': t['current'], 'ret20': t['ret20'],
                    'arrangement': t['arrangement']}
                   for name, t in index_trends.items()},
}

# Save daily result
daily_file = os.path.join(DATA_DIR, f"daily_{date_str}.json")
with open(daily_file, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

# Save latest
latest_file = os.path.join(DATA_DIR, "latest.json")
with open(latest_file, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

# Save to SQLite database
save_to_db(conn, date_str, index_trends, ranked_sectors, all_stocks)
conn.close()

# Save markdown summary
md_file = os.path.join(DATA_DIR, f"daily_{date_str}.md")
md_lines = []
md_lines.append(f"# 每日选股报告 — {date_str}")
md_lines.append("")
md_lines.append("## 市场状态")
for name, t in index_trends.items():
    md_lines.append(f"- **{name}**: {t['current']:.2f} | "
                    f"5日{t['ret5']:+.1f}% 10日{t['ret10']:+.1f}% 20日{t['ret20']:+.1f}% | {t['market_state']}")
md_lines.append("")
md_lines.append("## 板块强度排名")
for i, (name, s) in enumerate(ranked_sectors):
    md_lines.append(f"{i+1}. **{name}** — 得分{s['score']:+.1f} "
                    f"({s['avg_ret5']:+.1f}%/{s['avg_ret10']:+.1f}%/{s['avg_ret20']:+.1f}%)")
md_lines.append("")
md_lines.append("## 精选个股 TOP 20")
md_lines.append("| 排名 | 名称 | 代码 | 板块 | 得分 | 日涨跌 | 5日 | 10日 | 20日 | 价格 | 理由 |")
md_lines.append("|------|------|------|------|------|--------|-----|-----|-----|------|------|")
for i, s in enumerate(all_stocks[:20]):
    md_lines.append(f"| {i+1} | {s['name']} | {s['code']} | {s['sector']} | {s['score']} | "
                    f"{s['daily_chg']:+.1f}% | {s['ret5']:+.1f}% | {s['ret10']:+.1f}% | "
                    f"{s['ret20']:+.1f}% | {s['price']:.2f} | {', '.join(s['reasons'][:3])} |")

with open(md_file, 'w', encoding='utf-8') as f:
    f.write('\n'.join(md_lines))

# Also save a text output
txt_file = os.path.join(DATA_DIR, f"result_{date_str}.txt")
with open(txt_file, 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))

print(f"\n结果已保存:")
print(f"  JSON: {daily_file}")
print(f"  Markdown: {md_file}")
print(f"  文本: {txt_file}")
