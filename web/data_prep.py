"""
Unified web data preparation.
Generates all JSON files needed by the dashboard:
  - analysis_data.json (xueqiu analytics + methodology)
  - screener_history.json (aggregated daily results)
  - kb_index.json (via knowledge.builder)
"""
import json, os, sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import *

XUEQIU_BACKUP = XUEQIU_DIR / "xueqiu_posts" / "backup_5188.json"
# Fallback location
if not XUEQIU_BACKUP.exists():
    XUEQIU_BACKUP = XUEQIU_DIR / "backup_5188.json"


def load_posts():
    if not XUEQIU_BACKUP.exists():
        print(f"  WARNING: XUEQIU backup not found at {XUEQIU_BACKUP}")
        return []
    with open(XUEQIU_BACKUP, 'r', encoding='utf-8') as f:
        return json.load(f)


def build_monthly_activity(posts):
    months = Counter()
    for p in posts:
        ts = p.get("created_at")
        if ts:
            m = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m")
            months[m] += 1
    return [{"month": m, "count": c} for m, c in sorted(months.items())]


def build_keyword_data(posts):
    categories = {
        "技术指标": ["突破", "压力", "均线", "支撑", "回踩", "背离", "成交量", "换手", "筹码", "通道", "趋势线", "MACD", "KDJ", "钝化", "量比"],
        "交易策略": ["减仓", "加仓", "做T", "短线", "中线", "长线", "波段", "满仓", "空仓", "止损", "止盈", "追涨", "杀跌", "高抛低吸", "持股", "半仓", "日内", "补仓"],
        "市场判断": ["反弹", "牛市", "熊市", "见底", "见顶", "回调", "反转", "崩盘", "洗盘", "出货", "拉高", "护盘", "砸盘", "猴市", "筑底"],
        "投资理念": ["业绩", "题材", "龙头", "基本面", "PE", "估值", "概念", "成长", "热点", "政策", "白马", "价值投资", "技术分析", "趋势投资"],
        "风险控制": ["稳健", "回撤", "谨慎", "分散", "集中", "保守", "流动性", "风控"],
        "心理情绪": ["耐心", "乐观", "信心", "心态", "情绪", "悲观", "冷静", "贪婪", "恐惧", "后悔"],
        "板块偏好": ["医药", "AI", "机器人", "消费", "半导体", "芯片", "新能源", "银行", "有色", "锂电", "煤炭", "白酒", "汽车", "券商", "军工", "光伏", "地产", "保险", "钢铁"],
    }
    keyword_data = {}
    for cat, kws in categories.items():
        counts = {}
        for kw in kws:
            count = sum(1 for p in posts if kw in (p.get("text", "") + p.get("title", "")))
            if count > 0:
                counts[kw] = count
        keyword_data[cat] = dict(sorted(counts.items(), key=lambda x: -x[1])[:15])
    return keyword_data


def build_topic_data(posts):
    topic_patterns = {
        "大盘分析": ["大盘", "指数", "上证", "创业板", "科创"],
        "个股分析": ["这只", "个股", "标的", "看好"],
        "操作记录": ["买入", "卖出", "加仓", "减仓", "建仓"],
        "交易心理": ["心态", "情绪", "耐心", "纪律", "恐惧", "贪婪"],
        "学习心得": ["学习", "领悟", "体会", "总结", "反思"],
        "政策解读": ["政策", "央行", "利好", "利空", "监管"],
        "外围市场": ["美股", "港股", "纳斯达克", "标普"],
    }
    topic_counts = {}
    topic_samples = {}
    for topic, patterns in topic_patterns.items():
        count = 0
        samples = []
        for p in posts:
            txt = p.get("text", "")
            if any(pat in txt for pat in patterns):
                count += 1
                if len(samples) < 3 and len(txt) > 60:
                    ts = p.get("created_at", 0)
                    date_str = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d") if ts else "?"
                    samples.append({"date": date_str, "text": txt[:200]})
        topic_counts[topic] = count
        topic_samples[topic] = samples
    return topic_counts, topic_samples


def build_top_posts(posts, limit=30):
    scored = []
    for p in posts:
        rp = p.get("rp", 0) or 0
        fv = p.get("fv", 0) or 0
        ts = p.get("created_at", 0)
        date_str = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d") if ts else "?"
        txt = p.get("text", "")
        if len(txt) > 80:
            scored.append({"date": date_str, "text": txt[:250], "replies": rp, "favs": fv, "score": rp + fv})
    scored.sort(key=lambda x: -x["score"])
    return scored[:limit]


