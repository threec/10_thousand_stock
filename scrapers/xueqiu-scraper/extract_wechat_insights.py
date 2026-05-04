"""
Extract structured insights from WeChat articles for web dashboard.
Reads all 52 articles, extracts methodology, rules, quotes.
"""
import json, os, re
from datetime import datetime

SRC = r"D:\stock\data\wechat_articles"
DST = r"D:\stock\data\web\analysis_data.json"

def read_article(path):
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    meta = {}
    content_start = 0
    for i, line in enumerate(lines):
        line = line.strip()
        if line.startswith('标题:'):
            meta['title'] = line.replace('标题:', '').strip()
        elif line.startswith('日期:'):
            meta['date'] = line.replace('日期:', '').strip()
        elif line.startswith('链接:'):
            meta['url'] = line.replace('链接:', '').strip()
        elif line == '' and i > 3:
            content_start = i + 1
            break
    content = ''.join(lines[content_start:]).strip()
    return meta, content

# Read all articles
articles = []
for f in sorted(os.listdir(SRC)):
    if f.endswith('.txt') and f != '_index.txt':
        meta, content = read_article(os.path.join(SRC, f))
        if content:
            meta['file'] = f
            meta['word_count'] = len(content)
            articles.append((meta, content))

print(f"Loaded {len(articles)} articles")

# ================================================================
# Extract methodology sections
# ================================================================

