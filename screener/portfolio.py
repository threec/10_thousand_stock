"""
Portfolio and watchlist management + web data export.
"""
import json, sqlite3, os
from datetime import datetime

DB_PATH = r"D:\stock\data\screener\screener.db"
WEB_DIR = r"D:\stock\data\web"

from scoring import determine_strategy


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _dedup_stocks(rows):
    """Deduplicate stock_daily rows by code, keeping highest score."""
    seen = {}
    for r in rows:
        code = r['code']
        if code not in seen or (r.get('score', 0) or 0) > (seen[code].get('score', 0) or 0):
            seen[code] = r
    return list(seen.values())


def export_portfolio_json():
    """Generate portfolio.json with live strategy data from signal engine."""
    conn = _conn()
    date_str = datetime.now().strftime('%Y-%m-%d')

    # Get raw stock data for today (may have duplicates per code due to multi-sector)
    stock_rows = [dict(r) for r in conn.execute(
        "SELECT code, sector, name, score, price, daily_chg, ret5, ret10, ret20, ret60, is_bullish, reasons "
        "FROM stock_daily WHERE date=? ORDER BY score DESC",
        (date_str,)
    ).fetchall()]
    stock_map = {s['code']: s for s in _dedup_stocks(stock_rows)}

    # Get portfolio holdings
    holdings = [dict(r) for r in conn.execute(
        "SELECT * FROM portfolio WHERE active=1 ORDER BY id"
    ).fetchall()]

    portfolio_data = []
    for h in holdings:
        s = stock_map.get(h['code'], {})
        entry = h.get('entry_price', 0) or 0
        current = s.get('price', 0) or 0
        ret_pct = ((current - entry) / entry * 100) if entry else 0
        reasons = s.get('reasons', '') or ''
        is_bullish = s.get('is_bullish', 0)
        score = s.get('score', 0) or 0
        is_full_bullish = '完全多头排列' in reasons
        above_ma20 = '站上20日线' in reasons or '站上20/60日线' in reasons
        ret5 = s.get('ret5', 0) or 0

        strategy, action = determine_strategy(score, is_bullish, is_full_bullish,
                                               above_ma20, reasons, ret5)

        portfolio_data.append({
            'id': h['id'], 'code': h['code'], 'name': h.get('name', '?'),
            'entry_price': entry, 'entry_date': h.get('entry_date', ''),
            'current_price': current, 'return_pct': round(ret_pct, 1),
            'score': score, 'is_bullish': bool(is_bullish),
            'reasons': reasons,
            'ret5': s.get('ret5', 0) or 0,
            'ret20': s.get('ret20', 0) or 0,
            'daily_chg': s.get('daily_chg', 0) or 0,
            'strategy': strategy, 'action': action,
            'stop_method': h.get('stop_loss_method', 'ma10'),
            'entry_reason': h.get('entry_reason', ''),
        })

    # Get watchlist with deduplicated live data
    watchlist_rows = [dict(r) for r in conn.execute(
        "SELECT * FROM watchlist ORDER BY added_date"
    ).fetchall()]

    watchlist_data = []
    for w in watchlist_rows:
        s = stock_map.get(w['code'], {})
        score = s.get('score', 0) or 0
        alert = w.get('alert_score', 70) or 70
        reasons = s.get('reasons', '') or ''
        current_price = s.get('price', 0) or 0
        watched_price = w.get('watched_price', 0) or 0
        watch_ret = ((current_price - watched_price) / watched_price * 100) if watched_price else None

        watchlist_data.append({
            'id': w['id'], 'code': w['code'], 'name': w.get('name', '?'),
            'score': score, 'price': current_price,
            'ret5': s.get('ret5', 0) or 0, 'ret20': s.get('ret20', 0) or 0,
            'is_bullish': bool(s.get('is_bullish', 0)),
            'reasons': reasons,
            'alert_score': alert,
            'ready': score >= alert,
            'target_price': w.get('target_price', 0) or 0,
            'watched_price': watched_price,
            'watch_return': round(watch_ret, 1) if watch_ret is not None else None,
            'watch_reason': w.get('watch_reason', ''),
        })

    # Get today's signals (enriched with stock data)
    signals_raw = [dict(r) for r in conn.execute(
        "SELECT * FROM daily_signals WHERE date=? ORDER BY id", (date_str,)
    ).fetchall()]

    def _enrich_signal(s):
        """Add score, price, sector and Chinese strength label from stock data."""
        stock = stock_map.get(s['code'], {})
        s['score'] = stock.get('score', 0) or 0
        s['price'] = stock.get('price', 0) or 0
        s['sector'] = stock.get('sector', '') or ''
        s['daily_chg'] = stock.get('daily_chg', 0) or 0
        s['ret5'] = stock.get('ret5', 0) or 0
        s['ret20'] = stock.get('ret20', 0) or 0
        s['is_bullish'] = bool(stock.get('is_bullish', 0))
        # Map strength to Chinese
        zh = {'strong': '强', 'medium': '中', 'weak': '弱'}
        s['strength_zh'] = zh.get(s.get('strength', ''), s.get('strength', ''))
        return s

    signals = [_enrich_signal(s) for s in signals_raw]

    # Sort: buy signals by score desc, others keep original order
    buy_signals = sorted([s for s in signals if s['type'] == 'buy'],
                         key=lambda s: -s['score'])
    sell_signals = [s for s in signals if s['type'] == 'sell']
    sector_signals = [s for s in signals if s['type'] == 'sector']
    position_signals = [s for s in signals if s['type'] == 'position']

    # Get market summary
    index_rows = [dict(r) for r in conn.execute(
        "SELECT * FROM index_daily WHERE date=?", (date_str,)
    ).fetchall()]
    strong_count = sum(1 for r in index_rows if r.get('ret20', 0) > 0)
    states = [r.get('market_state', '') for r in index_rows]
    dominant = max(set(states), key=states.count) if states else '震荡市'

    top_sector_row = conn.execute(
        "SELECT name, score FROM sector_daily WHERE date=? ORDER BY rank LIMIT 1", (date_str,)
    ).fetchone()
    top_sector = dict(top_sector_row) if top_sector_row else {'name': '', 'score': 0}

    sectors = [dict(r) for r in conn.execute(
        "SELECT name, rank, score, avg_ret5, avg_ret10, avg_ret20 FROM sector_daily WHERE date=? ORDER BY rank",
        (date_str,)
    ).fetchall()]

    conn.close()

    output = {
        'date': date_str,
        'generated': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'market': {
            'state': dominant,
            'strong_count': strong_count,
            'total_indices': len(index_rows),
            'top_sector': top_sector.get('name', ''),
            'top_sector_score': top_sector.get('score', 0),
            'indices': [{'name': r['name'], 'close': r['close'], 'ret20': r['ret20'],
                         'arrangement': r['arrangement'], 'market_state': r['market_state']}
                        for r in index_rows],
        },
        'sectors': sectors,
        'portfolio': portfolio_data,
        'watchlist': watchlist_data,
        'signals': {
            'buy': buy_signals,
            'sell': sell_signals,
            'sector': sector_signals,
            'position': position_signals,
        },
    }

    os.makedirs(WEB_DIR, exist_ok=True)
    output_path = os.path.join(WEB_DIR, 'portfolio.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Portfolio data exported to {output_path}")
    print(f"  Holdings: {len(portfolio_data)}")
    print(f"  Watchlist: {len(watchlist_data)}")
    print(f"  Buy signals: {len(output['signals']['buy'])}")
    print(f"  Sell signals: {len(output['signals']['sell'])}")
    print(f"  Sector signals: {len(output['signals']['sector'])}")
    return output


if __name__ == '__main__':
    export_portfolio_json()
