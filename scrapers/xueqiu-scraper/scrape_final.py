"""
Final scraper:
- Uses regular browser context (simpler, more reliable)
- Saves/loads cookies for login persistence
- Makes API calls from within browser page.evaluate (bypasses WAF)
"""
import sys, os, json, re, time
from datetime import datetime
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

USER_ID = "7845696728"
OUTPUT_DIR = r"D:\stock\data"
COOKIE_FILE = os.path.join(OUTPUT_DIR, "cookies.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def log(msg):
    try: print(msg)
    except: print(msg.encode('ascii', errors='replace').decode('ascii'))


def ts_to_date(ts_ms):
    if ts_ms:
        return datetime.fromtimestamp(ts_ms / 1000).strftime('%Y-%m-%d %H:%M')
    return 'unknown'


all_posts = []
seen_ids = set()

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

    # Load saved cookies if exist
    if os.path.exists(COOKIE_FILE):
        log("[*] 加载已保存的 cookies...")
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            saved_cookies = json.load(f)
        context.add_cookies(saved_cookies)
        log(f"  加载了 {len(saved_cookies)} 个 cookies")

    page = context.new_page()

    # Check login
    page.goto("https://xueqiu.com/", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4000)

    logged_in = page.evaluate("() => !!(window.SNOWMAN_USER && window.SNOWMAN_USER.id)")
    user_name = page.evaluate("() => (window.SNOWMAN_USER && window.SNOWMAN_USER.screen_name) || ''")

    if logged_in:
        log(f"[+] Cookie 有效，已登录: {user_name}")
    else:
        log("[*] 未登录。请在浏览器中登录雪球，登录后刷新页面(F5)即可...")
        for attempt in range(120):
            time.sleep(3)
            try:
                lg = page.evaluate("() => !!(window.SNOWMAN_USER && window.SNOWMAN_USER.id)")
            except:
                lg = False
            if lg:
                uname = page.evaluate("() => (window.SNOWMAN_USER && window.SNOWMAN_USER.screen_name) || ''")
                log(f"[+] 登录成功: {uname}")
                break
            if attempt == 15:
                log("  (~45秒) 等待登录...")
            if attempt == 40:
                log("  (~2分钟) 仍在等待...")
        else:
            log("[!] 超时")

    # Save cookies
    cookies = context.cookies()
    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)
    log(f"[+] Cookies 已保存 ({len(cookies)} 个)，下次启动无需重新登录")

    # Also save localStorage (has auth tokens)
    local_storage = page.evaluate("""() => {
        const items = {};
        for (let i = 0; i < localStorage.length; i++) {
            const k = localStorage.key(i);
            items[k] = localStorage.getItem(k);
        }
        return items;
    }""")
    with open(os.path.join(OUTPUT_DIR, "localStorage.json"), "w", encoding="utf-8") as f:
        json.dump(local_storage, f, ensure_ascii=False, indent=2)

    # ============================================================
    # Call API from within the browser (bypasses WAF)
    # ============================================================
    log(f"\n{'='*60}")
    log(f"[STEP 2] 抓取 直到一万点的所有帖子")
    log("=" * 60)

    page.goto(f"https://xueqiu.com/u/{USER_ID}", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    # Test page 1 first
    log("\n[*] 测试 API page=1...")
    test_result = page.evaluate("""
        async () => {
            const resp = await fetch('/v4/statuses/user_timeline.json?user_id=' + 7845696728 + '&page=1', {
                headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                credentials: 'include',
            });
            const data = await resp.json();
            return {
                ok: resp.ok,
                status: resp.status,
                count: (data.statuses || []).length,
                total: data.total,
                maxPage: data.maxPage,
                page: data.page,
            };
        }
    """)
    log(f"  Page 1: ok={test_result.get('ok')}, status={test_result.get('status')}, "
        f"count={test_result.get('count')}, total={test_result.get('total')}, "
        f"maxPage={test_result.get('maxPage')}")

    # Test page 2 - the problem area
    log("\n[*] 测试 API page=2 (关键)...")
    test2 = page.evaluate("""
        async () => {
            const resp = await fetch('/v4/statuses/user_timeline.json?user_id=7845696728&page=2', {
                headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                credentials: 'include',
            });
            const text = await resp.text();
            let json = null;
            try { json = JSON.parse(text); } catch(e) {}
            return {
                ok: resp.ok,
                status: resp.status,
                text: text.substring(0, 500),
                count: json ? (json.statuses || []).length : -1,
            };
        }
    """)
    log(f"  Page 2: ok={test2.get('ok')}, status={test2.get('status')}")
    log(f"  Response: {test2.get('text', '')[:300]}")
    log(f"  Count: {test2.get('count', '?')}")

    if test2.get('ok') and test2.get('count', 0) >= 0:
        log("\n[+] Page 2 可访问！开始抓取全部帖子...")
        log("=" * 60)

        max_id = 0
        for pg in range(1, 2000):
            # Use page-based pagination first
            if pg == 1:
                url_arg = f"user_id={USER_ID}&page=1"
            else:
                url_arg = f"user_id={USER_ID}&page={pg}"

            result = page.evaluate("""
                async (args) => {
                    const resp = await fetch('/v4/statuses/user_timeline.json?' + args, {
                        headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                        credentials: 'include',
                    });
                    if (!resp.ok) return { error: true, status: resp.status, text: await resp.text() };
                    const data = await resp.json();
                    const statuses = data.statuses || data.list || [];
                    return { error: false, count: statuses.length, total: data.total, page: data.page, maxPage: data.maxPage,
                        statuses: statuses.map(s => ({id: s.id, title: s.title||'', text: s.text||s.description||'',
                            created_at: s.created_at, type: s.type, retweet_count: s.retweet_count||0, reply_count: s.reply_count||0,
                            view_count: s.view_count||0, fav_count: s.fav_count||0, truncated: s.truncated||false, target: s.target||''})) };
                }
            """, url_arg)

            if result.get('error'):
                log(f"  [第{pg}页] 错误: {result.get('status')} - {result.get('text', '')[:200]}")
                # Fallback: try max_id
                if all_posts:
                    last_id = all_posts[-1]['id']
                    fallback_arg = f"user_id={USER_ID}&max_id={last_id - 1}&count=20"
                    log(f"  -> 降级 max_id={last_id - 1}")
                    result = page.evaluate("""
                        async (args) => {
                            const resp = await fetch('/v4/statuses/user_timeline.json?' + args, {
                                headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                                credentials: 'include',
                            });
                            if (!resp.ok) return { error: true, status: resp.status, text: await resp.text() };
                            const data = await resp.json();
                            const statuses = data.statuses || data.list || [];
                            return { error: false, count: statuses.length, total: data.total, page: data.page, maxPage: data.maxPage,
                                statuses: statuses.map(s => ({id: s.id, title: s.title||'', text: s.text||s.description||'',
                                    created_at: s.created_at, type: s.type, retweet_count: s.retweet_count||0, reply_count: s.reply_count||0,
                                    truncated: s.truncated||false, target: s.target||''})) };
                        }
                    """, fallback_arg)
                    if result.get('error'):
                        log(f"  max_id 也失败: {result.get('text', '')[:200]}")
                        break
                else:
                    break

            if result.get('error'):
                break

            statuses = result.get('statuses', [])
            count = len(statuses)
            total = result.get('total', 0)
            page_num = result.get('page', 0)

            if count == 0:
                log(f"  [第{pg}轮] 空，结束")
                break

            new_count = 0
            for s in statuses:
                sid = s.get('id')
                if sid not in seen_ids:
                    seen_ids.add(sid)
                    raw = s.get('text', '')
                    clean = re.sub(r'<[^>]*>', '', raw)
                    clean = clean.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&#x27;', "'").replace('&nbsp;', ' ')
                    s['text_clean'] = clean.strip()
                    all_posts.append(s)
                    new_count += 1

            pct = f"{(len(all_posts)/total*100):.1f}%" if total else "?"
            log(f"  [第{page_num}页/{result.get('maxPage','?')}] +{new_count}条 (累计{len(all_posts)}/{total} = {pct})")

            if total and len(all_posts) >= total:
                log("  -> 全部完成!")
                break

            time.sleep(0.5)
    else:
        log("\n[!] Page 2 仍然不可访问。雪球限制未登录用户只能查看第一页。")
        log("[!] 可能需要用目标用户自己的登录态。请确认你登录的账号能否查看该用户第2页。")

    # Save
    posts_path = os.path.join(OUTPUT_DIR, "all_posts_final.json")
    with open(posts_path, "w", encoding="utf-8") as f:
        json.dump(all_posts, f, ensure_ascii=False, indent=2)

    log(f"\n{'='*60}")
    log(f"[结果] 共获取 {len(all_posts)} 条帖子")
    log(f"[+] 保存: {posts_path}")
    if all_posts:
        dates = [p.get('created_at', 0) for p in all_posts if p.get('created_at')]
        if dates:
            log(f"[*] 时间范围: {ts_to_date(min(dates))} ~ {ts_to_date(max(dates))}")
        log(f"[*] 最新3条:")
        for i, p in enumerate(all_posts[:3]):
            log(f"  [{i+1}] {ts_to_date(p.get('created_at', 0))}: {p.get('text_clean', p.get('text', ''))[:150]}...")

    log(f"\n浏览器保持打开中。可以手动关闭。")
    log("按 Ctrl+C 退出...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log("\n退出。")
