"""
Signal Engine — applies 15-section methodology rules to daily screener results.

Generates actionable signals:
  - BUY signals: entry opportunities based on methodology section 05
  - SELL signals: exit warnings based on methodology section 06
  - SECTOR signals: rotation alerts based on methodology section 03
  - POSITION signals: sizing guidance based on methodology sections 02, 07

Each signal links back to its source methodology chapter.
"""
import json, sqlite3, logging
from datetime import datetime, timedelta

from scoring import determine_strategy

logger = logging.getLogger(__name__)


class SignalEngine:
    """Detects buy/sell/sector/position signals from daily screener data."""

    def __init__(self, db_path):
        self.db_path = db_path

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ================================================================
    # BUY SIGNALS (Methodology Chapter 05: 买入时机与买点体系)
    # ================================================================

    def detect_buy_signals(self, stocks_today, stocks_yesterday=None):
        """
        Detect buy signals from today's screener results.
        """
        signals = []
        ytd = {s['code']: s for s in (stocks_yesterday or [])}

        for s in stocks_today:
            code = s['code']
            prev = ytd.get(code, {})

            # 🟢 突破买入: 当日突破20日新高 + 放量
            if s.get('has_breakout') and s.get('has_volume_break'):
                signals.append(self._make_signal(s, 'buy', '突破买入',
                    f"突破20日新高 + 放量突破(量比{s.get('vol_ratio',0):.1f})",
                    'strong', '05-买入时机: 模式二(突破)'))

            # 🟢 多头启动: 今天刚形成完全多头排列(昨天还不是)
            if s.get('is_full_bullish') and not prev.get('is_full_bullish'):
                signals.append(self._make_signal(s, 'buy', '多头启动',
                    '刚形成完全多头排列: MA5>MA10>MA20>MA60',
                    'strong', '05-买入时机: 模式一(顺势)'))

            # 🔵 均线低吸: 上升趋势 + 价格在20日线上方 + 评分中等以上
            in_uptrend = s.get('ret20', 0) > 10
            above_ma = s.get('above_ma20') or s.get('is_bullish')
            if in_uptrend and above_ma and not s.get('has_breakout') and s['score'] >= 60:
                signals.append(self._make_signal(s, 'buy', '均线低吸候选',
                    f"上升趋势(20日+{s.get('ret20',0):.1f}%) + 均线上方, 回踩可低吸",
                    'medium', '05-买入时机: 均线低吸法'))

            # 🔵 中枢突破: 突破20日新高 + 温和放量(非爆量)
            if s.get('has_breakout') and s.get('has_volume_mild') and s['score'] >= 75:
                signals.append(self._make_signal(s, 'buy', '中枢突破',
                    '突破平台 + 温和放量, 形态类似杯柄突破',
                    'medium', '05-买入时机: 振荡中枢上车'))

            # 🟡 趋势加速: 刚进入加速状态
            if s.get('accelerating') and not prev.get('accelerating') and s['score'] >= 70:
                signals.append(self._make_signal(s, 'buy', '趋势加速',
                    f"5日{s.get('ret5',0):+.1f}% > 10日{s.get('ret10',0):+.1f}% > 20日{s.get('ret20',0):+.1f}%",
                    'weak', '05-买入时机: 趋势加速(追高需谨慎)'))

        return signals

    # ================================================================
    # SELL SIGNALS (Methodology Chapter 06: 卖出与止损纪律)
    # ================================================================

    def detect_sell_signals(self, holdings, stocks_today, stocks_yesterday=None):
        """
        Detect sell signals for user's holdings.
        Uses available columns: price, ret5/10/20, is_bullish, daily_chg, reasons text.
        """
        signals = []
        today_map = {s['code']: s for s in stocks_today}
        ytd = {s['code']: s for s in (stocks_yesterday or [])}

        for h in holdings:
            code = h['code']
            s = today_map.get(code)
            if not s:
                continue

            prev = ytd.get(code, {})
            price = s['price']
            entry_price = h.get('entry_price', 0) or 0
            return_pct = ((price - entry_price) / entry_price * 100) if entry_price else 0

            # 🔴 趋势转弱: 今天非完全多头 且 昨天是完全多头 (多头排列消失)
            if not s.get('is_full_bullish') and prev.get('is_full_bullish') and s.get('ret5', 0) < 0:
                signals.append(self._make_signal(s, 'sell', '多头排列消失',
                    f"完全多头排列丧失 + 5日转负({s.get('ret5',0):+.1f}%), 收益率{return_pct:+.1f}%",
                    'forced', '06-卖出纪律: 趋势结束清仓'))

            # 🔴 高位破位: 高分+大跌幅
            was_high_score = prev and prev.get('score', 0) >= 80
            big_drop = s.get('daily_chg', 0) < -5
            if was_high_score and big_drop:
                signals.append(self._make_signal(s, 'sell', '高位破位',
                    f"高分股单日跌幅{s['daily_chg']:.1f}%, 警惕高位风险",
                    'forced', '06-卖出纪律: 高位大阴线=不确定性增加'))

            # 🟠 趋势转弱: 连续2日负收益+非多头
            neg_today = s.get('ret5', 0) < -3
            neg_yesterday = prev and prev.get('ret5', 0) < -3
            if neg_today and neg_yesterday and not s.get('is_bullish'):
                signals.append(self._make_signal(s, 'sell', '持续走弱',
                    f"连续走弱(5日{s.get('ret5',0):+.1f}%), 非多头排列",
                    'strong', '06-卖出纪律: 不及预期就跑路'))

            # 🟠 加速赶顶: 连续大涨+今日转跌
            rapid = s.get('ret5', 0) > 15 and s.get('daily_chg', 0) < 0
            was_strong = prev and prev.get('ret5', 0) > 10
            if rapid and was_strong:
                signals.append(self._make_signal(s, 'sell', '加速赶顶',
                    f"5日涨{s['ret5']:.1f}%后今日回落{s['daily_chg']:+.1f}%",
                    'medium', '06-卖出纪律: 连续加速后主动让利'))

        return signals

    # ================================================================
    # SECTOR ROTATION SIGNALS (Methodology Chapter 03: 板块与方向选择)
    # ================================================================

    def detect_sector_signals(self, sectors_today, sectors_history=None):
        """
        Detect sector rotation signals.

        Args:
            sectors_today: list of sector dicts from today with keys: name, score, rank
            sectors_history: dict of date -> list of sector dicts (last 5 days)
        Returns: list of signal dicts
        """
        signals = []
        if not sectors_history:
            return signals

        dates = sorted(sectors_history.keys())[-5:]

        # 🔴 板块走弱: 连续3天排名下降
        for sec in sectors_today:
            name = sec['name']
            ranks = []
            for d in dates:
                for s2 in sectors_history.get(d, []):
                    if s2.get('name') == name:
                        ranks.append(s2.get('rank', 99))
                        break
            if len(ranks) >= 3 and ranks[-3] < ranks[-2] < ranks[-1]:
                if sec['rank'] > 3:
                    signals.append({
                        'type': 'sector', 'signal': '板块走弱',
                        'code': '', 'stock_name': name,
                        'strength': 'warning',
                        'detail': f"{name}连续{len(ranks)}日排名下滑: {ranks[-3]}→{ranks[-2]}→{ranks[-1]}",
                        'source_rule': '03-板块选择: 放弃方向条件二',
                    })

        # 🟢 新板块崛起: 之前不在前5, 连续2天进前3
        today_top3 = {s['name'] for s in sectors_today if s.get('rank', 99) <= 3}
        for d in dates[-3:-1]:
            if d in sectors_history:
                prev_top5 = {s['name'] for s in sectors_history[d] if s.get('rank', 99) <= 5}
                newcomers = today_top3 - prev_top5
                for name in newcomers:
                    # Check it was also in top 3 yesterday
                    yesterday_top3 = set()
                    if len(dates) >= 2 and dates[-2] in sectors_history:
                        yesterday_top3 = {s['name'] for s in sectors_history[dates[-2]] if s.get('rank', 99) <= 3}
                    if name in yesterday_top3:
                        signals.append({
                            'type': 'sector', 'signal': '新板块崛起',
                            'code': '', 'stock_name': name,
                            'strength': 'strong',
                            'detail': f"{name}首次进入前三，可能成为新主线",
                            'source_rule': '03-板块选择: 风格转换识别',
                        })

        return signals

    # ================================================================
    # POSITION SIGNALS (Chapters 02, 07: 仓位管理)
    # ================================================================

    def detect_position_signals(self, market_summary, holdings, stocks_today):
        """
        Generate position management guidance.

        Args:
            market_summary: dict with market_state, strong_count, total_indices
            holdings: active portfolio holdings
            stocks_today: today's screener stocks
        Returns: list of position signal dicts
        """
        signals = []
        market = market_summary.get('market_state', '震荡市')
        today_map = {s['code']: s for s in stocks_today}

        # Market-based guidance
        if '牛市' in market:
            signals.append({
                'type': 'position', 'signal': '积极仓位',
                'code': '', 'stock_name': '整体市场',
                'strength': 'strong',
                'detail': f"市场状态: {market}, 建议高仓位, 积极进攻",
                'source_rule': '02-市场评估: 指数环境决定仓位',
            })
        elif '熊市' in market:
            signals.append({
                'type': 'position', 'signal': '防御仓位',
                'code': '', 'stock_name': '整体市场',
                'strength': 'forced',
                'detail': f"市场状态: {market}, 建议低仓位或空仓, 重质轻势",
                'source_rule': '02-市场评估: 指数环境决定仓位',
            })
        else:
            signals.append({
                'type': 'position', 'signal': '中性仓位',
                'code': '', 'stock_name': '整体市场',
                'strength': 'medium',
                'detail': f"市场状态: {market}, 控制仓位, 只做确定性高的机会",
                'source_rule': '02-市场评估: 振荡市策略',
            })

        # Per-holding position advice
        for h in holdings:
            s = today_map.get(h['code'])
            if not s:
                continue
            bullish = s.get('is_bullish', False)
            score = s.get('score', 0)

            if '牛市' in market and bullish and score >= 80:
                signals.append(self._make_signal(s, 'position', '加仓候选',
                    f"牛市+完全多头+高分{score}, 可考虑加仓",
                    'strong', '07-仓位管理: 确定性高集中仓位'))
            elif '熊市' in market and (not bullish or score < 60):
                signals.append(self._make_signal(s, 'position', '减仓候选',
                    f"熊市+非多头/低分{score}, 建议减仓或清仓",
                    'strong', '07-仓位管理: 下降趋势不持有'))

        return signals

    # ================================================================
    # MAIN DETECTION
    # ================================================================

    def _load_stocks(self, conn, date_str):
        """Load stocks from DB and enrich with parsed data from reasons text.
        Deduplicates by code — keeps highest-scored entry for stocks in multiple sectors."""
        rows = conn.execute(
            "SELECT code, name, sector, score, price, daily_chg, ret5, ret10, ret20, ret60, "
            "is_bullish, reasons FROM stock_daily WHERE date=? ORDER BY score DESC",
            (date_str,)
        ).fetchall()
        stocks = []
        seen = set()
        for r in rows:
            code = r['code']
            if code in seen:
                continue
            seen.add(code)
            d = dict(r)
            reasons = d.get('reasons', '')
            # Parse derived fields from reasons text
            d['has_breakout'] = '突破20日新高' in reasons
            d['has_volume_break'] = '放量突破' in reasons
            d['has_volume_mild'] = '温和放量' in reasons
            d['is_full_bullish'] = '完全多头排列' in reasons
            d['is_short_bullish'] = '短中期多头排列' in reasons or '短期多头' in reasons
            d['above_ma20'] = '站上20日线' in reasons or '站上20/60日线' in reasons
            d['near_60high'] = '接近60日新高' in reasons
            d['near_20high'] = '接近20日新高' in reasons
            d['low_start'] = '低位启动' in reasons
            d['accelerating'] = '趋势加速中' in reasons
            # Estimate vol_ratio from reasons
            import re
            vm = re.search(r'量比([\d.]+)', reasons)
            d['vol_ratio'] = float(vm.group(1)) if vm else 0
            stocks.append(d)
        return stocks

    def run(self, date_str=None):
        """
        Run all signal detection for a given date.

        Returns dict with buy_signals, sell_signals, sector_signals, position_signals.
        """
        if date_str is None:
            date_str = datetime.now().strftime('%Y-%m-%d')

        conn = self._conn()

        # Load today's data
        stocks_today = self._load_stocks(conn, date_str)

        sectors_today = [dict(r) for r in conn.execute(
            "SELECT name, rank, score, avg_ret5, avg_ret10, avg_ret20 FROM sector_daily WHERE date=? ORDER BY rank",
            (date_str,)
        ).fetchall()]

        # Load yesterday for trend detection
        yesterday = (datetime.strptime(date_str, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
        stocks_yesterday = self._load_stocks(conn, yesterday)

        # Load sector history
        sector_dates = [dict(r) for r in conn.execute(
            "SELECT DISTINCT date FROM sector_daily ORDER BY date DESC LIMIT 7"
        ).fetchall()]
        sectors_history = {}
        for sd in sector_dates:
            d = sd['date']
            sectors_history[d] = [dict(r) for r in conn.execute(
                "SELECT name, rank, score FROM sector_daily WHERE date=?", (d,)
            ).fetchall()]

        # Load holdings
        holdings = [dict(r) for r in conn.execute(
            "SELECT * FROM portfolio WHERE active=1"
        ).fetchall()]

        # Market summary
        index_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM index_daily WHERE date=?", (date_str,)
        ).fetchall()]
        strong_count = sum(1 for r in index_rows if r.get('ret20', 0) > 0)
        dominant_state = max(set(r.get('market_state', '震荡市') for r in index_rows),
                             key=lambda x: sum(1 for r2 in index_rows if r2.get('market_state') == x))
        market_summary = {
            'market_state': dominant_state,
            'strong_count': strong_count,
            'total': len(index_rows),
        }

        # Get index trends for market assessment
        index_trends = {}
        for r in index_rows:
            index_trends[r['name']] = {
                'current': r['close'], 'ret20': r['ret20'],
                'arrangement': r['arrangement'], 'market_state': r['market_state'],
            }

        # Detect signals
        buy_signals = self.detect_buy_signals(stocks_today, stocks_yesterday)
        sell_signals = self.detect_sell_signals(holdings, stocks_today, stocks_yesterday)
        sector_signals = self.detect_sector_signals(sectors_today, sectors_history)
        position_signals = self.detect_position_signals(market_summary, holdings, stocks_today)

        # Clear previous signals for today before saving
        conn.execute("DELETE FROM daily_signals WHERE date=?", (date_str,))

        # Save to DB
        for sig in buy_signals + sell_signals + position_signals:
            try:
                conn.execute(
                    "INSERT INTO daily_signals (date, code, stock_name, type, signal, strength, detail, source_rule) VALUES (?,?,?,?,?,?,?,?)",
                    (date_str, sig.get('code', ''), sig.get('stock_name', ''),
                     sig['type'], sig['signal'], sig.get('strength', ''),
                     sig.get('detail', ''), sig.get('source_rule', ''))
                )
            except Exception as e:
                logger.error(f"Failed to save signal: {sig.get('signal','?')} for {sig.get('code','?')}: {e}")
        for sig in sector_signals:
            try:
                conn.execute(
                    "INSERT INTO daily_signals (date, code, stock_name, type, signal, strength, detail, source_rule) VALUES (?,?,?,?,?,?,?,?)",
                    (date_str, '', sig.get('stock_name', ''), sig['type'], sig['signal'],
                     sig.get('strength', ''), sig.get('detail', ''), sig.get('source_rule', ''))
                )
            except Exception as e:
                logger.error(f"Failed to save sector signal: {sig.get('signal','?')} for {sig.get('stock_name','?')}: {e}")
        conn.commit()

        # Build watchlist status
        watchlist = [dict(r) for r in conn.execute("SELECT * FROM watchlist").fetchall()]
        watchlist_status = []
        for w in watchlist:
            found = None
            for s in stocks_today:
                if s['code'] == w['code']:
                    found = s
                    break
            if found:
                watchlist_status.append({
                    'code': w['code'], 'name': found['name'],
                    'score': found['score'], 'price': found['price'],
                    'reasons': found.get('reasons', ''),
                    'alert_score': w.get('alert_score', 70),
                    'ready': found['score'] >= w.get('alert_score', 70),
                })
            else:
                watchlist_status.append({
                    'code': w['code'], 'name': w.get('name', '?'),
                    'score': 0, 'price': 0, 'reasons': '',
                    'alert_score': w.get('alert_score', 70), 'ready': False,
                    'not_in_screener': True,
                })

        # Build portfolio status with strategy
        portfolio_status = []
        for h in holdings:
            found = None
            for s in stocks_today:
                if s['code'] == h['code']:
                    found = s
                    break
            status = {
                'id': h['id'], 'code': h['code'], 'name': h.get('name', '?'),
                'entry_price': h['entry_price'], 'entry_date': h['entry_date'],
                'stop_method': h.get('stop_loss_method', 'ma10'),
            }
            if found:
                entry = h['entry_price'] or 0
                ret = ((found['price'] - entry) / entry * 100) if entry else 0
                strategy, action = determine_strategy(
                    found['score'], found.get('is_bullish', False),
                    found.get('is_full_bullish', False),
                    found.get('above_ma20', False),
                    found.get('reasons', ''), found.get('ret5', 0))

                status.update({
                    'score': found['score'], 'price': found['price'],
                    'return_pct': round(ret, 1),
                    'is_bullish': found.get('is_bullish', False),
                    'is_full_bullish': found.get('is_full_bullish', False),
                    'reasons': found.get('reasons', ''),
                    'strategy': strategy,
                    'action': action,
                    'ret5': found.get('ret5', 0), 'ret20': found.get('ret20', 0),
                    'daily_chg': found.get('daily_chg', 0),
                })
            else:
                status.update({
                    'score': 0, 'price': 0, 'return_pct': 0, 'is_bullish': False,
                    'reasons': '', 'stop_price': 0,
                    'strategy': '该股票不在今日选股范围', 'action': 'unknown',
                })
            portfolio_status.append(status)

        conn.close()

        result = {
            'date': date_str,
            'market_summary': market_summary,
            'index_trends': index_trends,
            'buy_signals': buy_signals,
            'sell_signals': sell_signals,
            'sector_signals': sector_signals,
            'position_signals': position_signals,
            'portfolio_status': portfolio_status,
            'watchlist_status': watchlist_status,
            'top_sector': sectors_today[0]['name'] if sectors_today else '',
            'top_sector_score': sectors_today[0]['score'] if sectors_today else 0,
        }
        return result

    # ================================================================
    # HELPERS
    # ================================================================

    def _make_signal(self, stock, sig_type, signal, detail, strength, source_rule):
        return {
            'type': sig_type,
            'signal': signal,
            'code': stock.get('code', ''),
            'stock_name': stock.get('name', '?'),
            'sector': stock.get('sector', ''),
            'score': stock.get('score', 0),
            'price': stock.get('price', 0),
            'strength': strength,
            'detail': detail,
            'source_rule': source_rule,
        }
