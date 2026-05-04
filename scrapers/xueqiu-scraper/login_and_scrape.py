"""
Step 1: Open visible browser for manual Xueqiu login
Step 2: After login, auto-scrape ALL 20,540 posts via API
Step 3: Save results
"""
import sys, os, json, re, time
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

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


def fetch_all_posts(context, page, user_id):
    """Fetch all timeline posts using Playwright's native API (auto-cookies)."""
    all_posts = []
    seen_ids = set()
    max_id = 0
    max_pages = 1500

    while len(all_posts) < 100000 and max_pages > 0:
        url = f"https://xueqiu.com/v4/statuses/user_timeline.json?user_id={user_id}&count=20"
        if max_id > 0:
            url += f"&max_id={max_id}"

        try:
            resp = context.request.get(url, headers={
                'Accept': 'application/json, text/plain, */*',
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': f'https://xueqiu.com/u/{user_id}',
            })
        except Exception as e:
            log(f"  [网络错误] max_id={max_id}: {e}")
            time.sleep(2)
            continue

        if resp.status != 200:
            body = resp.text()[:300]
            log(f"  [错误] max_id={max_id}: HTTP {resp.status} - {body}")
            if '10022' in body or 'login' in body.lower() or '登录' in body:
                log("  -> 需要登录，请确认登录成功后重新运行")
            break

        try:
            data = resp.json()
        except:
            log(f"  [JSON解析失败] max_id={max_id}: {resp.text()[:200]}")
            break

        statuses = data.get('statuses', data.get('list', []))
        count = len(statuses)
        total = data.get('total', 0)
        max_page = data.get('maxPage', 0)
        page = data.get('page', 0)

        if count == 0:
            log(f"  max_id={max_id}: 没有更多帖子, total={total}")
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

        log(f"  [第{page}/{max_page}页] max_id={max_id}: 获取{count}条, 新增{new_count}条 (累计{len(all_posts)}/{total})")

        if total and len(all_posts) >= total:
            log(f"  -> 全部帖子已获取!")
            break

        if statuses:
            max_id = statuses[-1]['id'] - 1
        else:
            break

        max_pages -= 1
        time.sleep(0.4)

    return all_posts


