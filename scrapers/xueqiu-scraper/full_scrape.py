"""
Resilient scraper - saves checkpoint every 100 pages, retries on errors, resume support.
"""
import sys, os, json, re, time
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright
from datetime import datetime

USER_ID = "7845696728"
OUTPUT_DIR = r"D:\stock\data"
COOKIE_FILE = os.path.join(OUTPUT_DIR, "cookies.json")
CHECKPOINT_FILE = os.path.join(OUTPUT_DIR, "checkpoint.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def log(msg):
    s = str(msg)
    try: print(s); sys.stdout.flush()
    except: print(s.encode('ascii','replace').decode()); sys.stdout.flush()

# Load checkpoint if exists
all_posts = []
seen = set()
start_page = 1
if os.path.exists(CHECKPOINT_FILE):
    log("[*] Loading checkpoint...")
    with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
        cp = json.load(f)
    all_posts = cp.get('posts', [])
    seen = set(p['id'] for p in all_posts)
    start_page = cp.get('next_page', 1)
    log(f"  Resuming from page {start_page}, {len(all_posts)} posts already saved")

log("="*60)
log(f"Xueqiu Scraper - starting from page {start_page}")
log("="*60)

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=['--disable-blink-features=AutomationControlled','--no-sandbox','--disable-gpu']
    )
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        viewport={'width':1200,'height':800}, locale='zh-CN')
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
            context.add_cookies(json.load(f))
        log("[*] Cookies loaded")

    page = context.new_page()
    page.goto(f"https://xueqiu.com/u/{USER_ID}", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4000)
    log(f"  Page: {page.title()}")

    total = None
    total_pages = None
    consecutive_errors = 0

    for pg in range(start_page, 2000):
        # Fetch with timeout via AbortController
        result = page.evaluate("""
            async (args) => {
                const controller = new AbortController();
                const timer = setTimeout(() => controller.abort(), 15000);
                try {
                    const url = '/v4/statuses/user_timeline.json?user_id=' + args.uid + '&page=' + args.pg;
                    const r = await fetch(url, {
                        headers: {'Accept':'application/json','X-Requested-With':'XMLHttpRequest'},
                        credentials:'include', signal: controller.signal });
                    clearTimeout(timer);
                    if (!r.ok) return {err:true, st:r.status, txt:await r.text()};
                    const d = await r.json();
                    const sts = d.statuses || d.list || [];
                    return {err:false, sts:sts.map(s=>({id:s.id,title:s.title||'',
                        text:s.text||s.description||'',created_at:s.created_at,type:s.type,
                        rt:s.retweet_count||0,rp:s.reply_count||0,vw:s.view_count||0,
                        fv:s.fav_count||0,truncated:s.truncated||false,target:s.target||''})),
                        total:d.total,page:d.page,maxPage:d.maxPage,count:d.count};
                } catch(e) {
                    clearTimeout(timer);
                    return {err:true, st:0, txt:'Timeout/Network Error: '+e.message};
                }
            }
        """, {"uid": USER_ID, "pg": pg})

        if result.get('err'):
            consecutive_errors += 1
            err_txt = result.get('txt','')
            log(f"  [Pg{pg}] ERR: {err_txt[:200]} (consecutive={consecutive_errors})")
            if '10022' in err_txt or 'login' in err_txt.lower():
                log("  Login expired!")
                break
            if consecutive_errors >= 5:
                log("  Too many consecutive errors, stopping")
                break
            time.sleep(3)  # Wait before retry
            continue

        consecutive_errors = 0
        sts = result.get('sts', [])
        c = result.get('count', len(sts))
        total = result.get('total', total)
        total_pages = result.get('maxPage', total_pages)
        page_num = result.get('page', pg)

        if not sts or c == 0:
            log(f"  [Pg{pg}] Empty page, finished")
            break

        new_count = 0
        for s in sts:
            sid = s['id']
            if sid not in seen:
                seen.add(sid)
                raw = s.get('text','')
                clean = re.sub(r'<[^>]*>','',raw).replace('&amp;','&').replace('&lt;','<').replace('&gt;','>').replace('&quot;','"').replace('&#x27;',"'").replace('&nbsp;',' ')
                s['text'] = clean.strip()
                all_posts.append(s)
                new_count += 1

        pct = f"{len(all_posts)/total*100:.1f}%" if total else "?"
        log(f"  [Pg{page_num}/{total_pages}] +{new_count} (total {len(all_posts)}/{total} {pct})")

        # Save checkpoint every 100 pages
        if pg % 100 == 0:
            cp = {'posts': all_posts, 'next_page': pg + 1}
            with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
                json.dump(cp, f, ensure_ascii=False)
            log(f"  [Checkpoint saved at page {pg}]")

        if total and len(all_posts) >= total:
            log("  ALL DONE!")
            break

        time.sleep(0.5)  # Polite delay

    browser.close()

# Final save
final_path = os.path.join(OUTPUT_DIR, "all_posts_final.json")
with open(final_path, 'w', encoding='utf-8') as f:
    json.dump(all_posts, f, ensure_ascii=False, indent=2)

log(f"\n{'='*60}")
log(f"FINAL: {len(all_posts)} posts (of {total})")
log(f"Saved: {final_path}")

if all_posts:
    dates = [p.get('created_at',0) for p in all_posts if p.get('created_at')]
    if dates:
        dmin = datetime.fromtimestamp(min(dates)/1000).strftime('%Y-%m-%d')
        dmax = datetime.fromtimestamp(max(dates)/1000).strftime('%Y-%m-%d')
        log(f"Date range: {dmin} ~ {dmax}")

# Clean checkpoint on success
if os.path.exists(CHECKPOINT_FILE) and len(all_posts) >= (total or 0):
    os.remove(CHECKPOINT_FILE)
    log("Checkpoint cleaned (all done!)")
else:
    log(f"Checkpoint saved at page {start_page}, will resume on next run")