# 1. Core methodology rules (extracted through reading)
methodology_rules = [
    {
        "id": "three_step",
        "category": "选股框架",
        "title": "三步选股法：指数定向 → 板块定位 → 个股定买点",
        "description": "先判断指数大环境是否安全，再找到趋势最强的板块，最后在板块内挑走势最好的个股。指数提供仓位参考，板块提供方向，个股走势决定具体买卖。",
        "source": "综合多篇文章",
        "key_quotes": [
            "老朋友都知道，我一般是先看指数，再看板块，然后在板块里找个股。",
            "当着手交易的时候，走势永远是第一位的。",
            "不管指数如何，永远多关注趋势向好的板块，永远做趋势之上的个股。"
        ]
    },
    {
        "id": "bull_bear_quality",
        "category": "选股框架",
        "title": "牛市重势，熊市重质",
        "description": "牛市中关注趋势强度和突破形态，熊市中更看重基本面质量和估值支撑。在不同市场环境下，选股侧重点完全不同。",
        "source": "015_怎样选出最强的股",
        "key_quotes": [
            "牛市重势，熊市重质。",
            "首先是考虑一个板块，整体的估值、前景等等。然后会翻看一些代表性的个股，但是当着手交易的时候，走势永远是第一位的。"
        ]
    },
    {
        "id": "main_uptrend_high",
        "category": "选股框架",
        "title": "主升总是在相对高位展开",
        "description": "真正的上涨往往从看似"已经涨了很多"的位置开始。不是追高，而是在趋势确认后顺势而为。低位≠安全，低估值≠短期会上涨。",
        "source": "031_多高才算高; P01_跌下来应该会有一些机会",
        "key_quotes": [
            "主升通常在相对高位展开。",
            "牛市里，涨停或者新高通常才是一个买入的信号弹。",
            "那些在一段时间内走强（中期走强），但是在近期刚结束了一段时间的调整或者横盘（短期调整），但是还没有经过连续加速的股票。"
        ]
    },
    {
        "id": "find_difference",
        "category": "选股框架",
        "title": "找到那个不一样的点",
        "description": "95%的K线没有分析价值。关键在于找到标志性K线——新的价格、新的逻辑、新的成交量。找到跟之前不一样的点，然后买入。",
        "source": "011_找到那个不一样的点",
        "key_quotes": [
            "95%以上的K线都是没有任何意义的。或者是合理的，或者是随机的。都不值得分析。而找到那种标志性的K线，才是赚钱的根本。",
            "新这个字很丰富，买入的理由，可以是新的价格，也可以是新的逻辑，还可以是新的成交量，去找到跟之前不一样的那个点，然后买入。",
            "所有的逻辑能不能持续上涨，归根到底都是看资金的力量，是否有资金认可并买入，而所有买入在走势上都会留下痕迹。"
        ]
    },
    {
        "id": "compact_structure",
        "category": "技术分析",
        "title": "紧凑结构优先",
        "description": "涨的时候流畅，跌的时候跌得少的个股属于紧凑结构。紧凑=更高确定性，即使失败也能在较小范围内止损。但也要认识到这种偏好可能错过一些机会。",
        "source": "032_一些可能会耽误赚钱的偏好; 017_继续一些反思",
        "key_quotes": [
            "涨的时候流畅，跌的时候跌得少的个股就属于紧凑的结构。",
            "永远应该给紧凑的走势更大一点的权重。什么是紧凑的走势，简单来讲，就是一般不大跌，大跌了要快速反包。"
        ]
    },
    {
        "id": "active_vs_passive",
        "category": "技术分析",
        "title": "主动上涨 vs 被动反弹",
        "description": "主动上涨的股票：指数上涨时起步→指数回调时稳住保持上升趋势→指数回暖直接猛上。被动反弹：找不到技术理由，最大理由就是跌得够久，最强板块下跌时偷袭。",
        "source": "014_被动上涨",
        "key_quotes": [
            "什么是主动上涨，指数上涨的时候起步，指数回调的时候稳住保持上升趋势，指数回暖直接猛上。这就是很好的节奏。",
            "被动反弹，从技术指标上找不到多少上涨的理由，最大的理由就是跌得够久了。"
        ]
    },
    {
        "id": "test_by_decline",
        "category": "技术分析",
        "title": "真金还需火炼——下跌检验上涨成色",
        "description": "任何股票/方向的上涨成色需要通过下跌来检验。在指数下跌中保持稳定、或受影响后迅速收回失地的方向才是真正强势的方向。",
        "source": "029_真金还需火炼",
        "key_quotes": [
            "任何一个股票，一个方向，上涨的成色，是需要靠下跌来检验的。",
            "在指数下跌的时候，我们应该去寻找的，就是这样一些不受外力影响，保持自己走势的，或者是受影响下跌后在反弹过程中迅速收回失地的方向。",
            "好的行情，会给你足够的机会上车。"
        ]
    },
    {
        "id": "main_uptrend_conditions",
        "category": "技术分析",
        "title": "主升浪的三个条件",
        "description": "①历史新高或一年新高（中短期无套牢盘）②一二十天内保持在主要均线之上（5日最好，10日也行）③均线需要向上发散。板块效应取决于有多少个股符合主升条件。",
        "source": "039_为什么今天机器人涨不过算力",
        "key_quotes": [
            "什么是主升，我觉得至少要满足这样几个条件。首先，应该是历史新高，或者是一年新高。其次，应该在相当长一段时间里面保持在主要均线之上。均线需要是向上发散的。",
            "永远应该保持空杯心态，给主升阶段的个股更高的地位。"
        ]
    },
    {
        "id": "three_patterns",
        "category": "买卖规则",
        "title": "极简交易手册：三种赚钱模式",
        "description": "①已出现上涨趋势的票，顺势买入（新高/贴均线/反包/变轨加速）②上升趋势已成，强势整理平台刚突破或即将突破 ③强势股第一次大跌至超跌（20-30%），只做第一次。这三种都算顺势买入。",
        "source": "033_极简交易手册",
        "key_quotes": [
            "赚简单的钱。",
            "垃圾的股各有各的不同，而牛股总是相似的。",
            "逆势的机会比顺势的机会少很多。"
        ]
    },
    {
        "id": "oscillation_center",
        "category": "买卖规则",
        "title": "不要浪费任何一次振荡中枢",
        "description": "振荡中枢（横盘整理平台）是极佳的上车机会。横盘意味着筹码交换充分，突破后的持续性更强。突破后回踩中枢不破，往往是加仓良机。",
        "source": "015_怎样选出最强的股; P02_从交易角度看待AI应用",
        "key_quotes": [
            "不要浪费任何一次振荡中枢。",
            "能稳住，远比冲得快要重要。",
            "说明这里面是有一些耐心资本在这里面蓄力。"
        ]
    },
    {
        "id": "buy_expectation",
        "category": "买卖规则",
        "title": "买入符合预期，卖出不及预期",
        "description": "每次买入或加仓，要买入符合预期甚至高于预期的，而不是低于预期的。弱于预期的都要小心。不及预期的方向/个股采用"不及预期就跑路"，核心持仓采用"等到趋势结束再说"。",
        "source": "023_你会加仓什么样的医药; 012_理解比抄作业更重要; 042_强与弱",
        "key_quotes": [
            "每一次买入或者加仓，尽量要买入符合预期，或者是高于预期的，而不是买低于预期的。",
            "当你预期它这个地方有阻力应该调整的时候，它走出了稳健的振荡，那么可以认为是正常，可以高看一眼。而当你期待它应该连续上拉的时候，它走出了拖泥带水的感觉，可能就该放低一点预期。",
            "不及预期就跑路（非核心方向）vs 等到趋势结束再说（核心方向）。"
        ]
    },
    {
        "id": "ma_system",
        "category": "技术分析",
        "title": "均线是所有指标中最重要的一种",
        "description": "MA5/10用于判断短期强度，MA20/60用于判断中期趋势，MA120/250用于判断长期趋势。跌破10日线快速拉回=非常漂亮的走势。有板块效应的方向跌破均线容忍度可稍高。",
        "source": "038_10倍比两倍更简单; 015_怎样选出最强的股; 025_指数转折时关注什么样的股票",
        "key_quotes": [
            "均线是所有指标中最重要的一种。",
            "回踩的时候短期跌破10日线，20日线，都是正常的。但是快速的拉回就是非常漂亮的走势了。",
            "如果是看好的、有板块效应的方向，那么容忍度可以稍高一些。"
        ]
    },
    {
        "id": "right_direction_over_cost",
        "category": "交易心理",
        "title": "正确的方向比成本更重要",
        "description": "在牛市/强势市场中，及时把仓位放到正确的方向上远比斤斤计较买入成本重要。涨停通常只是启动信号，不是终点。",
        "source": "043_牛市心法; 035_关于昨天的一些答疑",
        "key_quotes": [
            "正确的方向比成本重要。",
            "牛市里一段上涨空间不小，那么及时把自己的仓位放到正确的方向上，远比斤斤计较买得便宜要重要得多。",
            "涨停通常只是一个启动的信号。"
        ]
    },
    {
        "id": "die_best_direction",
        "category": "交易心理",
        "title": "要死，也要死在最好的方向上",
        "description": "即使判断错误需要止损，也要在自己最看好的、最强的主线方向上操作。不在杂毛上浪费仓位和时间。",
        "source": "016_为什么大跌",
        "key_quotes": [
            "要死，也要死在最好的方向上。",
            "放弃80%，专注20%。"
        ]
    },
    {
        "id": "see_what_not_why",
        "category": "交易心理",
        "title": "多看是什么，少问为什么",
        "description": "盘面已经告诉你强弱，不必深究原因。理由可以收盘后再想，但对操作意义不大。交易者不要去无谓地吵架站队，关注如何上车更重要。",
        "source": "043_牛市心法",
        "key_quotes": [
            "多看是什么，少问为什么。",
            "我哪知道啊！！！想这么多不耽误赚钱吗？？？",
            "盘面就告诉了你金融很强，华为很强。"
        ]
    },
    {
        "id": "bull_market_principles",
        "category": "交易心理",
        "title": "牛市的基本原则就那么一些",
        "description": "华尔街没有新鲜事，A股也没有。趋势从小变大，跌多了总会反弹，调整结束能往上冲。不管什么题材什么大小，总会遵循这些规律。投机如山丘一样古老。",
        "source": "020_9.15随便聊聊; 001_A股没有新鲜事",
        "key_quotes": [
            "永远要去追寻一些更持久的规律。去关注市场中不变的东西。",
            "市场上不变的是什么，趋势总是从小变大，跌多了总会反弹，结束了一段时间的调整大概能往上冲一段。",
            "华尔街没有新鲜事。不可能有，因为投机像山岳一样古老。"
        ]
    },
    {
        "id": "first_big_drop",
        "category": "买卖规则",
        "title": "强趋势股第一次大跌值得尝试",
        "description": "前期走势完好的强趋势股第一次大幅下跌（20-30%），可以考虑尝试反弹。但确定性不如趋势突破类型高。第二次、第三次大跌则风险大增。",
        "source": "040_各玩各的; 033_极简交易手册",
        "key_quotes": [
            "对于前期走势完好的强趋势股的第一次大幅下跌，可以考虑尝试一下反弹。",
            "这种一般最好只做第一次。在极短的时间内跌幅20%~30%是一个重要的点。"
        ]
    },
    {
        "id": "judge_strength",
        "category": "技术分析",
        "title": "判断强弱的正确方法",
        "description": "判断强弱不是简单看涨跌，要结合①大盘走势②自身位置。在压力位下收敛振荡不破均线=强；该涨的时候拖泥带水=弱。",
        "source": "042_强与弱",
        "key_quotes": [
            "判断一个票的强与弱，不能这么孤立地看，在判断的过程中，一要关注大盘的走势，二要结合自身的位置。",
            "在该涨的时候有没有好好涨，在该调整的时候，调整的形态怎么样，这些都是需要密切关注的。"
        ]
    },
    {
        "id": "cup_handle",
        "category": "技术分析",
        "title": "杯柄形态与口袋支点",
        "description": "中期走强（允许涨1倍左右）+ 短期调整（约1个月）= 最完美的买点。杯柄、旗形等经典形态的内涵都是这个：中期走强后短期结束调整。",
        "source": "P01_跌下来应该会有一些机会; 033_极简交易手册",
        "key_quotes": [
            "中期走强部分可以允许上涨达到1倍左右，短期调整的时间，按A股最近的走势，大约1个月左右是最好的。",
            "什么杯柄也好，旗形也好，其实其中内涵的意义，都是这个，中期走强，短期结束调整。那就是最完美的。"
        ]
    },
    {
        "id": "ten_x_thinking",
        "category": "交易心理",
        "title": "10倍比两倍更简单——聚焦思维",
        "description": "10x需要聚焦和放弃。把注意力放在核心20%区域，过滤所有噪音。放弃80%的空间不大的机会，专注可能产生超额收益的方向。",
        "source": "038_10倍比两倍更简单",
        "key_quotes": [
            "放弃80%，专注20%。",
            "聚焦，放弃那些空间不大的机会。",
            "注意力是人类最大的瓶颈，要把注意力放到核心的20%区域。"
        ]
    },
]

