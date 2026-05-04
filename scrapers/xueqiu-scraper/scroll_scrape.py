"""Full scraper using page-based pagination only (tested working with cookies)."""
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

all_posts = []
seen = set()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True,
        args=['--disable-blink-features=AutomationControlled', '--no-sandbox'])
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        viewport={'width': 1200, 'height': 800}, locale='zh-CN')

    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            context.add_cookies(json.load(f))
        log("[*] 已加载 cookies")

    page = context.new_page()
    page.goto(f"https://xueqiu.com/u/{USER_ID}", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4000)
    log(f"  Title: {page.title()}")

    log("\n[*] 开始 page 分页抓取...")
    total = None
    total_pages = None

    for pg in range(1, 2000):
        result = page.evaluate("""
            async (args) => {
                const url = `/v4/statuses/user_timeline.json?user_id=${args.uid}&page=${args.pg}`;
                const r = await fetch(url, {
                    headers: {'Accept':'application/json','X-Requested-With':'XMLHttpRequest'}, credentials:'include'});
                if (!r.ok) return {err:true, st:r.status, txt:await r.text()};
                const d = await r.json();
                return {err:false, sts:(d.statuses||d.list||[]).map(s=>({id:s.id,title:s.title||'',
                    text:(s.text||s.description||''),created_at:s.created_at,type:s.type,
                    retweet_count:s.retweet_count||0,reply_count:s.reply_count||0,
                    view_count:s.view_count||0,fav_count:s.fav_count||0,
                    truncated:s.truncated||false,target:s.target||''})),
                    total:d.total,page:d.page,maxPage:d.maxPage,count:d.count};
            }
        """, {"uid": USER_ID, "pg": pg})

        if result.get('err'):
            log(f"  [Page {pg}] ERROR: HTTP {result.get('st')} - {result.get('txt','')[:200]}")
            if '10022' in result.get('txt','') or '登录' in result.get('txt',''):
                log("  -> 登录失效")
            break

        sts = result.get('sts', [])
        count = result.get('count', len(sts))
        total = result.get('total', total)
        total_pages = result.get('maxPage', total_pages)
        page_num = result.get('page', pg)

        if not sts:
            log(f"  [Page {pg}] 空, 抓取完成")
            break

        new_count = 0
        for s in sts:
            if s['id'] not in seen:
                seen.add(s['id'])
                raw = s.get('text', '')
                clean = re.sub(r'<[^>]*>', '', raw).replace('&amp;','&').replace('&lt;','<').replace('&gt;','>').replace('&quot;','"').replace('&#x27;',"'").replace('&nbsp;',' ')
                s['text'] = clean.strip()
                all_posts.append(s)
                new_count += 1

        pct = f"{len(all_posts)/total*100:.1f}%" if total else "?"
        tp = f"/{total_pages}" if total_pages else ""
        log(f"  [Page {page_num}{tp}] +{new_count}条 (累计{len(all_posts)}/{total} = {pct})")

        time.sleep(0.3)

    browser.close()

# Save
posts_path = os.path.join(OUTPUT_DIR, "all_posts_final.json")
with open(posts_path, "w", encoding="utf-8") as f:
    json.dump(all_posts, f, ensure_ascii=False, indent=2)

log(f"\n{'='*60}")
log(f"[完成] 共 {len(all_posts)} 条帖子 (总计 {total or '?'})")
log(f"[+] {posts_path}")
if all_posts:
    dates = [p.get('created_at',0) for p in all_posts if p.get('created_at')]
    if dates:
        log(f"[*] 时间跨度: {datetime.fromtimestamp(min(dates)/1000).strftime('%Y-%m-%d')} ~ {datetime.fromtimestamp(max(dates)/1000).strftime('%Y-%m-%d')}")
    log(f"[*] 最新: {all_posts[0].get('text','')[:120]}")
    log(f"[*] 最早: {all_posts[-1].get('text','')[:120]}")
