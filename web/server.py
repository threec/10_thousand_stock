"""
HTTP server for the stock dashboard.
Serves static files and data JSON, plus CRUD API for portfolio/watchlist.
"""
import http.server, os, json, sys, webbrowser, urllib.parse
from pathlib import Path

PORT = 8080
HOST = "127.0.0.1"
ROOT = Path(r"D:\stock")
STATIC_DIR = ROOT / "web" / "static"
DATA_DIR = ROOT / "data" / "web"
FALLBACK_DIR = DATA_DIR

# Import screener modules for API handlers
sys.path.insert(0, str(ROOT / "screener"))
from db import get_db, add_holding, update_holding, close_holding, get_holdings
from db import add_watch, remove_watch, get_watchlist, get_signals, acknowledge_signal
from portfolio import export_portfolio_json
from api import get_client


def _regenerate_portfolio():
    """Regenerate portfolio.json after data changes."""
    try:
        export_portfolio_json()
    except Exception as e:
        print(f"  [warn] portfolio.json regeneration failed: {e}")


def json_response(handler, data, status=200):
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.end_headers()
    handler.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))


def _calc_ma(values, period):
    """Compute simple moving average, padding with null for alignment."""
    ma = [None] * (period - 1)
    for i in range(period - 1, len(values)):
        avg = sum(values[i - period + 1:i + 1]) / period
        ma.append(round(avg, 2))
    return ma


def _agg_period(kline, period):
    """Aggregate daily kline data into weekly/monthly/quarterly/yearly bars."""
    if period == 'daily' or not kline:
        return kline

    dates = kline['dates']
    opens = kline['opens']
    closes = kline['closes']
    highs = kline['highs']
    lows = kline['lows']
    volumes = kline['volumes']
    n = len(dates)

    if n == 0:
        return kline

    # Bucket-merge reducer
    buckets = []
    current_key = None
    current = None

    for i in range(n):
        d = dates[i]
        if period == 'weekly':
            # Use ISO year-week for grouping
            parts = d.split('-')
            from datetime import date
            dt = date(int(parts[0]), int(parts[1]), int(parts[2]))
            iso = dt.isocalendar()
            key = f"{iso[0]}-W{iso[1]:02d}"
        elif period == 'monthly':
            key = d[:7]  # YYYY-MM
        elif period == 'quarterly':
            parts = d.split('-')
            q = (int(parts[1]) - 1) // 3 + 1
            key = f"{parts[0]}-Q{q}"
        elif period == 'yearly':
            key = d[:4]  # YYYY
        else:
            key = d  # daily

        if key != current_key:
            if current is not None:
                buckets.append(current)
            current = {
                'date': d, 'open': opens[i], 'close': closes[i],
                'high': highs[i], 'low': lows[i], 'volume': volumes[i],
            }
            current_key = key
        else:
            current['close'] = closes[i]
            current['high'] = max(current['high'], highs[i])
            current['low'] = min(current['low'], lows[i])
            current['volume'] += volumes[i]

    if current is not None:
        buckets.append(current)

    return {
        'dates': [b['date'] for b in buckets],
        'opens': [b['open'] for b in buckets],
        'closes': [b['close'] for b in buckets],
        'highs': [b['high'] for b in buckets],
        'lows': [b['low'] for b in buckets],
        'volumes': [round(b['volume'], 0) for b in buckets],
    }


def _calc_macd(closes, fast=12, slow=26, signal=9):
    """Calculate MACD, signal line, and histogram from closes array."""
    if len(closes) < slow + signal:
        return [None]*len(closes), [None]*len(closes), [None]*len(closes)

    ema_fast = [closes[0]]
    ema_slow = [closes[0]]
    mf = 2/(fast+1)
    ms = 2/(slow+1)

    for i in range(1, len(closes)):
        ema_fast.append(closes[i]*mf + ema_fast[i-1]*(1-mf))
        ema_slow.append(closes[i]*ms + ema_slow[i-1]*(1-ms))

    dif = [e_f - e_s for e_f, e_s in zip(ema_fast, ema_slow)]

    # Signal = EMA of DIF
    dea = [dif[0]]
    md = 2/(signal+1)
    for i in range(1, len(dif)):
        dea.append(dif[i]*md + dea[i-1]*(1-md))

    # Histogram = (DIF - DEA) * 2
    macd_hist = [(dif[i] - dea[i]) * 2 for i in range(len(dif))]

    pad_dif = [None]*(slow-1) + dif[slow-1:]
    pad_dea = [None]*(slow-1) + dea[slow-1:]
    pad_hist = [None]*(slow-1) + macd_hist[slow-1:]

    return [round(x, 4) if x is not None else None for x in pad_dif], \
           [round(x, 4) if x is not None else None for x in pad_dea], \
           [round(x, 4) if x is not None else None for x in pad_hist]