def build_long_posts(posts, min_len=300):
    long_posts = []
    for p in posts:
        txt = p.get("text", "")
        if len(txt) > min_len:
            ts = p.get("created_at", 0)
            date_str = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d") if ts else "?"
            long_posts.append({
                "date": date_str, "text": txt, "length": len(txt),
                "replies": p.get("rp", 0) or 0, "favs": p.get("fv", 0) or 0,
            })
    long_posts.sort(key=lambda x: -x["length"])
    return long_posts[:60]


def build_screener_history():
    """Aggregate historical screener results."""
    history = []
    screener_dir = Path(SCREENER_DIR)
    if not screener_dir.exists():
        return history
    for fname in sorted(screener_dir.glob("daily_*.json")):
        try:
            with open(fname, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Extract summary stats
            date = data.get('date', fname.stem.replace('daily_', ''))
            top_sectors = [(s[0], s[1]) for s in data.get('sector_ranking', [])[:3]]
            top_scores = [s['score'] for s in data.get('top_stocks', [])[:5]]
            avg_score = sum(top_scores) / len(top_scores) if top_scores else 0
            bull_count = sum(1 for s in data.get('top_stocks', []) if s.get('is_bullish'))
            history.append({
                'date': date,
                'top_sectors': top_sectors,
                'top5_avg_score': round(avg_score, 1),
                'bullish_count': bull_count,
                'total_stocks': len(data.get('top_stocks', [])),
            })
        except Exception as e:
            print(f"   [warn] Failed to parse {fname}: {e}")
    return history


def prepare_all():
    """Run all data preparation steps."""
    print("=" * 50)
    print("Web Data Preparation")
    print("=" * 50)

    # Load posts
    posts = load_posts()
    print(f"\nLoaded {len(posts)} posts")

    if not posts:
        print("No posts found, skipping analytics generation")
        return

    # Build analytics
    print("\n1. Monthly activity...")
    monthly = build_monthly_activity(posts)
    print(f"   {len(monthly)} months")

    print("2. Keyword frequency...")
    keywords = build_keyword_data(posts)
    total_kw = sum(len(v) for v in keywords.values())
    print(f"   {total_kw} keywords across {len(keywords)} categories")

    print("3. Topic classification...")
    topics, topic_samples = build_topic_data(posts)
    print(f"   {len(topics)} topics")

    print("4. Top posts...")
    top = build_top_posts(posts)
    print(f"   {len(top)} top posts")

    print("5. Long-form posts...")
    long = build_long_posts(posts)
    print(f"   {len(long)} long posts")

    print("6. Screener history...")
    screener_hist = build_screener_history()
    print(f"   {len(screener_hist)} days")

    # Load existing analysis data for methodology and articles
    existing = {}
    analysis_path = WEB_DIR / "analysis_data.json"
    if analysis_path.exists():
        with open(analysis_path, 'r', encoding='utf-8') as f:
            existing = json.load(f)

    # Build output
    timestamps = [p.get("created_at", 0) for p in posts if p.get("created_at")]
    analysis_data = {
        "meta": {
            "total_posts": len(posts),
            "date_range": {
                "from": datetime.fromtimestamp(min(timestamps) / 1000).strftime("%Y-%m-%d") if timestamps else "?",
                "to": datetime.fromtimestamp(max(timestamps) / 1000).strftime("%Y-%m-%d") if timestamps else "?",
            },
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        },
        "monthly_activity": monthly,
        "keyword_data": keywords,
        "topic_counts": topics,
        "topic_samples": topic_samples,
        "top_posts": top,
        "long_posts": long,
        "methodology": existing.get("methodology", {}),
        "wechat_articles": existing.get("wechat_articles", {}),
    }

    # Write analysis_data.json
    WEB_DIR.mkdir(parents=True, exist_ok=True)
    with open(analysis_path, 'w', encoding='utf-8') as f:
        json.dump(analysis_data, f, ensure_ascii=False, indent=2)
    print(f"\nSaved analysis_data.json -> {analysis_path}")

    # Write screener_history.json
    history_path = WEB_DIR / "screener_history.json"
    with open(history_path, 'w', encoding='utf-8') as f:
        json.dump(screener_hist, f, ensure_ascii=False, indent=2)
    print(f"Saved screener_history.json -> {history_path}")

    # Rebuild KB index
    print("\n7. Building KB index...")
    try:
        from knowledge.builder import build
        build()
    except ImportError:
        print("   KB builder not available, skipping")

    print("\nDone.")


if __name__ == '__main__':
    prepare_all()