# 2. Evolution timeline
evolution = [
    {"phase": "早期（2023-2024初）", "focus": "出海、PCB/CPO", "key_learnings": "对标美股思维有效，顺势做趋势股；月线级别底部判断"},
    {"phase": "2024年中", "focus": "金融、机器人萌芽", "key_learnings": "上证50领导指数判断；底部构筑需要一年或更长；权重领涨不同于小票超跌"},
    {"phase": "2024下半年", "focus": "机器人、AI硬件", "key_learnings": "摆脱对标思维，国产科技独立行情；主升浪条件明确化；杯柄/口袋支点系统化"},
    {"phase": "2025上半年", "focus": "机器人持续、医药、消费", "key_learnings": "牛市心法成熟（多看是什么少问为什么）；主动vs被动上涨；10x聚焦思维"},
    {"phase": "2025下半年", "focus": "存储/芯片、新能源", "key_learnings": "极简交易手册三模式；找到不一样的点；板块轮动节奏（进攻→防守→进攻）"},
    {"phase": "2026至今", "focus": "半导体产业链全面看好", "key_learnings": "半导体设备/存储/洁净室；牛市下半场振荡加大但新高必然；流动性驱动的结构性行情"},
]

# 3. Sector rotation framework
sector_framework = {
    "进攻型": {
        "description": "市场强势时配置，弹性大、趋势强",
        "sectors": ["半导体/存储", "AI硬件(CPO/PCB/铜缆)", "机器人/智能制造"],
        "signal": "均线多头排列批量出现，板块指数突破，新高个股增多"
    },
    "防御/补涨型": {
        "description": "市场调整或振荡时配置，位置低、估值合理",
        "sectors": ["医药/创新药", "消费/白酒", "新能源/光伏"],
        "signal": "跌到关键支撑（年线/60日线），出现底部放量或收敛形态"
    },
    "周期型": {
        "description": "涨价或政策驱动，阶段性参与",
        "sectors": ["有色/稀土", "金融/券商", "电力设备"],
        "signal": "商品价格标杆确认，政策催化，低位平台突破"
    }
}

