"""
Simpler approach:
1. Open browser for manual login
2. Extract cookies to Python
3. Use Python requests with these cookies to call the API
"""
import sys, os, json, re, time
from datetime import datetime
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import requests
from playwright.sync_api import sync_playwright

USER_ID = "7845696728"
OUTPUT_DIR = r"D:\stock\data"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def log(msg):
    try: print(msg)
    except: print(msg.encode('ascii', errors='replace').decode('ascii'))


def ts_to_date(ts_ms):
    if ts_ms:
        return datetime.fromtimestamp(ts_ms / 1000).strftime('%Y-%m-%d %H:%M')
    return 'unknown'


log("=" * 60)
log("[STEP 1] 打开浏览器登录雪球")
log("=" * 60)
log("浏览器窗口已打开，请登录后刷新页面(F5)即可自动继续...")
log("")

cookies = []
with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
    )
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        viewport={'width': 1200, 'height': 800},
        locale='zh-CN',
    )
    page = context.new_page()
    page.goto("https://xueqiu.com/", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    # Wait for login
    logged_in = page.evaluate("() => !!(window.SNOWMAN_USER && window.SNOWMAN_USER.id)")
    if logged_in:
        log("[*] 已登录，无需重新登录")
    else:
        log("[*] 请在浏览器中登录雪球，登录后刷新页面(F5)即可...")
        for attempt in range(60):
            time.sleep(5)
            lg = page.evaluate("() => !!(window.SNOWMAN_USER && window.SNOWMAN_USER.id)")
            if lg:
                log(f"[+] 检测到登录！(等待 {(attempt+1)*5} 秒)")
                break
            if attempt == 6:
                log("  等待中... (~30秒)")
        else:
            log("[!] 超时，尝试继续...")

    # Get user info
    user_info = page.evaluate("""() => {
        if (window.SNOWMAN_USER && window.SNOWMAN_USER.id) {
            return {id: window.SNOWMAN_USER.id, name: window.SNOWMAN_USER.screen_name};
        }
        return null;
    }""")
    if user_info:
        log(f"[+] 当前用户: {user_info['name']} (ID: {user_info['id']})")

    # Get all cookies including HttpOnly ones
    cookies = context.cookies()
    log(f"[+] 获取了 {len(cookies)} 个 cookies")

    # Also get localStorage and sessionStorage tokens
    local_storage = page.evaluate("""() => {
        const items = {};
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            items[key] = localStorage.getItem(key);
        }
        return items;
    }""")
    log(f"[+] 获取了 {len(local_storage)} 个 localStorage 项")

    browser.close()

# Save cookies for inspection
with open(os.path.join(OUTPUT_DIR, "cookies.json"), "w", encoding="utf-8") as f:
    json.dump(cookies, f, ensure_ascii=False, indent=2)
with open(os.path.join(OUTPUT_DIR, "localStorage.json"), "w", encoding="utf-8") as f:
    json.dump(local_storage, f, ensure_ascii=False, indent=2)

log(f"\n[+] Cookies 和 localStorage 已保存到 {OUTPUT_DIR}")

# ============================================================
# STEP 2: Use Python requests with cookies to call API
# ============================================================
log(f"\n{'='*60}")
log("[STEP 2] 使用 cookies 调用 API 抓取所有帖子")
log("=" * 60)

session = requests.Session()

# Convert Playwright cookies to requests cookies
for c in cookies:
    session.cookies.set(c['name'], c['value'], domain=c.get('domain', ''))

# Set headers exactly like the browser
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Referer': f'https://xueqiu.com/u/{USER_ID}',
    'X-Requested-With': 'XMLHttpRequest',
    'Cache-Control': 'no-cache',
})

# Also add some critical localStorage tokens as cookies if they exist
for key in ['xq_a_token', 'xq_r_token', 'xq_token']:
    if key in local_storage:
        val = local_storage[key]
        session.cookies.set(key, val, domain='xueqiu.com')
        log(f"[*] Added localStorage token as cookie: {key}")

