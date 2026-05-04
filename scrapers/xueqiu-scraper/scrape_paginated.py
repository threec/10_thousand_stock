"""
Try max_id cursor-based pagination and also get full article text for long posts.
"""
import sys, os, json, re, time
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

USER_ID = "7845696728"
OUTPUT_DIR = r"D:\stock\data"

def log(msg):
    try: print(msg)
    except: print(msg.encode('ascii', errors='replace').decode('ascii'))

def fetch_posts():
    all_posts = []
    seen_ids = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled', '--no-sandbox'])
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='zh-CN',
        )
        page = context.new_page()

        log("[*] Loading main page...")
        page.goto(f"https://xueqiu.com/u/{USER_ID}", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
        log(f"  Title: {page.title()}")

        # Try approach 1: max_id pagination
        log("\n[Approach 1] max_id cursor pagination...")
        max_id = 0
        for i in range(200):
            result = page.evaluate("""
                async (params) => {
                    let url = `https://xueqiu.com/v4/statuses/user_timeline.json?user_id=${params.userId}&count=20`;
                    if (params.maxId > 0) {
                        url += `&max_id=${params.maxId}`;
                    }
                    const resp = await fetch(url, {
                        headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                        credentials: 'include',
                    });
                    if (!resp.ok) {
                        return { error: true, status: resp.status, text: await resp.text() };
                    }
                    const data = await resp.json();
                    const statuses = data.statuses || data.list || [];
                    return {
                        error: false,
                        count: statuses.length,
                        next_max_id: data.next_max_id || data.next_id || 0,
                        statuses: statuses.map(s => ({
                            id: s.id,
                            title: s.title || '',
                            text: (s.text || s.description || '').replace(/<[^>]*>/g, ''),
                            created_at: s.created_at,
                            type: s.type,
                            retweet_count: s.retweet_count || 0,
                            reply_count: s.reply_count || 0,
                            view_count: s.view_count || 0,
                            truncated: s.truncated || false,
                            target: s.target || '',
                        })),
                        raw_keys: Object.keys(data),
                    };
                }
            """, {"userId": USER_ID, "maxId": max_id})

            if result.get('error'):
                log(f"  max_id={max_id}: ERROR {result.get('status')} - {result.get('text', '')[:200]}")
                break

            statuses = result.get('statuses', [])
            count = result.get('count', 0)
            next_max_id = result.get('next_max_id', 0)
            raw_keys = result.get('raw_keys', [])

            if count == 0:
                log(f"  max_id={max_id}: empty, done")
                break

            new_count = 0
            for s in statuses:
                if s['id'] not in seen_ids:
                    seen_ids.add(s['id'])
                    text = s['text']
                    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&#x27;', "'").replace('&nbsp;', ' ')
                    s['text'] = text
                    all_posts.append(s)
                    new_count += 1

            log(f"  max_id={max_id}: {count} returned, {new_count} new (total: {len(all_posts)}), next_max_id={next_max_id}, keys={raw_keys}")

            if next_max_id and next_max_id > 0:
                max_id = next_max_id
            elif statuses:
                # Use last post id minus 1 as max_id
                last_id = min(s['id'] for s in statuses)
                max_id = last_id - 1
            else:
                break

            time.sleep(0.5)

        browser.close()

    return all_posts


def fetch_long_texts(posts):
    """Fetch full text for truncated long posts."""
    log(f"\n[Step 3] Fetching full text for truncated posts...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled', '--no-sandbox'])
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='zh-CN',
        )
        page = context.new_page()
        page.goto(f"https://xueqiu.com/u/{USER_ID}", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        long_posts = [p for p in posts if p.get('truncated') or p.get('type') == '3' or '...' in p.get('text', '')[-50:]]
        log(f"  Found {len(long_posts)} truncated/long posts to expand")

        for i, post in enumerate(long_posts[:100]):  # Limit to 100
            target = post.get('target', '')
            if not target:
                continue

            result = page.evaluate("""
                async (target) => {
                    const url = 'https://xueqiu.com' + target;
                    const resp = await fetch(url, {
                        headers: { 'Accept': 'text/html', 'X-Requested-With': 'XMLHttpRequest' },
                        credentials: 'include',
                    });
                    const html = await resp.text();

                    // Try to find full article content
                    const match = html.match(/SNOWMAN_STATUS_TEXT\\s*=\\s*"([^"]*)"/);
                    if (match) {
                        return match[1].replace(/<[^>]*>/g, '').replace(/\\n/g, '\n');
                    }

                    // Alternative: look for article body
                    const articleMatch = html.match(/<div[^>]*class="[^"]*article[^"]*"[^>]*>([\\s\\S]*?)<\\/div>/i);
                    if (articleMatch) {
                        return articleMatch[1].replace(/<[^>]*>/g, '').trim();
                    }

                    return null;
                }
            """, target)

            if result:
                post['full_text'] = result
                if i % 10 == 0:
                    log(f"    [{i+1}/{len(long_posts[:100])}] expanded: {result[:100]}...")

            time.sleep(0.3)

        browser.close()

    return posts


if __name__ == "__main__":
    log("=" * 60)
    log("Xueqiu max_id Pagination Scraper")
    log("=" * 60)

    posts = fetch_posts()

    log(f"\n[+] Total unique posts: {len(posts)}")

    # Save
    output_path = os.path.join(OUTPUT_DIR, "all_timeline_posts.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)
    log(f"[+] Saved to {output_path}")

    # Date range
    if posts:
        dates = sorted([p.get('created_at', 0) for p in posts if p.get('created_at')])
        if dates:
            from datetime import datetime
            log(f"[*] Date range: {datetime.fromtimestamp(dates[0]/1000)} to {datetime.fromtimestamp(dates[-1]/1000)}")