# 4. Track record of stocks mentioned
stock_mentions = [
    {"stock": "寒武纪", "code": "sh688256", "context": "国产科技核心，对标英伟达的独立行情", "period": "2024-2026"},
    {"stock": "长川科技", "code": "sz300604", "context": "半导体设备'明牌'，类比光模块时期的新易盛", "period": "2025-2026"},
    {"stock": "兆易创新", "code": "sh603986", "context": "存储最稳健选择，杯柄形态典范", "period": "2025-2026"},
    {"stock": "江波龙", "code": "sz301308", "context": "存储模组弹性标的，大级别突破", "period": "2025-2026"},
    {"stock": "香农芯创", "code": "sz300857", "context": "存储第一眼看中的标的，三波加速后谨慎", "period": "2025"},
    {"stock": "德明利", "code": "sz300672", "context": "存储模组，与香农/江波龙节奏相近", "period": "2025-2026"},
    {"stock": "北方华创", "code": "sz002371", "context": "半导体设备龙头", "period": "2026"},
    {"stock": "柯力传感", "code": "sh688662", "context": "机器人核心票，标准杯柄形态", "period": "2024-2025"},
    {"stock": "新易盛", "code": "sz300502", "context": "CPO代表，三次买点的经典回顾案例", "period": "2023-2025"},
    {"stock": "深南电路", "code": "sz002916", "context": "PCB核心，类比宇通客车一月的突破调整", "period": "2024-2026"},
    {"stock": "亚翔集成", "code": "sh603929", "context": "洁净室龙头，半导体扩产直接受益", "period": "2025-2026"},
    {"stock": "成都先导", "code": "sh688222", "context": "医药中走势最强势的代表之一", "period": "2025-2026"},
    {"stock": "东方财富", "code": "sz300059", "context": "金融科技核心，牛市风向标", "period": "2024-2025"},
]