def main():
    all_posts = []
    articles = []

    with sync_playwright() as p:
        # STEP 1: Open VISIBLE browser for manual login
        log("=" * 60)
        log("[STEP 1] 打开浏览器，请在窗口中登录雪球")
        log("=" * 60)
        log("1. 浏览器窗口已打开")
        log("2. 请点击右上角【登录】，用手机号/微信扫码登录")
        log("3. 登录成功后回到此窗口，按 Enter 继续...")
        log("")

        browser = p.chromium.launch(
            headless=False,  # VISIBLE browser
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
        )
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1200, 'height': 800},
            locale='zh-CN',
        )
        page = context.new_page()

        # Go to login page
        page.goto("https://xueqiu.com/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        # Check if already logged in, otherwise wait for user to login
        logged_in = page.evaluate("""() => {
            return !!(window.SNOWMAN_USER && window.SNOWMAN_USER.id);
        }""")
        if logged_in:
            log("[*] 检测到已登录状态，无需重新登录")
        else:
            log("[*] 请在浏览器窗口中完成登录（微信扫码或手机号），登录后会自动检测并继续...")
            log("[*] 不会自动刷新，请放心操作。登录成功后手动刷新一下页面即可。")
            # Poll for login status - check every 5 seconds, no navigation
            for attempt in range(60):  # up to 5 minutes
                time.sleep(5)
                is_logged = page.evaluate("""() => {
                    return !!(window.SNOWMAN_USER && window.SNOWMAN_USER.id);
                }""")
                if is_logged:
                    log(f"[+] 检测到登录成功！(等待了 {(attempt+1)*5} 秒)")
                    break
                if attempt == 6:  # ~30s
                    log("  等待中... 登录成功后会检测到")
                if attempt == 18:  # ~90s
                    log("  仍在等待... 请确保登录后刷新一下页面 (F5)")
            else:
                log("[!] 等待超时 (5分钟)，将尝试继续抓取...")

        # Verify login
        page.goto("https://xueqiu.com/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        user_info = page.evaluate("""() => {
            if (window.SNOWMAN_USER && window.SNOWMAN_USER.id) {
                return {id: window.SNOWMAN_USER.id, name: window.SNOWMAN_USER.screen_name};
            }
            return null;
        }""")

        if user_info:
            log(f"[+] 确认登录状态: {user_info.get('name', 'unknown')} (ID: {user_info.get('id', 'unknown')})")
        else:
            log("[!] 检测不到登录状态，将尝试继续（可能只能抓取公开页面的内容）...")

        # Save cookies for future use
        cookies = context.cookies()
        cookie_path = os.path.join(OUTPUT_DIR, "cookies_logged_in.json")
        with open(cookie_path, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        log(f"[+] 已保存 {len(cookies)} 个 cookies 到 {cookie_path}")

        # STEP 2: Navigate to target user page and start scraping
        log(f"\n[STEP 2] 开始抓取 直到一万点 (ID: {USER_ID}) 的所有帖子...")
        log("=" * 60)

        page.goto(f"https://xueqiu.com/u/{USER_ID}", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        # STEP 2a: Fetch all timeline posts via Playwright's native API
        log("\n[*] Phase A: 抓取全部帖子 (timeline)...")
        seen_ids = set()
        all_posts = fetch_all_posts(context, page, USER_ID)

        # STEP 2b: Fetch full text for truncated/long posts
        log(f"\n[*] Phase B: 展开长文...")
        long_posts = [p for p in all_posts if p.get('truncated') or p.get('type') == '3']
        log(f"  发现 {len(long_posts)} 篇长文")

        articles = []
        for i, post in enumerate(long_posts):
            target = post.get('target', '')
            if not target:
                continue
            try:
                resp = context.request.get(f"https://xueqiu.com{target}", headers={
                    'Accept': 'text/html',
                })
                if resp.status == 200:
                    html = resp.text()
                    # Extract article content
                    idx = html.find('article__bd')
                    if idx == -1:
                        idx = html.find('article-content')
                    if idx == -1:
                        idx = html.find('class="detail')
                    if idx != -1:
                        start = html.find('>', idx) + 1
                        end = html.find('</article>', start)
                        if end == -1:
                            end = html.find('</div></div></div>', start)
                        if end != -1:
                            content = html[start:end]
                            content = re.sub(r'<[^>]*>', '', content).strip()
                            post['full_text'] = content
                if (i + 1) % 10 == 0:
                    log(f"    [{i+1}/{len(long_posts)}] 展开中...")
            except Exception as e:
                pass
            time.sleep(0.3)

        # STEP 2c: Try to get columns (专栏)
        log(f"\n[*] Phase C: 抓取专栏...")
        try:
            resp = context.request.get(
                f"https://xueqiu.com/v4/columns/user_columns.json?user_id={USER_ID}&page=1&count=50",
                headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'}
            )
            if resp.status == 200:
                data = resp.json()
                cols = data.get('columns', data.get('list', []))
                log(f"  找到 {len(cols)} 篇专栏")
                for col in cols:
                    articles.append({
                        'id': col.get('id', ''),
                        'title': col.get('title', ''),
                        'description': re.sub(r'<[^>]*>', '', col.get('description', '') or ''),
                        'created_at': col.get('created_at', ''),
                        'view_count': col.get('view_count', 0),
                        'target': col.get('target', ''),
                    })
        except Exception as e:
            log(f"  专栏抓取异常: {e}")

        browser.close()

    return all_posts, articles


if __name__ == "__main__":
    posts, articles = main()

    log(f"\n{'='*60}")
    log(f"[完成] 抓取完毕!")
    log(f"  帖子总数: {len(posts)}")
    log(f"  专栏文章: {len(articles)}")
    log(f"{'='*60}")

    # Save all posts
    posts_path = os.path.join(OUTPUT_DIR, "all_posts_complete.json")
    with open(posts_path, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)
    log(f"\n[+] 帖子已保存: {posts_path}")

    # Save articles
    articles_path = os.path.join(OUTPUT_DIR, "articles.json")
    with open(articles_path, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    log(f"[+] 专栏已保存: {articles_path}")

    # Print date range
    if posts:
        dates = sorted([p.get('created_at', 0) for p in posts if p.get('created_at')], reverse=True)
        if dates:
            log(f"\n[*] 时间范围: {ts_to_date(dates[-1])} ~ {ts_to_date(dates[0])}")
            log(f"[*] 最新5条:")
            for i, p in enumerate(posts[:5]):
                created = ts_to_date(p.get('created_at', 0))
                text = p.get('text_clean', p.get('text', ''))[:200]
                log(f"  [{i+1}] {created}")
                log(f"      {text}...")
