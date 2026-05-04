"""
Central configuration for the stock dashboard project.
Single source of truth for all paths, settings, and constants.
"""
from pathlib import Path

# ================================================================
# Base directories
# ================================================================
ROOT = Path(r"D:\stock")
DATA = ROOT / "data"
KB = ROOT / "knowledge_base"

# Data subdirectories
SCREENER_DIR = DATA / "screener"
WEB_DIR = DATA / "web"
WECHAT_DIR = DATA / "wechat_articles"
XUEQIU_DIR = DATA / "xueqiu_posts"
CACHE_DIR = DATA / "cache"
LOG_DIR = SCREENER_DIR / "logs"

# Ensure directories exist
for d in [SCREENER_DIR, WEB_DIR, WECHAT_DIR, XUEQIU_DIR, CACHE_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ================================================================
# Database paths
# ================================================================
SCREENER_DB = str(SCREENER_DIR / "screener.db")
CACHE_DB = str(CACHE_DIR / "api_cache.db")

# ================================================================
# Web server
# ================================================================
WEB_PORT = 8080
WEB_HOST = "127.0.0.1"

# ================================================================
# API settings
# ================================================================
API_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
API_REFERER = 'https://finance.sina.com.cn'
API_TIMEOUT = 15
API_RETRIES = 3
API_RETRY_DELAY = 1.5
API_DELAY_INDEX = 0.2       # seconds between index API calls
API_DELAY_STOCK = 0.15      # seconds between stock API calls
API_DELAY_SECTOR = 0.3      # seconds between sector processing

# Cache TTLs (minutes)
KLINE_CACHE_TTL_MINUTES = 240   # 4 hours
QUOTE_CACHE_TTL_MINUTES = 5     # 5 minutes
INDEX_CACHE_TTL_MINUTES = 60    # 1 hour

# ================================================================
# Sina Finance API endpoints
# ================================================================
KLINE_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={code}&scale=240&ma=no&datalen={count}"
QUOTE_URL = "https://hq.sinajs.cn/list={code}"

# ================================================================
# Index definitions
# ================================================================
INDEX_CODES = {
    '上证指数': 'sh000001',
    '深证成指': 'sz399001',
    '创业板指': 'sz399006',
    '科创50': 'sh000688',
    '沪深300': 'sh000300',
    '上证50': 'sh000016',
    '中证1000': 'sh000852',
    '中证500': 'sh000905',
}

# ================================================================
# Sector definitions with representative stocks
# ================================================================
SECTORS = {
    '半导体': [
        'sh688981', 'sz002371', 'sh688012', 'sh688072', 'sz300604',
        'sz300672', 'sh600703', 'sh688256', 'sz002049', 'sz002156',
        'sh688396', 'sz300661',
    ],
    '光模块/算力': [
        'sz300308', 'sz300502', 'sz300394', 'sz300570', 'sz002916',
        'sz300548', 'sh601138', 'sz300638', 'sz300620',
    ],
    '存储/芯片': [
        'sz300857', 'sz300474', 'sh688525', 'sh688110', 'sz300672',
        'sh688256', 'sh603986', 'sz002049', 'sz301308',
    ],
    '机器人/智造': [
        'sz300124', 'sz002396', 'sz300007', 'sz300228', 'sz300354',
        'sz002527', 'sz300024', 'sh688017', 'sz300660', 'sz300161',
    ],
    '医药/创新药': [
        'sz300759', 'sh688180', 'sh688266', 'sz000963', 'sz300347',
        'sh688276', 'sh688235', 'sz002653', 'sh600276',
    ],
    'AI/软件': [
        'sz300033', 'sh688111', 'sz002230', 'sh688981', 'sz300474',
        'sz300502', 'sh600536', 'sz300624',
    ],
    '新能源/光伏': [
        'sz300274', 'sh601012', 'sz300750', 'sz002459', 'sz300763',
        'sz300118', 'sh688599', 'sz300724',
    ],
    '消费/白酒': [
        'sh600519', 'sz000858', 'sz000568', 'sh600809', 'sz002304',
        'sh600887', 'sz000895',
    ],
    '金融/券商': [
        'sz300059', 'sh600030', 'sh601688', 'sz300033', 'sz002673',
        'sh601211',
    ],
    '国防军工': [
        'sh600760', 'sh600893', 'sz002013', 'sh688122', 'sz300034',
        'sz300722',
    ],
    '汽车/零部件': [
        'sh601238', 'sz002594', 'sh600104', 'sz300750', 'sz000625',
        'sh601633',
    ],
}

# ================================================================
# Scoring weights (max points per category, total = 100)
# ================================================================
SCORE_WEIGHTS = {
    'bullish_alignment': 40,   # 多头排列
    'breakout': 25,            # 突破/新高
    'momentum': 15,            # 趋势加速
    'volume': 10,              # 量价配合
    'fundamental': 10,         # 基本面（价格位置代理）
}

# ================================================================
# Market state thresholds
# ================================================================
BULL_THRESHOLD = 5        # ret60 > 5% + 多头排列 = 牛市
BEAR_THRESHOLD = -10      # ret60 < -10% + 空头排列 = 熊市

# ================================================================
# MA analysis settings
# ================================================================
MA_PERIODS = {
    'ma5': 5,
    'ma10': 10,
    'ma20': 20,
    'ma60': 60,
}
KLINE_LOOKBACK = 120  # trading days to fetch

# ================================================================
# Knowledge base file list (generated by builder script)
# ================================================================
KB_SECTIONS = [
    "01-投资哲学与底层信仰",
    "02-市场环境评估体系",
    "03-板块与方向选择",
    "04-个股筛选体系",
    "05-买入时机与买点体系",
    "06-卖出与止损纪律",
    "07-仓位管理与风险控制",
    "08-交易心理与纪律",
    "09-技术分析工具箱",
    "10-不同市场阶段的操作策略",
    "11-学习与成长路径",
    "12-经典语录精选",
    "13-经典案例研究",
    "14-常见错误与行为偏误",
    "15-行业与赛道分析框架",
]