def read_body(handler):
    length = int(handler.headers.get('Content-Length', 0))
    if length == 0:
        return {}
    body = handler.rfile.read(length).decode('utf-8')
    return json.loads(body)


# ---- Local DB helpers (use stock_list + stock_kline_daily) ----

def _get_stock_name(code):
    """Look up stock name from local stock_list table."""
    conn = get_db(str(ROOT / "data" / "screener" / "screener.db"))
    row = conn.execute("SELECT name FROM stock_list WHERE code=?", (code,)).fetchone()
    conn.close()
    return row['name'] if row else None


def _get_local_kline(code, count=500):
    """Get daily K-line from local stock_kline_daily table."""
    conn = get_db(str(ROOT / "data" / "screener" / "screener.db"))
    rows = conn.execute(
        "SELECT date, open, high, low, close, volume FROM stock_kline_daily "
        "WHERE code=? ORDER BY date ASC LIMIT ?",
        (code, count)
    ).fetchall()
    conn.close()
    if not rows:
        return None
    result = {'dates':[], 'opens':[], 'closes':[], 'highs':[], 'lows':[], 'volumes':[]}
    for r in rows:
        result['dates'].append(r['date'])
        result['opens'].append(r['open'])
        result['closes'].append(r['close'])
        result['highs'].append(r['high'])
        result['lows'].append(r['low'])
        result['volumes'].append(r['volume'])
    return result


def _search_stocks(query, limit=20):
    """Search stock_list by code or name, return matches."""
    conn = get_db(str(ROOT / "data" / "screener" / "screener.db"))
    like = f"%{query}%"
    rows = conn.execute(
        "SELECT code, name FROM stock_list WHERE code LIKE ? OR name LIKE ? LIMIT ?",
        (like, like, limit)
    ).fetchall()
    conn.close()
    return [{'code': r['code'], 'name': r['name']} for r in rows]


