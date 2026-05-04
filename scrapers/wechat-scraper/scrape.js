import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';

const FIRST_ARTICLE = 'https://mp.weixin.qq.com/s/m9UDZB1W_d1n3BjCFEGGew';
const OUTPUT_DIR = './output';
const ARTICLES_JSON = path.join(OUTPUT_DIR, 'articles.json');
const TXT_DIR = path.join(OUTPUT_DIR, 'txt');

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  fs.mkdirSync(TXT_DIR, { recursive: true });

  console.log('启动浏览器...');
  const browser = await chromium.launch({
    headless: true,
    channel: 'chrome',
    args: ['--no-sandbox', '--disable-blink-features=AutomationControlled'],
  });

  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    locale: 'zh-CN',
  });

  await context.addInitScript(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => false });
  });

  const page = await context.newPage();

  // ===== Step 1: 打开第一篇文章，提取 biz =====
  console.log('[1] 打开第一篇文章提取账号信息...');
  await page.goto(FIRST_ARTICLE, { timeout: 30000, waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(3000);

  const html = await page.content();
  const bizMatch = html.match(/var\s+biz\s*=\s*['"]([^'"]+)['"]/);
  const biz = bizMatch ? bizMatch[1] : null;

  const accountName = await page.evaluate(() =>
    document.querySelector('#js_name')?.textContent?.trim()
  );

  console.log(`    公众号: ${accountName}`);
  console.log(`    biz: ${biz}`);

  if (!biz) {
    console.error('❌ 无法提取 biz，退出');
    await browser.close();
    return;
  }

  // ===== Step 2: 通过 getmsg API 获取全部文章列表 =====
  console.log('[2] 通过 getmsg 接口获取文章列表...');

  const seen = new Set();
  const articles = [];
  seen.add(FIRST_ARTICLE);

  for (let offset = 0; offset < 200; offset += 10) {
    const apiUrl = `https://mp.weixin.qq.com/mp/profile_ext?action=getmsg&__biz=${biz}&f=json&offset=${offset}&count=10&is_ok=1&scene=124`;

    console.log(`    offset=${offset}...`);

    try {
      const resp = await page.evaluate(async (url) => {
        const r = await fetch(url);
        return await r.json();
      }, apiUrl);

      if (!resp || resp.ret !== 0) {
        // ret !== 0 means error or end of list
        console.log(`    响应 ret=${resp?.ret}，停止`);
        break;
      }

      const msgList = JSON.parse(resp.general_msg_list);
      if (!msgList.list || msgList.list.length === 0) {
        console.log('    文章列表为空，完成');
        break;
      }

      for (const item of msgList.list) {
        const ext = item.app_msg_ext_info;
        if (!ext) continue;

        const links = [{ title: ext.title, url: ext.content_url || ext.link }];
        if (ext.multi_app_msg_item_list) {
          for (const m of ext.multi_app_msg_item_list) {
            links.push({ title: m.title, url: m.content_url || m.link });
          }
        }

        for (const l of links) {
          if (l.url && !seen.has(l.url)) {
            seen.add(l.url);
            articles.push({
              url: l.url,
              title: l.title || null,
              date: item.comm_msg_info?.datetime
                ? new Date(item.comm_msg_info.datetime * 1000).toISOString().split('T')[0]
                : null,
              content: null,
            });
          }
        }
      }

      console.log(`    累计 ${articles.length} 篇文章`);

      if (msgList.list.length < 10) {
        console.log('    已到最后一页');
        break;
      }

      await sleep(800 + Math.random() * 1500);
    } catch (e) {
      console.log(`    请求失败: ${e.message}`);
      break;
    }
  }

  console.log(`\n    共获取 ${articles.length} 篇文章`);

  // ===== Step 3: 逐篇抓取内容 =====
  console.log('[3] 开始抓取文章内容...\n');

  let successCount = 0;
  let failCount = 0;

  for (let i = 0; i < articles.length; i++) {
    const a = articles[i];
    const label = a.title || a.url.substring(0, 50);

    process.stdout.write(`    [${i + 1}/${articles.length}] ${label.substring(0, 60)}... `);

    try {
      await page.goto(a.url, { timeout: 20000, waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(1500 + Math.random() * 1500);

      const bodyText = await page.evaluate(() => document.body.innerText || '');

      if (bodyText.includes('环境异常') || bodyText.includes('去验证')) {
        process.stdout.write('⚠ 被拦截，等待重试... ');
        await sleep(8000);
        await page.reload({ timeout: 20000, waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(3000);
        const retry = await page.evaluate(() => document.body.innerText || '');
        if (retry.includes('环境异常')) {
          console.log('❌ 跳过');
          failCount++;
          continue;
        }
      }

      a.title = await page.evaluate(() =>
        document.querySelector('#activity-name')?.textContent?.trim()
      ) || a.title;

      a.date = await page.evaluate(() =>
        document.querySelector('#publish_time')?.textContent?.trim()
      ) || a.date;

      a.content = await page.evaluate(() =>
        document.querySelector('#js_content')?.textContent?.trim() || null
      );

      if (a.content) {
        successCount++;
        console.log('✓');
      } else {
        failCount++;
        console.log('⚠ 空内容');
      }

      // 每篇存一个 txt
      const safeName = (a.title || 'untitled').replace(/[<>:"/\\|?*]/g, '_').substring(0, 80);
      const filename = `${String(i + 1).padStart(4, '0')}_${safeName}.txt`;
      const text = `标题: ${a.title || '未知'}\n日期: ${a.date || '未知'}\n链接: ${a.url}\n\n${a.content || '(无内容)'}`;
      fs.writeFileSync(path.join(TXT_DIR, filename), text, 'utf-8');
    } catch (e) {
      console.log(`❌ ${e.message}`);
      failCount++;
    }

    // 每30篇休息
    if ((i + 1) % 30 === 0 && i < articles.length - 1) {
      console.log('    --- 暂停 8 秒 ---');
      await sleep(8000);
    }
  }

  // ===== Step 4: 保存汇总 JSON =====
  console.log('\n[4] 保存汇总...');

  const summary = {
    account: accountName,
    scrapedAt: new Date().toISOString(),
    total: articles.length,
    success: successCount,
    fail: failCount,
    articles: articles.map(a => ({
      title: a.title,
      url: a.url,
      date: a.date,
      contentLen: a.content ? a.content.length : 0,
    })),
  };

  fs.writeFileSync(ARTICLES_JSON, JSON.stringify(summary, null, 2), 'utf-8');

  console.log(`    成功: ${successCount}  失败: ${failCount}  总计: ${articles.length}`);
  console.log(`    汇总: ${ARTICLES_JSON}`);
  console.log(`    文章: ${TXT_DIR}`);
  console.log('\n✅ 完成！');

  await browser.close();
}

main().catch(e => {
  console.error('Fatal:', e);
  process.exit(1);
});
