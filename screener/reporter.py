"""
Generate screener output reports: JSON, Markdown, and text.
"""
import json, os
from datetime import datetime
from pathlib import Path


def generate_json(date_str, index_trends, sector_ranking, top_stocks, output_dir):
    """Generate daily JSON and latest.json."""
    out = {
        'date': date_str,
        'market_state': {
            name: t['market_state'] for name, t in index_trends.items()
        },
        'index_data': {
            name: {
                'close': t['current'],
                'ret20': t['ret20'],
                'arrangement': t['arrangement'],
            }
            for name, t in index_trends.items()
        },
        'sector_ranking': [
            [s['name'], round(s['score'], 2), round(s.get('avg_ret5', 0), 2),
             round(s.get('avg_ret10', 0), 2), round(s.get('avg_ret20', 0), 2)]
            for s in sector_ranking
        ],
        'top_stocks': top_stocks[:30],  # Limit to 30 for JSON size
    }

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Daily file
    daily_path = output_dir / f'daily_{date_str}.json'
    with open(daily_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # Latest file (overwrite)
    latest_path = output_dir / 'latest.json'
    with open(latest_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    return out


def generate_markdown(date_str, index_trends, sector_ranking, top_stocks, output_dir):
    """Generate human-readable Markdown report."""
    lines = []
    lines.append(f"# 每日A股选股报告")
    lines.append(f"**日期**: {date_str}")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    # Market overview
    lines.append("## 一、指数环境")
    lines.append("")
    lines.append("| 指数 | 收盘价 | 5日 | 10日 | 20日 | 60日 | 均线 | 状态 |")
    lines.append("|------|--------|-----|------|------|------|------|------|")
    for name, t in index_trends.items():
        lines.append(
            f"| {name} | {t['current']:.2f} | {t['ret5']:+.1f}% | {t['ret10']:+.1f}% | "
            f"{t['ret20']:+.1f}% | {t['ret60']:+.1f}% | {t['arrangement']} | {t['market_state']} |"
        )
    lines.append("")

    strong = sum(1 for t in index_trends.values() if t['ret20'] > 0)
    total = len(index_trends)
    lines.append(f"**综合判断**: {strong}/{total} 指数20日线上方")
    lines.append("")

    # Sector ranking
    lines.append("## 二、板块排名")
    lines.append("")
    lines.append("| 排名 | 板块 | 得分 | 均涨5日 | 均涨10日 | 均涨20日 | 多头数 |")
    lines.append("|------|------|------|---------|----------|----------|--------|")
    for i, s in enumerate(sector_ranking):
        lines.append(
            f"| {i+1} | {s['name']} | {s['score']:.1f} | "
            f"{s.get('avg_ret5',0):+.1f}% | {s.get('avg_ret10',0):+.1f}% | "
            f"{s.get('avg_ret20',0):+.1f}% | {s.get('bull_count',0)} |"
        )
    lines.append("")

    # Top stocks
    lines.append("## 三、高分个股 (Top 20)")
    lines.append("")
    lines.append("| 排名 | 名称 | 代码 | 板块 | 得分 | 涨跌 | 5日 | 10日 | 20日 | 理由 |")
    lines.append("|------|------|------|------|------|------|-----|------|------|------|")
    for i, s in enumerate(top_stocks[:20]):
        reasons = ', '.join(s.get('reasons', [])[:2])
        lines.append(
            f"| {i+1} | {s['name']} | {s['code']} | {s.get('sector','')} | "
            f"**{s['score']}** | {s['daily_chg']:+.1f}% | {s['ret5']:+.1f}% | "
            f"{s['ret10']:+.1f}% | {s['ret20']:+.1f}% | {reasons} |"
        )
    lines.append("")

    # Top 3 sectors recommendation
    lines.append("## 四、重点关注")
    lines.append("")
    for i, s in enumerate(sector_ranking[:3]):
        top = [st for st in top_stocks if st.get('sector') == s['name']][:3]
        stock_names = '、'.join(st['name'] for st in top)
        lines.append(f"{i+1}. **{s['name']}** (得分: {s['score']:.1f}): {stock_names}")

    md_content = '\n'.join(lines)

    output_dir = Path(output_dir)
    md_path = output_dir / f'daily_{date_str}.md'
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)

    return md_content


def generate_text(date_str, index_trends, sector_ranking, top_stocks, output_dir):
    """Generate plain text log output."""
    lines = []
    lines.append("=" * 80)
    lines.append(f"每日A股选股 — 直到一万点方法论")
    lines.append(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 80)
    lines.append("")

    lines.append("第一步：指数环境判断")
    lines.append("-" * 40)
    for name, t in index_trends.items():
        lines.append(
            f"  {name:8s} 收盘{t['current']:.2f}  "
            f"{t['ret5']:+.1f}%/{t['ret10']:+.1f}%/{t['ret20']:+.1f}%/{t['ret60']:+.1f}%  "
            f"均线:{t['arrangement']}  状态:{t['market_state']}"
        )
    lines.append("")

    lines.append("第二步：板块排名")
    lines.append("-" * 40)
    for i, s in enumerate(sector_ranking):
        lines.append(
            f"  {i+1:2d}. {s['name']:12s}  得分:{s['score']:6.1f}  "
            f"均涨:{s.get('avg_ret5',0):+.1f}%/{s.get('avg_ret10',0):+.1f}%/{s.get('avg_ret20',0):+.1f}%"
        )
    lines.append("")

    lines.append("第三步：高分个股 (Top 40)")
    lines.append("-" * 40)
    for i, s in enumerate(top_stocks[:40]):
        reasons = ','.join(s.get('reasons', [])[:2])
        lines.append(
            f"  {i+1:2d}. {s['name']:8s} {s['code']:10s} {s.get('sector',''):12s}  "
            f"得分:{s['score']:3d}  涨跌:{s['daily_chg']:+.1f}%  "
            f"{s['ret5']:+.1f}%/{s['ret10']:+.1f}%/{s['ret20']:+.1f}%  {reasons}"
        )

    text_output = '\n'.join(lines)

    output_dir = Path(output_dir)
    txt_path = output_dir / f'result_{date_str}.txt'
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(text_output)

    return text_output