class DashboardHandler(http.server.SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        serve_dir = str(STATIC_DIR) if STATIC_DIR.exists() else str(FALLBACK_DIR)
        super().__init__(*args, directory=serve_dir, **kwargs)

    def log_message(self, format, *args):
        if '%s' in format and args:
            print(f"  [{self.log_date_time_string()}] {args[0]}")
        else:
            print(f"  [{self.log_date_time_string()}] {format % args}")

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-store, max-age=0')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        path = self.path.split('?')[0]

        if path == '/api/portfolio':
            self._handle_get_portfolio()
            return
        elif path == '/api/watchlist':
            self._handle_get_watchlist()
            return
        elif path == '/api/signals':
            self._handle_get_signals()
            return
        elif path.startswith('/api/kline/'):
            code = path.replace('/api/kline/', '')
            code = urllib.parse.unquote(code)
            self._handle_get_kline(code)
            return
        elif path == '/api/stock/search':
            self._handle_stock_search()
            return
        elif path.startswith('/api/quote/'):
            code = path.replace('/api/quote/', '')
            code = urllib.parse.unquote(code)
            self._handle_get_quote(code)
            return
        elif path.startswith('/api/'):
            filename = path.replace('/api/', '')
            filepath = DATA_DIR / filename
            if filepath.exists() and filepath.is_file():
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                with open(filepath, 'r', encoding='utf-8') as f:
                    self.wfile.write(f.read().encode('utf-8'))
            else:
                json_response(self, {'error': 'not found'}, 404)
            return

        super().do_GET()

    def do_POST(self):
        path = self.path.split('?')[0]

        if path == '/api/portfolio/add':
            self._handle_portfolio_add()
        elif path == '/api/portfolio/update':
            self._handle_portfolio_update()
        elif path == '/api/portfolio/close':
            self._handle_portfolio_close()
        elif path == '/api/watchlist/add':
            self._handle_watchlist_add()
        elif path == '/api/watchlist/remove':
            self._handle_watchlist_remove()
        elif path == '/api/signals/ack':
            self._handle_signals_ack()
        else:
            json_response(self, {'error': 'not found'}, 404)

    def do_DELETE(self):
        path = self.path.split('?')[0]
        if path.startswith('/api/watchlist/'):
            code = path.replace('/api/watchlist/', '')
            code = urllib.parse.unquote(code)
            self._handle_watchlist_delete(code)
        else:
            json_response(self, {'error': 'not found'}, 404)

    # ---- Portfolio endpoints ----

    def _handle_get_portfolio(self):
        try:
            conn = get_db(str(ROOT / "data" / "screener" / "screener.db"))
            rows = [dict(r) for r in get_holdings(conn, active_only=False)]
            conn.close()
            json_response(self, rows)
        except Exception as e:
            json_response(self, {'error': str(e)}, 500)

    def _handle_portfolio_add(self):
        try:
            data = read_body(self)
            conn = get_db(str(ROOT / "data" / "screener" / "screener.db"))
            rid = add_holding(conn, code=data.get('code', ''),
                            name=data.get('name', ''),
                            entry_price=data.get('entry_price', 0),
                            entry_date=data.get('entry_date', ''),
                            entry_reason=data.get('entry_reason', ''),
                            stop_loss_method=data.get('stop_loss_method', 'ma10'),
                            notes=data.get('notes', ''))
            conn.close()
            _regenerate_portfolio()
            json_response(self, {'id': rid, 'status': 'ok'})
        except Exception as e:
            json_response(self, {'error': str(e)}, 500)

    def _handle_portfolio_update(self):
        try:
            data = read_body(self)
            hid = data.pop('id', None)
            if not hid:
                json_response(self, {'error': 'id required'}, 400)
                return
            conn = get_db(str(ROOT / "data" / "screener" / "screener.db"))
            update_holding(conn, hid, **data)
            conn.close()
            _regenerate_portfolio()
            json_response(self, {'status': 'ok'})
        except Exception as e:
            json_response(self, {'error': str(e)}, 500)

    def _handle_portfolio_close(self):
        try:
            data = read_body(self)
            hid = data.get('id')
            if not hid:
                json_response(self, {'error': 'id required'}, 400)
                return
            conn = get_db(str(ROOT / "data" / "screener" / "screener.db"))
            close_holding(conn, hid)
            conn.close()
            _regenerate_portfolio()
            json_response(self, {'status': 'ok'})
        except Exception as e:
            json_response(self, {'error': str(e)}, 500)

    # ---- Watchlist endpoints ----

    def _handle_get_watchlist(self):
        try:
            conn = get_db(str(ROOT / "data" / "screener" / "screener.db"))
            rows = [dict(r) for r in get_watchlist(conn)]
            conn.close()
            json_response(self, rows)
        except Exception as e:
            json_response(self, {'error': str(e)}, 500)

    def _handle_watchlist_add(self):
        try:
            data = read_body(self)
            conn = get_db(str(ROOT / "data" / "screener" / "screener.db"))
            rid = add_watch(conn, code=data.get('code', ''),
                          name=data.get('name', ''),
                          target_price=data.get('target_price', 0),
                          watch_reason=data.get('watch_reason', ''),
                          alert_score=data.get('alert_score', 70),
                          notes=data.get('notes', ''),
                          watched_price=data.get('watched_price', 0))
            conn.close()
            _regenerate_portfolio()
            json_response(self, {'id': rid, 'status': 'ok'})
        except Exception as e:
            json_response(self, {'error': str(e)}, 500)

    def _handle_watchlist_remove(self):
        try:
            data = read_body(self)
            code = data.get('code')
            if not code:
                json_response(self, {'error': 'code required'}, 400)
                return
            conn = get_db(str(ROOT / "data" / "screener" / "screener.db"))
            remove_watch(conn, code)
            conn.close()
            _regenerate_portfolio()
            json_response(self, {'status': 'ok'})
        except Exception as e:
            json_response(self, {'error': str(e)}, 500)

    def _handle_watchlist_delete(self, code):
        try:
            conn = get_db(str(ROOT / "data" / "screener" / "screener.db"))
            remove_watch(conn, code)
            conn.close()
            _regenerate_portfolio()
            json_response(self, {'status': 'ok'})
        except Exception as e:
            json_response(self, {'error': str(e)}, 500)

    # ---- K-line endpoint ----

    def _handle_get_kline(self, code):
        try:
            count = 500
            period = 'daily'
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            if 'count' in params:
                count = int(params['count'][0])
            if 'period' in params:
                period = params['period'][0]

            # Always fetch daily data (need enough for aggregation + MA base)
            fetch_count = count
            if period != 'daily':
                fetch_count = count * 5  # oversample for aggregation
            fetch_count = min(fetch_count, 1000)

            # Always fetch from Sina API (network) for complete K-line data
            client = get_client(str(ROOT / "data" / "cache" / "api_cache.db"))
            daily = client.get_kline(code, count=fetch_count)
            if not daily:
                json_response(self, {'error': 'no data for '+code}, 404)
                return

            # Aggregate to target period
            kline = _agg_period(daily, period)

            # Trim to requested count
            for key in ('dates', 'opens', 'closes', 'highs', 'lows', 'volumes'):
                if len(kline[key]) > count:
                    kline[key] = kline[key][-count:]

            # Compute MAs (period-adaptive)
            closes = kline['closes']
            if period == 'daily':
                ma5 = _calc_ma(closes, 5)
                ma10 = _calc_ma(closes, 10)
                ma20 = _calc_ma(closes, 20)
            elif period == 'weekly':
                ma5 = _calc_ma(closes, 5)
                ma10 = _calc_ma(closes, 10)
                ma20 = _calc_ma(closes, 20)
            elif period == 'monthly':
                ma5 = _calc_ma(closes, 5)
                ma10 = _calc_ma(closes, 10)
                ma20 = _calc_ma(closes, 12)
            elif period == 'quarterly':
                ma5 = _calc_ma(closes, 5)
                ma10 = _calc_ma(closes, 8)
                ma20 = _calc_ma(closes, 12)
            else:  # yearly
                ma5 = _calc_ma(closes, 3)
                ma10 = _calc_ma(closes, 5)
                ma20 = _calc_ma(closes, 10)

            # MACD
            macd_dif, macd_dea, macd_hist = _calc_macd(closes)

            json_response(self, {
                'code': code,
                'period': period,
                'dates': kline['dates'],
                'opens': kline['opens'],
                'closes': kline['closes'],
                'highs': kline['highs'],
                'lows': kline['lows'],
                'volumes': kline['volumes'],
                'ma5': ma5,
                'ma10': ma10,
                'ma20': ma20,
                'macd_dif': macd_dif,
                'macd_dea': macd_dea,
                'macd_hist': macd_hist,
            })
        except Exception as e:
            json_response(self, {'error': str(e)}, 500)

    # ---- Signals endpoints ----

    def _handle_get_signals(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            date_str = params.get('date', [None])[0]
            sig_type = params.get('type', [None])[0]
            conn = get_db(str(ROOT / "data" / "screener" / "screener.db"))
            rows = [dict(r) for r in get_signals(conn, date_str, sig_type)]
            conn.close()
            json_response(self, rows)
        except Exception as e:
            json_response(self, {'error': str(e)}, 500)

    def _handle_signals_ack(self):
        try:
            data = read_body(self)
            sid = data.get('id')
            if not sid:
                json_response(self, {'error': 'id required'}, 400)
                return
            conn = get_db(str(ROOT / "data" / "screener" / "screener.db"))
            acknowledge_signal(conn, sid)
            conn.close()
            json_response(self, {'status': 'ok'})
        except Exception as e:
            json_response(self, {'error': str(e)}, 500)

    # ---- Stock search endpoint ----

    def _handle_stock_search(self):
        """Search stock_list by code or name for autocomplete."""
        try:
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            q = params.get('q', [''])[0].strip()
            if len(q) < 1:
                json_response(self, [])
                return
            results = _search_stocks(q, limit=15)
            json_response(self, results)
        except Exception as e:
            json_response(self, {'error': str(e)}, 500)

    # ---- Quote endpoint ----

    def _handle_get_quote(self, code):
        """Name from local stock_list (fast), price from Sina API (live)."""
        try:
            name = _get_stock_name(code)

            # Always get live price from network
            client = get_client(str(ROOT / "data" / "cache" / "api_cache.db"))
            quote = client.get_quote(code)
            price = quote['current'] if quote else 0

            if not name and quote:
                name = quote['name']
            if not name:
                json_response(self, {'error': 'no quote for '+code}, 404)
                return

            json_response(self, {
                'code': code,
                'name': name,
                'price': price or 0,
            })
        except Exception as e:
            json_response(self, {'error': str(e)}, 500)


def run():
    server = http.server.HTTPServer((HOST, PORT), DashboardHandler)
    url = f"http://{HOST}:{PORT}"
    print(f"\n  Dashboard: {url}")
    print(f"  API: {url}/api/portfolio.json")
    print(f"  API: {url}/api/portfolio")
    print(f"  Ctrl+C to stop\n")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.shutdown()


if __name__ == '__main__':
    run()
