"""
SQLite database for screener results, tracking, and cache.
"""
import json, sqlite3
from datetime import datetime


def get_db(db_path):
    """Get a database connection with WAL mode and schema initialized."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
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

        CREATE TABLE IF NOT EXISTS stock_tracking (
            code TEXT NOT NULL,
            first_date TEXT NOT NULL,
            first_price REAL,
            first_score INTEGER,
            first_sector TEXT,
            appearances INTEGER DEFAULT 1,
            last_appearance TEXT,
            max_score INTEGER,
            PRIMARY KEY (code)
        );

        CREATE TABLE IF NOT EXISTS screener_runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            api_calls INTEGER,
            stocks_scored INTEGER,
            duration_seconds REAL,
            market_state TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_stock_date ON stock_daily(date);
        CREATE INDEX IF NOT EXISTS idx_sector_date ON sector_daily(date);
        CREATE INDEX IF NOT EXISTS idx_index_date ON index_daily(date);

        -- Portfolio: current holdings
        CREATE TABLE IF NOT EXISTS portfolio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            name TEXT,
            entry_price REAL,
            entry_date TEXT,
            quantity INTEGER DEFAULT 1,
            entry_reason TEXT,
            stop_loss_method TEXT DEFAULT 'ma10',
            notes TEXT,
            active INTEGER DEFAULT 1
        );

        -- Watchlist: stocks to monitor
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT,
            added_date TEXT,
            target_price REAL,
            watched_price REAL,
            watch_reason TEXT,
            alert_score INTEGER DEFAULT 70,
            notes TEXT
        );

        -- Portfolio snapshots: daily tracking of holdings
        CREATE TABLE IF NOT EXISTS portfolio_snapshot (
            date TEXT NOT NULL,
            code TEXT NOT NULL,
            price REAL,
            score INTEGER,
            return_pct REAL,
            ma5 REAL, ma10 REAL, ma20 REAL, ma60 REAL,
            is_bullish INTEGER,
            signals TEXT,
            PRIMARY KEY (date, code)
        );

        -- Daily signals log
        CREATE TABLE IF NOT EXISTS daily_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            code TEXT NOT NULL,
            stock_name TEXT,
            type TEXT NOT NULL,
            signal TEXT NOT NULL,
            strength TEXT,
            detail TEXT,
            source_rule TEXT,
            acknowledged INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_signals_date ON daily_signals(date);
        CREATE INDEX IF NOT EXISTS idx_signals_code ON daily_signals(code);
    """)
    # Migration: add watched_price for existing watchlist tables
    try:
        conn.execute("ALTER TABLE watchlist ADD COLUMN watched_price REAL")
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.commit()
    return conn


# ================================================================
# Portfolio CRUD
# ================================================================

def add_holding(conn, code, name='', entry_price=0, entry_date='', entry_reason='',
                stop_loss_method='ma10', notes=''):
    c = conn.cursor()
    c.execute(
        "INSERT INTO portfolio (code, name, entry_price, entry_date, entry_reason, stop_loss_method, notes) VALUES (?,?,?,?,?,?,?)",
        (code, name, entry_price, entry_date, entry_reason, stop_loss_method, notes)
    )
    conn.commit()
    return c.lastrowid


def update_holding(conn, holding_id, **kwargs):
    allowed = {'name', 'entry_price', 'entry_date', 'entry_reason', 'stop_loss_method', 'notes', 'active'}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    sets = ', '.join(f"{k}=?" for k in updates)
    vals = list(updates.values()) + [holding_id]
    conn.execute(f"UPDATE portfolio SET {sets} WHERE id=?", vals)
    conn.commit()


def close_holding(conn, holding_id):
    conn.execute("UPDATE portfolio SET active=0 WHERE id=?", (holding_id,))
    conn.commit()


def get_holdings(conn, active_only=True):
    sql = "SELECT id, code, name, entry_price, entry_date, quantity, entry_reason, stop_loss_method, notes, active FROM portfolio"
    if active_only:
        sql += " WHERE active=1"
    return conn.execute(sql + " ORDER BY id").fetchall()


# ================================================================
# Watchlist CRUD
# ================================================================

def add_watch(conn, code, name='', target_price=0, watch_reason='', alert_score=70, notes='', watched_price=0):
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO watchlist (code, name, added_date, target_price, watched_price, watch_reason, alert_score, notes) VALUES (?,?,date('now'),?,?,?,?,?)",
        (code, name, target_price, watched_price, watch_reason, alert_score, notes)
    )
    conn.commit()
    return c.lastrowid


def remove_watch(conn, code):
    conn.execute("DELETE FROM watchlist WHERE code=?", (code,))
    conn.commit()


def get_watchlist(conn):
    return conn.execute("SELECT * FROM watchlist ORDER BY added_date").fetchall()


# ================================================================
# Portfolio snapshots
# ================================================================

def save_snapshot(conn, date_str, code, price, score, return_pct, ma5, ma10, ma20, ma60, is_bullish, signals_json):
    conn.execute(
        "INSERT OR REPLACE INTO portfolio_snapshot VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (date_str, code, price, score, return_pct, ma5, ma10, ma20, ma60, is_bullish, signals_json)
    )
    conn.commit()


