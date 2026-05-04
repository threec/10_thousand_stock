import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUTPUT_DIR = path.join(__dirname, 'output');
const TXT_DIR = path.join(OUTPUT_DIR, 'txt');

// ====== 文章链接列表：你每给一篇，我加到下面 ======
const START_INDEX = 84;
const ARTICLE_URLS = [
  'https://mp.weixin.qq.com/s/Xx8BWKL9czS83ydlqlNd8g',
  'https://mp.weixin.qq.com/s/BXpmyJkglPWC3gFFUTVT0A',
  'https://mp.weixin.qq.com/s/sNaM8P3q2g9DDotNNpl6Og',
  'https://mp.weixin.qq.com/s/svEaFQloTBKUnzn0BmqB7A',
  'https://mp.weixin.qq.com/s/Sc5rR8Hq68hUqdeZTtsLjA',
  'https://mp.weixin.qq.com/s/ERKtONWmzdm6Wief7yfieg',
  'https://mp.weixin.qq.com/s/2kUjtildVQqlzwtU4VYk8w',
  'https://mp.weixin.qq.com/s/mFL_sIFSTGwnR_ijwnMq2w',
];

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function fetchArticle(page, url, index) {
  console.log(`\n[${index}] ${url.substring(0, 70)}...`);

  await page.goto(url, { timeout: 25000, waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);

  const bodyText = await page.evaluate(() => document.body.innerText || '');
  if (bodyText.includes('环境异常')) {
    console.log('  ⚠ 被拦截，等待重试...');
    await sleep(8000);
    await page.reload({ timeout: 25000, waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(3000);
    const retry = await page.evaluate(() => document.body.innerText || '');
    if (retry.includes('环境异常')) {
      console.log('  ❌ 重试失败，跳过');
      return null;
    }
  }

  const title = await page.evaluate(() =>
    document.querySelector('#activity-name')?.textContent?.trim() || ''
  );
  const date = await page.evaluate(() =>
    document.querySelector('#publish_time')?.textContent?.trim() || ''
  );
  const account = await page.evaluate(() =>
    document.querySelector('#js_name')?.textContent?.trim() || ''
  );
  const content = await page.evaluate(() =>
    document.querySelector('#js_content')?.textContent?.trim() || ''
  );

  if (!title && !content) {
    console.log('  ❌ 内容为空');
    return null;
  }

  console.log(`  公众号: ${account}`);
  console.log(`  标题:   ${title}`);
  console.log(`  日期:   ${date}`);
  console.log(`  字数:   ${content.length}`);

  return { title, date, account, content, url };
}

async function main() {
  fs.mkdirSync(TXT_DIR, { recursive: true });

  console.log('启动浏览器...');
  const browser = await chromium.launch({
    headless: true,
    channel: 'chrome',
    args: ['--no-sandbox'],
  });
  const page = await browser.newPage();

  let success = 0;
  let fail = 0;

  for (let i = 0; i < ARTICLE_URLS.length; i++) {
    try {
      const idx = START_INDEX + i;
      const article = await fetchArticle(page, ARTICLE_URLS[i], idx);
      if (article) {
        success++;
        const safeName = (article.title || 'untitled')
          .replace(/[<>:"/\\|?*]/g, '_').substring(0, 60);
        const filename = `${String(idx).padStart(3, '0')}_${safeName}.txt`;
        const text = [
          `标题: ${article.title}`,
          `日期: ${article.date}`,
          `公众号: ${article.account}`,
          `链接: ${article.url}`,
          '',
          article.content,
        ].join('\n');
        fs.writeFileSync(path.join(TXT_DIR, filename), text, 'utf-8');
        console.log(`  ✓ ${filename}`);
      } else {
        fail++;
      }
    } catch (e) {
      console.log(`  ❌ 错误: ${e.message}`);
      fail++;
    }
  }

  console.log(`\n✅ 完成！成功 ${success}，失败 ${fail}`);
  console.log(`   输出目录: ${TXT_DIR}`);
  await browser.close();
}

main().catch(e => { console.error(e); process.exit(1); });