# 5. Key quotes collection
key_quotes = [
    {"quote": "新高是每一个牛股的必由之路，那就在必由之路上守它。", "topic": "选股"},
    {"quote": "截断亏损，让利润飞。", "topic": "风控"},
    {"quote": "垃圾的股各有各的不同，而牛股总是相似的。", "topic": "选股"},
    {"quote": "知道和拿住，其中仍然有不小的差距。", "topic": "交易心理"},
    {"quote": "如果在白宫没有熟人，最好还是多看K线。", "topic": "技术分析"},
    {"quote": "好的行情，会给你足够的机会上车。", "topic": "交易心理"},
    {"quote": "永远去追寻一些更持久的规律。", "topic": "交易心理"},
    {"quote": "投机如山丘一样古老。", "topic": "交易心理"},
    {"quote": "对牛股历史走势的反复揣摩，才是该出手时就出手的保证。", "topic": "学习方法"},
    {"quote": "在相对高位的时候，还要能想到它去到更高的位置。做交易这个事情，想象力非常重要。", "topic": "交易心理"},
    {"quote": "左侧尽量保证自己的安全，右侧那要有耐心。", "topic": "买卖规则"},
    {"quote": "大多数时候牛票的买点其实比以往更难以把握。", "topic": "买卖规则"},
    {"quote": "主线这种说法...并不是常常都有的。很多时候，没有就是没有。", "topic": "市场认知"},
    {"quote": "永远应该保持空杯心态，给主升阶段的个股更高的地位。", "topic": "交易心理"},
    {"quote": "每支票都要想一下它和别的有什么区别，有没有区分度。", "topic": "选股"},
]

# Build final output
existing = {}
if os.path.exists(DST):
    with open(DST, 'r', encoding='utf-8') as f:
        existing = json.load(f)

output = {
    **existing,
    "wechat_articles": {
        "count": len(articles),
        "date_range": "2023-06 ~ 2026-04",
        "articles": [
            {
                "file": m['file'],
                "title": m['title'],
                "date": m.get('date', ''),
                "url": m.get('url', ''),
                "word_count": m.get('word_count', 0),
            }
            for m, _ in articles
        ]
    },
    "methodology_rules": methodology_rules,
    "evolution": evolution,
    "sector_framework": sector_framework,
    "stock_mentions": stock_mentions,
    "key_quotes": key_quotes,
    "updated_at": datetime.now().strftime('%Y-%m-%d %H:%M'),
}

with open(DST, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"Saved enriched analysis_data.json ({len(json.dumps(output, ensure_ascii=False))} bytes)")
print(f"  Methodology rules: {len(methodology_rules)}")
print(f"  Evolution phases: {len(evolution)}")
print(f"  Stock mentions: {len(stock_mentions)}")
print(f"  Key quotes: {len(key_quotes)}")
print(f"  WeChat articles: {len(articles)}")
