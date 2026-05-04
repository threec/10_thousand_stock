"""
Sina Finance API client with SQLite caching.
Caches K-line data (4hr TTL) and real-time quotes (5min TTL).
"""
import json, sqlite3, time, urllib.request
from datetime import datetime, timedelta
from pathlib import Path


class APIClient:
    """Cached Sina Finance API client."""

    def __init__(self, cache_db_path, kline_ttl_minutes=240, quote_ttl_minutes=5,
                 user_agent='Mozilla/5.0', referer='https://finance.sina.com.cn'):
        self.cache_db = cache_db_path
        self.kline_ttl = kline_ttl_minutes
        self.quote_ttl = quote_ttl_minutes
        self.headers = {
            'User-Agent': user_agent,
            'Referer': referer,
        }
        self.stats = {'hits': 0, 'misses': 0, 'errors': 0}
        self._init_db()

    def _init_db(self):
        Path(self.cache_db).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.cache_db)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS api_cache (
                cache_key TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                response_data TEXT,
                cached_at TEXT,
                ttl_minutes INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_cached_at ON api_cache(cached_at);
        """)
        conn.commit()
        conn.close()

    def _is_fresh(self, cached_at, ttl_minutes):
        try:
            cached_time = datetime.strptime(cached_at, '%Y-%m-%d %H:%M')
            age = (datetime.now() - cached_time).total_seconds() / 60
            return age < ttl_minutes
        except:
            return False

    def _cache_get(self, cache_key):
        conn = sqlite3.connect(self.cache_db)
        row = conn.execute(
            "SELECT response_data, cached_at, ttl_minutes FROM api_cache WHERE cache_key=?",
            (cache_key,)
        ).fetchone()
        conn.close()
        if row and self._is_fresh(row[1], row[2]):
            self.stats['hits'] += 1
            return row[0]
        self.stats['misses'] += 1
        return None

    def _cache_set(self, cache_key, url, data, ttl_minutes):
        conn = sqlite3.connect(self.cache_db)
        conn.execute(
            "INSERT OR REPLACE INTO api_cache VALUES (?, ?, ?, ?, ?)",
            (cache_key, url, data, datetime.now().strftime('%Y-%m-%d %H:%M'), ttl_minutes)
        )
        conn.commit()
        conn.close()

    def fetch(self, url, encoding='gbk', retries=3, timeout=15):
        """Fetch URL with retries."""
        for i in range(retries):
            try:
                req = urllib.request.Request(url, headers=self.headers)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return resp.read().decode(encoding, errors='replace')
            except Exception:
                if i == retries - 1:
                    self.stats['errors'] += 1
                    return None
                time.sleep(1.5)

    def get_kline(self, code, count=120):
        """Get daily K-line data with caching."""
        cache_key = f"kline:{code}:{count}"
        cached = self._cache_get(cache_key)
        if cached:
            return self._parse_kline(cached)

        url = (
            "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            f"CN_MarketData.getKLineData?symbol={code}&scale=240&ma=no&datalen={count}"
        )
        text = self.fetch(url, encoding='utf-8')
        if not text:
            return None
        try:
            data = json.loads(text)
        except:
            return None
        if not data:
            return None

        self._cache_set(cache_key, url, text, self.kline_ttl)
        return self._parse_kline(text)

    def _parse_kline(self, text):
        """Parse kline JSON text into structured dict."""
        try:
            data = json.loads(text)
        except:
            return None
        if not data:
            return None
        result = {
            'dates': [], 'opens': [], 'closes': [], 'highs': [], 'lows': [], 'volumes': [],
        }
        for d in data:
            result['dates'].append(d['day'])
            result['opens'].append(float(d['open']))
            result['closes'].append(float(d['close']))
            result['highs'].append(float(d['high']))
            result['lows'].append(float(d['low']))
            result['volumes'].append(float(d['volume']))
        return result

    def get_quote(self, code):
        """Get real-time stock quote with caching."""
        cache_key = f"quote:{code}"
        cached = self._cache_get(cache_key)
        if cached:
            return self._parse_quote(cached, code)

        url = f"https://hq.sinajs.cn/list={code}"
        text = self.fetch(url)
        if not text:
            return None

        self._cache_set(cache_key, url, text, self.quote_ttl)
        return self._parse_quote(text, code)

    def _parse_quote(self, text, code):
        try:
            parts = text.split('"')[1].split(',')
            if len(parts) > 5:
                return {
                    'code': code,
                    'name': parts[0],
                    'open': float(parts[1]),
                    'prev_close': float(parts[2]),
                    'current': float(parts[3]),
                    'high': float(parts[4]),
                    'low': float(parts[5]),
                }
        except:
            pass
        return None

    def get_index_kline(self, code, count=120):
        """Get index K-line (same as stock kline, cached longer)."""
        cache_key = f"index_kline:{code}:{count}"
        cached = self._cache_get(cache_key)
        if cached:
            return self._parse_kline(cached)

        url = (
            "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            f"CN_MarketData.getKLineData?symbol={code}&scale=240&ma=no&datalen={count}"
        )
        text = self.fetch(url, encoding='utf-8')
        if not text:
            return None

        self._cache_set(cache_key, url, text, 60)  # 1hr TTL for indices
        return self._parse_kline(text)

    def get_stats(self):
        return dict(self.stats)


# Singleton
_client = None


def get_client(cache_db=None):
    global _client
    if _client is None:
        if cache_db is None:
            from config import CACHE_DB
            cache_db = CACHE_DB
        _client = APIClient(cache_db)
    return _client