def get_snapshot_history(conn, code, limit=60):
    rows = conn.execute(
        "SELECT date, price, score, return_pct, is_bullish, signals FROM portfolio_snapshot WHERE code=? ORDER BY date DESC LIMIT ?",
        (code, limit)
    ).fetchall()
    return list(reversed(rows))


# ================================================================
# Daily signals
# ================================================================

def save_signal(conn, date_str, code, stock_name, sig_type, signal, strength, detail, source_rule):
    conn.execute(
        "INSERT INTO daily_signals (date, code, stock_name, type, signal, strength, detail, source_rule) VALUES (?,?,?,?,?,?,?,?)",
        (date_str, code, stock_name, sig_type, signal, strength, detail, source_rule)
    )
    conn.commit()


def get_signals(conn, date_str=None, sig_type=None, limit=50):
    sql = "SELECT date, code, stock_name, type, signal, strength, detail, source_rule, acknowledged FROM daily_signals WHERE 1=1"
    params = []
    if date_str:
        sql += " AND date=?"
        params.append(date_str)
    if sig_type:
        sql += " AND type=?"
        params.append(sig_type)
    sql += " ORDER BY date DESC, id DESC LIMIT ?"
    params.append(limit)
    return conn.execute(sql, params).fetchall()


def acknowledge_signal(conn, signal_id):
    conn.execute("UPDATE daily_signals SET acknowledged=1 WHERE id=?", (signal_id,))
    conn.commit()


# ================================================================
# Data storage helpers (used by stock_screener.py)
# ================================================================

def save_index(conn, date_str, index_trends):
    c = conn.cursor()
    c.execute("DELETE FROM index_daily WHERE date=?", (date_str,))
    for name, t in index_trends.items():
        c.execute(
            "INSERT INTO index_daily VALUES (?,?,?,?,?,?,?,?,?)",
            (date_str, name, t['current'], t['ret5'], t['ret10'], t['ret20'], t['ret60'],
             t['arrangement'], t['market_state'])
        )
    conn.commit()


def save_sectors(conn, date_str, ranked_sectors):
    c = conn.cursor()
    c.execute("DELETE FROM sector_daily WHERE date=?", (date_str,))
    for i, sec in enumerate(ranked_sectors):
        c.execute(
            "INSERT INTO sector_daily VALUES (?,?,?,?,?,?,?,?,?,?)",
            (date_str, sec['name'], i + 1, sec['score'],
             sec.get('avg_ret5', 0), sec.get('avg_ret10', 0), sec.get('avg_ret20', 0),
             sec.get('bull_count', 0), sec.get('breakout_count', 0), sec.get('total_count', 0))
        )
    conn.commit()


def save_stocks(conn, date_str, all_stocks):
    c = conn.cursor()
    c.execute("DELETE FROM stock_daily WHERE date=?", (date_str,))
    for s in all_stocks:
        c.execute(
            "INSERT INTO stock_daily VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (date_str, s['code'], s['sector'], s['name'], s['score'],
             s['price'], s['daily_chg'], s['ret5'], s['ret10'], s['ret20'], s['ret60'],
             ', '.join(s.get('reasons', [])), 1 if s.get('is_bullish') else 0)
        )
    conn.commit()


def track_appearances(conn, date_str, all_stocks):
    """Update stock_tracking with appearance history."""
    c = conn.cursor()
    seen = set()
    for s in all_stocks:
        code = s['code']
        if code in seen:
            continue
        seen.add(code)

        existing = c.execute(
            "SELECT appearances, max_score FROM stock_tracking WHERE code=?", (code,)
        ).fetchone()

        if existing:
            c.execute(
                "UPDATE stock_tracking SET appearances = appearances + 1, last_appearance=?, max_score=MAX(max_score,?) WHERE code=?",
                (date_str, s['score'], code)
            )
        else:
            c.execute(
                "INSERT INTO stock_tracking VALUES (?,?,?,?,?,?,?,?)",
                (code, date_str, s['price'], s['score'], s['sector'], 1, date_str, s['score'])
            )
    conn.commit()


def record_run(conn, date_str, api_calls, stocks_scored, duration, market_state=""):
    c = conn.cursor()
    c.execute(
        "INSERT INTO screener_runs (date, started_at, completed_at, api_calls, stocks_scored, duration_seconds, market_state) VALUES (?,?,?,?,?,?,?)",
        (date_str, datetime.now().strftime('%Y-%m-%d %H:%M'), datetime.now().strftime('%Y-%m-%d %H:%M'),
         api_calls, stocks_scored, duration, market_state)
    )
    conn.commit()


def get_cached_kline(conn, code):
    c = conn.cursor()
    row = c.execute("SELECT data, updated_at FROM kline_cache WHERE code=?", (code,)).fetchone()
    if row:
        try:
            return json.loads(row[0])
        except Exception:
            pass
    return None


def set_cached_kline(conn, code, data):
    conn.execute(
        "INSERT OR REPLACE INTO kline_cache VALUES (?,?,?)",
        (code, json.dumps(data), datetime.now().strftime('%Y-%m-%d %H:%M'))
    )
    conn.commit()
