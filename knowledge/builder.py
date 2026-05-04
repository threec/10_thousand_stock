"""
Build kb_index.json from knowledge_base/*.md files.
Generates a searchable index and article catalog for the web dashboard.
"""
import json, os, re
from datetime import datetime
from pathlib import Path

KB_DIR = Path(r"D:\stock\knowledge_base")
WEB_DIR = Path(r"D:\stock\data\web")
WECHAT_DIR = Path(r"D:\stock\data\wechat_articles")


def parse_md_sections(filepath):
    """Parse a knowledge base .md file into structured sections."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    sections = []
    current_h2 = None
    current_principles = []

    for line in content.split('\n'):
        line = line.strip()
        if line.startswith('# ') and not line.startswith('## '):
            # Main title
            title = line.replace('# ', '').strip()
        elif line.startswith('## '):
            if current_h2 and current_principles:
                sections.append({
                    'title': current_h2,
                    'principles': current_principles,
                })
            current_h2 = line.replace('## ', '').strip()
            current_principles = []
        elif line.startswith('### '):
            current_principles.append({
                'title': line.replace('### ', '').strip(),
                'items': [],
            })
        elif line.startswith('- ') and current_principles:
            item = line.replace('- ', '').strip()
            if item:
                current_principles[-1]['items'].append(item)
        elif line.startswith('**来源**') and current_principles:
            source = line.replace('**来源**', '').replace(':', '').strip()
            current_principles[-1]['source'] = source

    if current_h2 and current_principles:
        sections.append({'title': current_h2, 'principles': current_principles})

    return {
        'file': filepath.name,
        'title': title if 'title' in dir() else filepath.stem,
        'sections': sections,
        'raw_content': content,
    }


def parse_article_headers():
    """Parse all WeChat article .txt files for metadata."""
    articles = []
    if not WECHAT_DIR.exists():
        return articles

    for f in sorted(WECHAT_DIR.glob('*.txt')):
        if f.name == '_index.txt':
            continue
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                lines = fh.readlines()
            meta = {}
            for line in lines[:10]:
                line = line.strip()
                if line.startswith('标题:'):
                    meta['title'] = line.replace('标题:', '').strip()
                elif line.startswith('日期:'):
                    meta['date'] = line.replace('日期:', '').strip()
                elif line.startswith('链接:'):
                    meta['url'] = line.replace('链接:', '').strip()
            if meta:
                meta['file'] = f.name
                articles.append(meta)
        except Exception:
            pass
    return articles


def build_search_index(kb_data):
    """Build a simple keyword search index from all KB content."""
    index = {}
    for doc in kb_data:
        text = doc.get('raw_content', '')
        words = set(re.findall(r'[一-鿿\w]+', text.lower()))
        for w in words:
            if len(w) < 2:
                continue
            if w not in index:
                index[w] = []
            index[w].append(doc['file'])
    return index


def build():
    """Main builder: read KB files, build index, write JSON."""
    if not KB_DIR.exists():
        print(f"KB directory not found: {KB_DIR}")
        return

    kb_files = sorted(KB_DIR.glob('*.md'))
    if not kb_files:
        print("No .md files found in knowledge_base/")
        return

    print(f"Found {len(kb_files)} knowledge base files")

    # Parse all KB files
    kb_data = []
    for f in kb_files:
        data = parse_md_sections(f)
        kb_data.append(data)
        sections_count = len(data['sections'])
        print(f"  {f.name}: {sections_count} sections")

    # Parse article headers
    articles = parse_article_headers()
    print(f"  Articles: {len(articles)}")

    # Build search index
    search_index = build_search_index(kb_data)
    print(f"  Search terms: {len(search_index)}")

    # Build output
    kb_index = {
        'generated': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'kb_files': [
            {
                'file': d['file'],
                'title': d['title'],
                'section_count': len(d['sections']),
            }
            for d in kb_data
        ],
        'sections': [
            {
                'file': d['file'],
                'title': d['title'],
                'content': d['sections'],
            }
            for d in kb_data
        ],
        'search_index': search_index,
        'articles': articles,
    }

    WEB_DIR.mkdir(parents=True, exist_ok=True)
    output_path = WEB_DIR / 'kb_index.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(kb_index, f, ensure_ascii=False, indent=2)

    print(f"\nBuilt kb_index.json -> {output_path}")
    print(f"  KB sections: {sum(len(d['sections']) for d in kb_data)}")
    print(f"  Articles: {len(articles)}")


if __name__ == '__main__':
    build()
