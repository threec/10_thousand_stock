"""Open browser for manual login, auto-detect login, save cookies + localStorage."""
import json, os, time
from playwright.sync_api import sync_playwright

OUTPUT_DIR = r"D:\stock\data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False,
        args=['--disable-blink-features=AutomationControlled', '--no-sandbox'])
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        viewport={'width': 1200, 'height': 800}, locale='zh-CN')
    page = context.new_page()
    page.goto("https://xueqiu.com/", wait_until="domcontentloaded", timeout=30000)

    print("请在弹出的浏览器中完成登录...")
    print("等待登录完成（每 2 秒检测一次）...")

    # Auto-detect login by checking if user is logged in
    logged_in = False
    for i in range(300):  # Max 10 minutes
        try:
            # Check by trying to access user homepage
            result = page.evaluate("""
                () => {
                    const userNav = document.querySelector('.nav__user, .nav__avatar, [class*="avatar"], .login__avatar');
                    if (userNav) return true;
                    // Also check if we can see login-related elements missing
                    const loginBtn = document.querySelector('a[href*="login"], .login__btn');
                    return !loginBtn;
                }
            """)
            if result:
                logged_in = True
                break
        except:
            pass
        time.sleep(2)
        if i % 15 == 0 and i > 0:
            print(f"  已等待 {i*2} 秒，请继续登录...")

    if not logged_in:
        print("超时未检测到登录，将尝试保存当前状态...")
    else:
        print("检测到登录状态!")

    page.wait_for_timeout(2000)

    # Save cookies
    cookies = context.cookies()
    cookie_file = os.path.join(OUTPUT_DIR, "cookies.json")
    with open(cookie_file, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)
    print(f"Cookies 已保存: {len(cookies)} 条")

    # Save localStorage
    try:
        local_storage = page.evaluate("() => JSON.parse(JSON.stringify(localStorage))")
        ls_file = os.path.join(OUTPUT_DIR, "localStorage.json")
        with open(ls_file, "w", encoding="utf-8") as f:
            json.dump(local_storage, f, ensure_ascii=False, indent=2)
        print(f"localStorage 已保存: {len(local_storage)} 个 key")
    except Exception as e:
        print(f"localStorage: {e}")

    browser.close()
    print("完成！可以继续运行 chunk_scrape.py")