# Test the session
log("\n[*] 测试 API 访问...")
test_url = f"https://xueqiu.com/v4/statuses/user_timeline.json?user_id={USER_ID}&page=1&count=20"
try:
    test_resp = session.get(test_url, timeout=15)
    log(f"  Status: {test_resp.status_code}")
    if test_resp.status_code == 200:
        data = test_resp.json()
        log(f"  Posts: {len(data.get('statuses', []))}")
        log(f"  Total: {data.get('total', 'N/A')}")
        log(f"  maxPage: {data.get('maxPage', 'N/A')}")
        log(f"  Page size: {data.get('count', 'N/A')}")
    else:
        log(f"  Response: {test_resp.text[:500]}")
except Exception as e:
    log(f"  Error: {e}")

# Now fetch all pages
log("\n[*] 开始抓取全部帖子...")
all_posts = []
seen_ids = set()
max_id = 0
total_pages = None

for page_num in range(1, 2000):
    url = f"https://xueqiu.com/v4/statuses/user_timeline.json?user_id={USER_ID}&count=20"
    if max_id > 0:
        url += f"&max_id={max_id}"

    try:
        resp = session.get(url, timeout=15)
    except Exception as e:
        log(f"  [网络错误] 第{page_num}轮: {e}")
        time.sleep(2)
        continue

    if resp.status_code == 400:
        body = resp.text[:300]
        if '10022' in body or '登录' in body:
            log(f"  [第{page_num}轮] 登录失效!")
            log(f"  Cookie 可能已过期，需要重新登录")
        else:
            log(f"  [第{page_num}轮] HTTP 400: {body}")
        break

    if resp.status_code != 200:
        log(f"  [第{page_num}轮] HTTP {resp.status_code}: {resp.text[:200]}")
        if resp.status_code == 429:
            time.sleep(5)
            continue
        break

    try:
        data = resp.json()
    except:
        log(f"  [第{page_num}轮] JSON 解析失败: {resp.text[:300]}")
        break

    statuses = data.get('statuses', data.get('list', []))
    count = len(statuses)
    total = data.get('total', 0)
    max_page = data.get('maxPage', 0)
    page = data.get('page', 0)

    if total_pages is None:
        total_pages = max_page
        log(f"  [信息] 总共 {total} 条帖子, {max_page} 页")

    if count == 0:
        log(f"  [第{page_num}轮] 没有更多帖子")
        break

    new_count = 0
    for s in statuses:
        sid = s.get('id')
        if sid not in seen_ids:
            seen_ids.add(sid)
            raw = s.get('text', '') or s.get('description', '')
            clean = re.sub(r'<[^>]*>', '', raw)
            clean = clean.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&#x27;', "'").replace('&nbsp;', ' ')
            s['text_clean'] = clean.strip()
            all_posts.append(s)
            new_count += 1

    progress = f"{(len(all_posts)/total*100):.1f}%"
    log(f"  [第{page}/{max_page}页] 获取{count}条, 新增{new_count}条 (累计{len(all_posts)}/{total} = {progress})")

    if total and len(all_posts) >= total:
        log(f"  -> 全部帖子抓取完毕!")
        break

    if statuses:
        max_id = statuses[-1]['id'] - 1
    else:
        break

    time.sleep(0.3)

# Save all posts
posts_path = os.path.join(OUTPUT_DIR, "all_posts_complete.json")
with open(posts_path, "w", encoding="utf-8") as f:
    json.dump(all_posts, f, ensure_ascii=False, indent=2)

log(f"\n{'='*60}")
log(f"[完成] 共获取 {len(all_posts)} 条帖子")
log(f"[+] 已保存到: {posts_path}")

if all_posts:
    dates = [p.get('created_at', 0) for p in all_posts if p.get('created_at')]
    if dates:
        log(f"[*] 时间范围: {ts_to_date(min(dates))} ~ {ts_to_date(max(dates))}")
