"""
Chunked scraper - scrapes in small batches, saves after each batch, restarts browser.
Survives stalls because each chunk is a fresh session.
"""
import sys, os, json, re, time
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright
from datetime import datetime

USER_ID = "7845696728"
OUTPUT_DIR = r"D:\stock\data"
COOKIE_FILE = os.path.join(OUTPUT_DIR, "cookies.json")
STATE_FILE = os.path.join(OUTPUT_DIR, "scrape_state.json")
FINAL_FILE = os.path.join(OUTPUT_DIR, "all_posts_final.json")
CHUNK_SIZE = 30  # Pages per chunk
os.makedirs(OUTPUT_DIR, exist_ok=True)

def log(msg):
    s = str(msg)
    try: print(s); sys.stdout.flush()
    except: print(s.encode('ascii','replace').decode()); sys.stdout.flush()

def do_chunk(start_page, existing_posts, seen_ids):
    """Scrape CHUNK_SIZE pages starting from start_page. Returns (new_posts, next_page, done)."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True,
            args=['--disable-blink-features=AutomationControlled','--no-sandbox','--disable-gpu'])
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            viewport={'width':1200,'height':800}, locale='zh-CN')

        if os.path.exists(COOKIE_FILE):
            with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
                context.add_cookies(json.load(f))

        page = context.new_page()
        page.goto(f"https://xueqiu.com/u/{USER_ID}", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        total = None
        posts = list(existing_posts)
        seen = set(seen_ids)
        last_page = start_page
        done = False

        for pg in range(start_page, start_page + CHUNK_SIZE):
            result = page.evaluate("""
                async (args) => {
                    const ctrl = new AbortController();
                    setTimeout(() => ctrl.abort(), 15000);
                    try {
                        const r = await fetch('/v4/statuses/user_timeline.json?user_id='+args.uid+'&page='+args.pg, {
                            headers: {'Accept':'application/json','X-Requested-With':'XMLHttpRequest'},
                            credentials:'include', signal: ctrl.signal });
                        if (!r.ok) return {err:true, st:r.status, txt:await r.text()};
                        const d = await r.json();
                        const sts = d.statuses || d.list || [];
                        return {err:false, sts:sts.map(s=>({id:s.id,title:s.title||'',
                            text:s.text||s.description||'',created_at:s.created_at,type:s.type,
                            rt:s.retweet_count||0,rp:s.reply_count||0,vw:s.view_count||0,
                            fv:s.fav_count||0,truncated:s.truncated||false,target:s.target||''})),
                            total:d.total,page:d.page,maxPage:d.maxPage,count:d.count};
                    } catch(e) { return {err:true, st:0, txt:'Timeout: '+e.message}; }
                }
            """, {"uid": USER_ID, "pg": pg})

            if result.get('err'):
                err_txt = result.get('txt','')
                is_html = err_txt.startswith('<!doctype') or err_txt.startswith('<html') or '<!DOCTYPE' in err_txt.upper()
                log(f"  [Pg{pg}] ERR: {err_txt[:80]}...")
                if '10022' in err_txt:
                    log("  Login expired!")
                    done = True
                    break
                # Rate limiting / WAF - wait longer
                if is_html:
                    log("  WAF/rate limit detected, waiting 60s...")
                    time.sleep(60)
                else:
                    time.sleep(5)
                # Retry once
                result = page.evaluate("""async(args) => {
                    const r = await fetch('/v4/statuses/user_timeline.json?user_id='+args.uid+'&page='+args.pg, {
                        headers:{'Accept':'application/json','X-Requested-With':'XMLHttpRequest'}, credentials:'include'});
                    if(!r.ok) return {err:true, st:r.status};
                    const d = await r.json();
                    const sts=d.statuses||d.list||[];
                    return {err:false,sts:sts.map(s=>({id:s.id,title:s.title||'',
                        text:s.text||s.description||'',created_at:s.created_at,type:s.type,
                        rt:s.retweet_count||0,rp:s.reply_count||0,vw:s.view_count||0,
                        fv:s.fav_count||0,truncated:s.truncated||false,target:s.target||''})),
                        total:d.total,page:d.page,maxPage:d.maxPage,count:d.count};
                }""", {"uid": USER_ID, "pg": pg})
                if result.get('err'):
                    log(f"  [Pg{pg}] Retry also failed, stopping chunk")
                    break

            sts = result.get('sts', [])
            c = result.get('count', len(sts))
            total = result.get('total', total)
            total_pages = result.get('maxPage')

            if not sts or c == 0:
                log(f"  [Pg{pg}] Empty, done!")
                done = True
                break

            new_added = 0
            for s in sts:
                if s['id'] not in seen:
                    seen.add(s['id'])
                    raw = s.get('text','')
                    clean = re.sub(r'<[^>]*>','',raw).replace('&amp;','&').replace('&lt;','<').replace('&gt;','>').replace('&quot;','"').replace('&#x27;',"'").replace('&nbsp;',' ')
                    s['text'] = clean.strip()
                    posts.append(s)
                    new_added += 1

            pct = f"{len(posts)/total*100:.1f}%" if total else "?"
            log(f"  [Pg{pg}/{total_pages}] +{new_added} (total {len(posts)} {pct})")

            if total and len(posts) >= total:
                log("  ALL DONE!")
                done = True
                break

            last_page = pg + 1
            time.sleep(0.6)

        browser.close()
        return posts, last_page, done, total


# Main loop
log("="*60)
log("Chunked Scraper - 直到一万点")
log("="*60)

# Load previous state
all_posts = []
seen_ids = set()
next_page = 1

if os.path.exists(STATE_FILE):
    with open(STATE_FILE, 'r', encoding='utf-8') as f:
        state = json.load(f)
    all_posts = state.get('posts', [])
    seen_ids = set(p['id'] for p in all_posts)
    next_page = state.get('next_page', 1)
    log(f"[*] Resuming: {len(all_posts)} posts saved, starting from page {next_page}")

chunk_num = 0
MAX_CHUNKS = 200
same_page_stuck = 0
last_start_page = 0

while chunk_num < MAX_CHUNKS:
    chunk_num += 1
    log(f"\n--- Chunk {chunk_num} (pages {next_page}-{next_page+CHUNK_SIZE-1}) ---")

    # Track if we're stuck on same page
    if next_page == last_start_page:
        same_page_stuck += 1
        if same_page_stuck >= 3:
            log(f"  Page {next_page} failed 3x, skipping to {next_page+1}")
            next_page += 1
            same_page_stuck = 0
    else:
        same_page_stuck = 0
    last_start_page = next_page

    all_posts, next_page, done, total = do_chunk(next_page, all_posts, seen_ids)

    # Update seen_ids
    seen_ids = set(p['id'] for p in all_posts)

    # Save state
    state = {'posts': all_posts, 'next_page': next_page, 'total': total}
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False)
    log(f"  State saved: {len(all_posts)} posts, next page {next_page}")

    # Also save incremental backup
    backup_file = os.path.join(OUTPUT_DIR, f"backup_{len(all_posts)}.json")
    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump(all_posts, f, ensure_ascii=False, indent=2)

    if done:
        log(f"\n[FINISHED] All pages scraped!")
        break

    if chunk_num >= MAX_CHUNKS:
        log(f"\n[STOPPED] Max chunks ({MAX_CHUNKS}) reached")
        break

    # Small pause between chunks
    time.sleep(1)

# Save final
with open(FINAL_FILE, 'w', encoding='utf-8') as f:
    json.dump(all_posts, f, ensure_ascii=False, indent=2)

log(f"\n{'='*60}")
log(f"DONE: {len(all_posts)} posts")
log(f"Saved: {FINAL_FILE}")
if all_posts:
    dates = [p.get('created_at',0) for p in all_posts if p.get('created_at')]
    if dates:
        dmin = datetime.fromtimestamp(min(dates)/1000).strftime('%Y-%m-%d')
        dmax = datetime.fromtimestamp(max(dates)/1000).strftime('%Y-%m-%d')
        log(f"Date range: {dmin} ~ {dmax}")
