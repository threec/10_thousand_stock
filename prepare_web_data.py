"""
Prepare data for the web dashboard from scraped posts and screener results.
"""
import json, os, re
from collections import Counter, defaultdict
from datetime import datetime

DATA_DIR = r"D:\stock\data"
WEB_DIR = os.path.join(DATA_DIR, "web")
os.makedirs(WEB_DIR, exist_ok=True)

# ---- Load posts ----
backup_file = os.path.join(DATA_DIR, "xueqiu_posts", "backup_5188.json")
with open(backup_file, "r", encoding="utf-8") as f:
    posts = json.load(f)

print(f"Loaded {len(posts)} posts")

# ================================================================
# 1. Monthly activity data
# ================================================================
months = Counter()
for p in posts:
    ts = p.get("created_at")
    if ts:
        m = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m")
        months[m] += 1

monthly_activity = [{"month": m, "count": c} for m, c in sorted(months.items())]

# ================================================================
# 2. Keyword frequency by category
# ================================================================
categories = {
    "技术指标": ["突破", "压力", "均线", "支撑", "回踩", "背离", "成交量", "换手", "筹码", "通道", "趋势线", "MACD", "KDJ", "钝化", "量比"],
    "交易策略": ["减仓", "加仓", "做T", "短线", "中线", "长线", "波段", "满仓", "空仓", "止损", "止盈", "追涨", "杀跌", "高抛低吸", "持股", "半仓", "日内", "补仓"],
    "市场判断": ["反弹", "牛市", "熊市", "见底", "见顶", "回调", "反转", "崩盘", "洗盘", "出货", "拉高", "护盘", "砸盘", "猴市", "筑底	"],
    "投资理念": ["业绩", "题材", "龙头", "基本面", "PE", "估值", "概念", "成长", "热点", "政策", "白马", "价值投资", "技术分析", "趋势投资	"],
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

# ================================================================
# 3. Topic classification
# ================================================================
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

# ================================================================
# 4. Top engaged posts
# ================================================================
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
top_posts = scored[:30]

# ================================================================
# 5. Long-form key posts (his detailed analysis posts)
# ================================================================
long_posts = []
for p in posts:
    txt = p.get("text", "")
    if len(txt) > 300:
        ts = p.get("created_at", 0)
        date_str = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d") if ts else "?"
        long_posts.append({
            "date": date_str,
            "text": txt,
            "length": len(txt),
            "replies": p.get("rp", 0) or 0,
            "favs": p.get("fv", 0) or 0,
        })

long_posts.sort(key=lambda x: -x["length"])

# ================================================================
# 6. Screener historical data
# ================================================================
screener_dir = os.path.join(DATA_DIR, "screener")
screener_history = []
if os.path.exists(screener_dir):
    for fname in sorted(os.listdir(screener_dir)):
        if fname.startswith("daily_") and fname.endswith(".json"):
            with open(os.path.join(screener_dir, fname), "r", encoding="utf-8") as f:
                screener_history.append(json.load(f))

# ================================================================
# 7. Write all to web JSON
# ================================================================
web_data = {
    "meta": {
        "total_posts": len(posts),
        "date_range": {
            "from": datetime.fromtimestamp(min(p.get("created_at", 0) for p in posts if p.get("created_at")) / 1000).strftime("%Y-%m-%d"),
            "to": datetime.fromtimestamp(max(p.get("created_at", 0) for p in posts if p.get("created_at")) / 1000).strftime("%Y-%m-%d"),
        },
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
    },
    "monthly_activity": monthly_activity,
    "keyword_data": keyword_data,
    "topic_counts": topic_counts,
    "topic_samples": topic_samples,
    "top_posts": top_posts,
    "long_posts": long_posts[:60],
    "screener_history": screener_history,
}

output_file = os.path.join(WEB_DIR, "analysis_data.json")
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(web_data, f, ensure_ascii=False, indent=2)

print(f"Data written to {output_file}")
print(f"  Monthly data: {len(monthly_activity)} months")
print(f"  Keywords: {sum(len(v) for v in keyword_data.values())} across {len(keyword_data)} categories")
print(f"  Topics: {len(topic_counts)} categories")
print(f"  Top posts: {len(top_posts)}")
print(f"  Long posts: {len(long_posts[:60])}")
print(f"  Screener history: {len(screener_history)} days")
