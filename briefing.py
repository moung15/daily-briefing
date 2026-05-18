"""
=============================================================
  오늘의 브리핑 - 완전 무료 버전 (월 ₩0)
=============================================================
  
  데이터 소스: 네이버 검색 API (무료 25,000회/일)
  실행 환경: GitHub Actions (무료 2,000분/월)
  호스팅: GitHub Pages (무료)
  알림: Telegram Bot (무료) / Gmail SMTP (무료)
  
  카테고리 12개:
  1. 주요뉴스    2. 정치        3. AI·테크    4. 부동산
  5. 주식·금융   6. 경제        7. 국제·외교  8. 사회·사건
  9. 법률·판결  10. 생활·날씨  11. 문화·엔터 12. 헬스·과학
  
  필수 환경변수:
    NAVER_CLIENT_ID      - 네이버 개발자센터 Client ID
    NAVER_CLIENT_SECRET  - 네이버 개발자센터 Client Secret
  
  선택 환경변수:
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    SENDER_EMAIL, SENDER_PASSWORD, RECIPIENT_EMAIL
    PAGES_URL

=============================================================
"""

import os
import sys
import json
import re
import time
import smtplib
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from html import unescape
from pathlib import Path

# ============ Configuration ============
NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD", "")
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL", "")
PAGES_URL = os.environ.get("PAGES_URL", "")

KST = timezone(timedelta(hours=9))

# 카테고리 정의 + 네이버 검색 쿼리
CATEGORIES = [
    {"key": "top",          "name": "주요뉴스",  "han": "主要", "en": "Top Stories",   "icon": "★", "query": "오늘 주요뉴스"},
    {"key": "politics",     "name": "정치",      "han": "政治", "en": "Politics",      "icon": "⬢", "query": "정치 국회"},
    {"key": "ai",           "name": "AI·테크",   "han": "技術", "en": "AI & Tech",     "icon": "◎", "query": "AI 인공지능"},
    {"key": "real_estate",  "name": "부동산",    "han": "不動産","en": "Real Estate",  "icon": "⌂", "query": "부동산 아파트"},
    {"key": "stocks",       "name": "주식·금융", "han": "金融", "en": "Markets",       "icon": "⟁", "query": "코스피 증시"},
    {"key": "economy",      "name": "경제",      "han": "經濟", "en": "Economy",       "icon": "$", "query": "한국 경제"},
    {"key": "international","name": "국제·외교", "han": "外交", "en": "International", "icon": "◐", "query": "외교 국제뉴스"},
    {"key": "society",      "name": "사회·사건", "han": "社會", "en": "Society",       "icon": "▤", "query": "사회 사건사고"},
    {"key": "law",          "name": "법률·판결", "han": "法律", "en": "Law",           "icon": "⚖", "query": "법원 판결"},
    {"key": "life",         "name": "생활·날씨", "han": "生活", "en": "Life",          "icon": "✿", "query": "날씨 생활정보"},
    {"key": "culture",      "name": "문화·엔터", "han": "文化", "en": "Culture",       "icon": "♬", "query": "연예 문화"},
    {"key": "health",       "name": "헬스·과학", "han": "健康", "en": "Health",        "icon": "✚", "query": "건강 의료 과학"},
]


# ============ Helpers ============
def clean_html(text):
    """HTML 태그 및 엔티티 제거"""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = text.replace("\u200b", "").strip()
    return text


def relative_time(pub_date_str):
    """RFC 822 날짜를 '2시간 전' 형식으로 변환"""
    if not pub_date_str:
        return ""
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(pub_date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        now = datetime.now(KST)
        diff = now - dt
        seconds = int(diff.total_seconds())
        
        if seconds < 60:
            return "방금 전"
        elif seconds < 3600:
            return f"{seconds // 60}분 전"
        elif seconds < 86400:
            return f"{seconds // 3600}시간 전"
        elif seconds < 604800:
            return f"{seconds // 86400}일 전"
        else:
            return dt.strftime("%m월 %d일")
    except Exception:
        return ""


def extract_source(link):
    """URL에서 매체명 추출"""
    if not link:
        return ""
    
    domain_to_name = {
        "yna.co.kr": "연합뉴스", "ytn.co.kr": "YTN", "kbs.co.kr": "KBS",
        "mbc.co.kr": "MBC", "imnews.imbc.com": "MBC뉴스", "sbs.co.kr": "SBS",
        "jtbc.co.kr": "JTBC", "tvchosun.com": "TV조선", "channela.com": "채널A",
        "chosun.com": "조선일보", "biz.chosun.com": "조선비즈",
        "joongang.co.kr": "중앙일보", "donga.com": "동아일보",
        "hani.co.kr": "한겨레", "khan.co.kr": "경향신문", "kmib.co.kr": "국민일보",
        "hankyung.com": "한국경제", "mk.co.kr": "매일경제", "edaily.co.kr": "이데일리",
        "fnnews.com": "파이낸셜뉴스", "mt.co.kr": "머니투데이", "sedaily.com": "서울경제",
        "asiae.co.kr": "아시아경제", "newsis.com": "뉴시스", "news1.kr": "뉴스1",
        "zdnet.co.kr": "ZDNet Korea", "etnews.com": "전자신문", "aitimes.com": "AI타임스",
        "lawtimes.co.kr": "법률신문", "hankookilbo.com": "한국일보",
        "seoul.co.kr": "서울신문", "hankookilbo": "한국일보", "munhwa.com": "문화일보",
        "naver.com": "네이버뉴스", "daum.net": "다음뉴스",
    }
    
    try:
        host = urllib.parse.urlparse(link).netloc.lower()
        host = re.sub(r"^(www\.|m\.|news\.)", "", host)
        for domain, name in domain_to_name.items():
            if domain in host:
                return name
        parts = host.split(".")
        if len(parts) >= 2:
            return parts[0].upper()
        return host
    except Exception:
        return ""


# ============ Naver News API ============
def fetch_category(query, display=4):
    """네이버 검색 API로 카테고리별 뉴스 조회"""
    encoded_query = urllib.parse.quote(query)
    url = (f"https://openapi.naver.com/v1/search/news.json"
           f"?query={encoded_query}&display={display}&sort=date")
    
    req = urllib.request.Request(url, headers={
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
        "User-Agent": "Daily-Briefing/1.0",
    })
    
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    
    items = []
    for item in data.get("items", [])[:display]:
        title = clean_html(item.get("title", ""))
        description = clean_html(item.get("description", ""))
        link = item.get("link", "") or item.get("originallink", "")
        source = extract_source(link)
        rel_time = relative_time(item.get("pubDate", ""))
        
        if len(description) > 120:
            description = description[:120].rsplit(" ", 1)[0] + "..."
        
        items.append({
            "title": title,
            "description": description,
            "link": link,
            "source": source,
            "time": rel_time,
        })
    
    return items


def fetch_all_briefing():
    """모든 카테고리 뉴스 수집"""
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        raise RuntimeError("NAVER_CLIENT_ID/NAVER_CLIENT_SECRET 환경변수 필요")
    
    result = {}
    print(f"[{datetime.now(KST):%H:%M:%S}] 12개 카테고리 수집 시작...")
    
    for cat in CATEGORIES:
        try:
            items = fetch_category(cat["query"], display=4)
            result[cat["key"]] = items
            print(f"  ✓ {cat['name']:10s} {len(items)}개")
            time.sleep(0.3)
        except Exception as e:
            print(f"  ✗ {cat['name']:10s} 실패: {str(e)[:80]}")
            result[cat["key"]] = []
    
    return result


# ============ HTML Generation ============
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>오늘의 브리핑 · {date_short}</title>
<meta property="og:title" content="오늘의 브리핑 · {date_short}">
<meta property="og:description" content="{hero_title}">
<meta name="theme-color" content="#1a1612">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;700;800&family=Noto+Serif+KR:wght@400;500;700;900&family=Pretendard:wght@300;400;500;600;700;800&family=IBM+Plex+Mono:wght@300;400;500&family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400;1,700&display=swap" rel="stylesheet">
<style>
:root {{
  --paper:#f4ede0; --paper-deep:#ebe2d0; --ink:#1a1612; --ink-soft:#4a3f33;
  --ink-light:#7a6a55; --seal-red:#a8231f; --seal-deep:#7a1612; --gold:#9c7c34;
  --celadon:#4d6b5a; --line:rgba(26,22,18,0.18); --line-soft:rgba(26,22,18,0.08);
}}
*{{box-sizing:border-box;margin:0;padding:0;}}
html,body{{
  background:var(--paper);color:var(--ink);
  font-family:'Noto Serif KR','Nanum Myeongjo',Georgia,serif;
  line-height:1.7;min-height:100vh;
  background-image:
    radial-gradient(at 20% 10%,rgba(168,35,31,0.04) 0px,transparent 50%),
    radial-gradient(at 80% 90%,rgba(156,124,52,0.05) 0px,transparent 50%),
    repeating-linear-gradient(0deg,transparent 0,transparent 2px,rgba(26,22,18,0.012) 2px,rgba(26,22,18,0.012) 4px);
}}
.container{{max-width:1280px;margin:0 auto;padding:36px 28px 60px;}}
.masthead{{border-top:4px double var(--ink);border-bottom:1px solid var(--ink);padding:18px 0 14px;margin-bottom:8px;}}
.masthead-top{{display:flex;justify-content:space-between;font-family:'Pretendard',sans-serif;font-size:11px;letter-spacing:0.12em;text-transform:uppercase;color:var(--ink-soft);margin-bottom:18px;flex-wrap:wrap;gap:12px;}}
.title-block{{text-align:center;position:relative;}}
.title-block::before,.title-block::after{{content:'◆';position:absolute;top:50%;transform:translateY(-50%);font-size:12px;color:var(--seal-red);}}
.title-block::before{{left:8%;}} .title-block::after{{right:8%;}}
.eyebrow{{font-family:'Playfair Display',serif;font-style:italic;font-size:13px;letter-spacing:0.3em;color:var(--ink-light);text-transform:uppercase;margin-bottom:4px;}}
.masthead h1{{font-family:'Noto Serif KR',serif;font-weight:900;font-size:clamp(38px,6vw,64px);letter-spacing:-0.02em;line-height:1;margin:4px 0;}}
.masthead h1 .accent{{color:var(--seal-red);}}
.masthead-subtitle{{font-family:'Playfair Display',serif;font-style:italic;font-size:15px;color:var(--ink-soft);margin-top:6px;}}
.masthead-bottom{{display:flex;justify-content:space-between;margin-top:18px;padding-top:14px;border-top:1px solid var(--line);font-family:'Pretendard',sans-serif;font-size:12px;color:var(--ink-soft);flex-wrap:wrap;gap:12px;}}
.clock{{font-family:'IBM Plex Mono',monospace;font-size:14px;color:var(--ink);font-weight:500;}}
.clock-dot{{display:inline-block;width:6px;height:6px;background:var(--seal-red);border-radius:50%;margin-right:8px;animation:pulse 1.4s ease-in-out infinite;}}
@keyframes pulse{{0%,100%{{opacity:1;}}50%{{opacity:0.3;}}}}
.hero{{background:var(--ink);color:var(--paper);padding:36px 40px;margin:24px 0 32px;position:relative;overflow:hidden;}}
.hero::before{{content:'';position:absolute;top:-50%;right:-10%;width:60%;height:200%;background:radial-gradient(circle,rgba(168,35,31,0.2) 0%,transparent 60%);}}
.hero-content{{position:relative;z-index:1;}}
.hero-eyebrow{{font-family:'Playfair Display',serif;font-style:italic;font-size:12px;color:#ffb8b5;letter-spacing:0.3em;text-transform:uppercase;margin-bottom:12px;}}
.hero h2{{font-family:'Noto Serif KR',serif;font-weight:900;font-size:clamp(24px,3vw,32px);line-height:1.3;letter-spacing:-0.02em;margin-bottom:14px;}}
.hero a.hero-link{{color:inherit;text-decoration:none;}}
.hero a.hero-link:hover h2{{color:#ffb8b5;}}
.hero p{{font-family:'Pretendard',sans-serif;font-size:14px;line-height:1.7;opacity:0.85;max-width:800px;}}
.hero .hero-meta{{font-family:'Pretendard',sans-serif;font-size:11px;color:#ffb8b5;letter-spacing:0.1em;margin-top:14px;text-transform:uppercase;opacity:0.7;}}
.news-grid{{display:grid;grid-template-columns:repeat(12,1fr);gap:0;}}
.category{{padding:28px 26px;border:1px solid var(--line);margin:-0.5px;background:var(--paper);display:flex;flex-direction:column;}}
.category:nth-child(1){{grid-column:span 7;background:rgba(168,35,31,0.04);}}
.category:nth-child(2){{grid-column:span 5;}}
.category:nth-child(3){{grid-column:span 4;}}
.category:nth-child(4){{grid-column:span 4;}}
.category:nth-child(5){{grid-column:span 4;}}
.category:nth-child(6){{grid-column:span 6;}}
.category:nth-child(7){{grid-column:span 6;}}
.category:nth-child(8){{grid-column:span 5;}}
.category:nth-child(9){{grid-column:span 4;}}
.category:nth-child(10){{grid-column:span 3;}}
.category:nth-child(11){{grid-column:span 4;}}
.category:nth-child(12){{grid-column:span 8;}}
.cat-header{{display:flex;justify-content:space-between;align-items:flex-start;padding-bottom:14px;margin-bottom:18px;border-bottom:2px solid var(--ink);}}
.cat-title{{display:flex;align-items:baseline;gap:10px;}}
.cat-num{{font-family:'Playfair Display',serif;font-style:italic;font-size:13px;color:var(--ink-light);}}
.cat-name{{font-family:'Noto Serif KR',serif;font-weight:800;font-size:22px;letter-spacing:-0.01em;}}
.cat-name .han{{font-size:14px;color:var(--seal-red);font-weight:700;margin-left:4px;vertical-align:super;}}
.cat-en{{font-family:'Playfair Display',serif;font-style:italic;font-size:12px;color:var(--ink-light);margin-top:4px;}}
.cat-icon{{font-size:22px;color:var(--ink-light);}}
.news-item{{padding:14px 0;border-bottom:1px dotted var(--line-soft);transition:padding-left 0.2s ease;}}
.news-item:last-child{{border-bottom:none;}}
.news-item a{{color:inherit;text-decoration:none;display:block;}}
.news-item:hover{{padding-left:6px;}}
.news-item a:hover .news-headline{{color:var(--seal-red);}}
.news-headline{{font-family:'Noto Serif KR',serif;font-weight:700;color:var(--ink);font-size:15.5px;line-height:1.45;margin-bottom:6px;letter-spacing:-0.01em;transition:color 0.2s ease;}}
.news-summary{{font-family:'Noto Serif KR',serif;font-size:13px;color:var(--ink-soft);line-height:1.65;margin-bottom:6px;}}
.news-meta{{font-family:'Pretendard',sans-serif;font-size:11px;color:var(--ink-light);letter-spacing:0.05em;display:flex;gap:8px;align-items:center;}}
.news-meta .source{{font-weight:600;}}
.empty{{font-family:'Pretendard',sans-serif;font-size:12px;color:var(--ink-light);text-align:center;padding:20px 0;}}
.footer-info{{margin-top:50px;padding:28px;border:2px solid var(--ink);background:linear-gradient(to bottom,rgba(168,35,31,0.02),transparent);position:relative;text-align:center;}}
.footer-info::before{{content:'自動發行';position:absolute;top:-14px;left:24px;background:var(--paper);padding:0 12px;font-family:'Noto Serif KR',serif;font-weight:700;font-size:14px;color:var(--seal-red);letter-spacing:0.1em;}}
.footer-info p{{font-family:'Pretendard',sans-serif;font-size:13px;color:var(--ink-soft);line-height:1.7;}}
.footer-info code{{font-family:'IBM Plex Mono',monospace;background:var(--paper-deep);padding:2px 7px;font-size:12.5px;color:var(--seal-deep);border-radius:2px;}}
@media (max-width:900px){{
  .container{{padding:20px 16px 50px;}}
  .news-grid{{display:block;}}
  .category,.category:nth-child(n){{grid-column:span 12;margin:0;}}
  .masthead h1{{font-size:42px;}}
  .hero{{padding:28px 24px;}}
}}
.reveal{{animation:reveal 0.6s cubic-bezier(0.16,1,0.3,1) backwards;}}
@keyframes reveal{{from{{opacity:0;transform:translateY(8px);}}to{{opacity:1;transform:translateY(0);}}}}
</style>
</head>
<body>
<div class="container">
  <header class="masthead">
    <div class="masthead-top">
      <span>{date_full}</span>
      <span>Vol. I · Edition {edition}</span>
      <span>Seoul · Korea · Auto</span>
    </div>
    <div class="title-block">
      <div class="eyebrow">Your Personal Morning Press</div>
      <h1>오늘의 <span class="accent">브리핑</span></h1>
      <div class="masthead-subtitle">Twelve Categories — Free & Auto-Generated</div>
    </div>
    <div class="masthead-bottom">
      <div class="clock" id="liveClock"><span class="clock-dot"></span>00:00:00 KST</div>
      <div style="font-family:'Playfair Display',serif;font-style:italic;">"Free. Daily. Delivered while you sleep."</div>
      <div>발행 · {generated_at}</div>
    </div>
  </header>
  
  {hero_html}
  
  <section class="news-grid">
    {categories_html}
  </section>
  
  <section class="footer-info">
    <p>
      이 페이지는 <strong>매일 오전 8시 KST 자동 생성</strong>됩니다.<br>
      Naver Search API · GitHub Actions · 100% 무료 운영<br>
      <code>auto-deployed · {generated_at}</code>
    </p>
  </section>
</div>
<script>
function updateClock(){{
  const now=new Date();
  const hh=String(now.getHours()).padStart(2,'0');
  const mm=String(now.getMinutes()).padStart(2,'0');
  const ss=String(now.getSeconds()).padStart(2,'0');
  document.getElementById('liveClock').innerHTML='<span class="clock-dot"></span>'+hh+':'+mm+':'+ss+' KST';
}}
setInterval(updateClock,1000);updateClock();
</script>
</body>
</html>
"""


def html_escape(text):
    if not text:
        return ""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def render_category(cat, items, idx):
    num_roman = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"][idx]
    delay = idx * 60
    
    if not items:
        items_html = '<div class="empty">— 데이터를 불러올 수 없습니다 —</div>'
    else:
        items_html = ""
        for item in items:
            link = html_escape(item.get("link", "#"))
            title = html_escape(item.get("title", ""))
            desc = html_escape(item.get("description", ""))
            source = html_escape(item.get("source", ""))
            ttime = html_escape(item.get("time", ""))
            
            meta_parts = []
            if source:
                meta_parts.append(f'<span class="source">{source}</span>')
            if ttime:
                meta_parts.append("<span>·</span>")
                meta_parts.append(f"<span>{ttime}</span>")
            meta_html = "".join(meta_parts)
            
            items_html += f'''
            <div class="news-item">
              <a href="{link}" target="_blank" rel="noopener">
                <div class="news-headline">{title}</div>
                <div class="news-summary">{desc}</div>
                <div class="news-meta">{meta_html}</div>
              </a>
            </div>
            '''
    
    return f'''
    <article class="category reveal" style="animation-delay:{delay}ms">
      <header class="cat-header">
        <div class="cat-title">
          <span class="cat-num">{num_roman}.</span>
          <div>
            <div class="cat-name">{cat["name"]}<span class="han">{cat["han"]}</span></div>
            <div class="cat-en">{cat["en"]}</div>
          </div>
        </div>
        <span class="cat-icon">{cat["icon"]}</span>
      </header>
      {items_html}
    </article>
    '''


def render_hero(data):
    top_items = data.get("top", [])
    if not top_items:
        return '''
        <section class="hero reveal">
          <div class="hero-content">
            <div class="hero-eyebrow">Today's Brief</div>
            <h2>오늘의 브리핑</h2>
            <p>12개 카테고리의 한국 주요 뉴스를 자동으로 정리했습니다.</p>
          </div>
        </section>
        '''
    
    top = top_items[0]
    title = html_escape(top.get("title", ""))
    desc = html_escape(top.get("description", ""))
    link = html_escape(top.get("link", "#"))
    source = html_escape(top.get("source", ""))
    ttime = html_escape(top.get("time", ""))
    
    meta = " · ".join(filter(None, [source, ttime]))
    
    return f'''
    <section class="hero reveal">
      <div class="hero-content">
        <div class="hero-eyebrow">Today's Headline</div>
        <a href="{link}" target="_blank" rel="noopener" class="hero-link">
          <h2>{title}</h2>
        </a>
        <p>{desc}</p>
        <div class="hero-meta">{meta}</div>
      </div>
    </section>
    '''


def generate_html(data):
    now = datetime.now(KST)
    date_short = now.strftime("%Y-%m-%d")
    weekday_kr = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]
    date_full = f"{now.year}년 {now.month}월 {now.day}일 ({weekday_kr})"
    
    start = datetime(now.year, 1, 1, tzinfo=KST)
    edition = (now - start).days + 1
    generated_at = now.strftime("%Y-%m-%d %H:%M KST")
    
    hero_html = render_hero(data)
    top_items = data.get("top", [])
    hero_title = top_items[0].get("title", "오늘의 브리핑") if top_items else "오늘의 브리핑"
    
    categories_html = ""
    for idx, cat in enumerate(CATEGORIES):
        items = data.get(cat["key"], [])
        categories_html += render_category(cat, items, idx)
    
    return HTML_TEMPLATE.format(
        date_short=date_short,
        date_full=date_full,
        edition=f"{edition:03d}",
        generated_at=generated_at,
        hero_title=html_escape(hero_title),
        hero_html=hero_html,
        categories_html=categories_html,
    )


# ============ Notifications ============
def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    body = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False,
    }
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=30).read()
        print(f"[{datetime.now(KST):%H:%M:%S}] ✓ Telegram 발송 완료")
        return True
    except Exception as e:
        print(f"⚠ Telegram 실패: {e}")
        return False


def send_email(subject, html_body):
    if not all([SENDER_EMAIL, SENDER_PASSWORD, RECIPIENT_EMAIL]):
        return False
    
    msg = MIMEText(html_body, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECIPIENT_EMAIL
    
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        print(f"[{datetime.now(KST):%H:%M:%S}] ✓ Email 발송 완료")
        return True
    except Exception as e:
        print(f"⚠ Email 실패: {e}")
        return False


def build_notification_message(data):
    now = datetime.now(KST)
    today = now.strftime("%Y년 %m월 %d일")
    weekday_kr = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]
    
    top_items = data.get("top", [])
    hero_title = top_items[0].get("title", "오늘의 핵심 뉴스") if top_items else "오늘의 핵심 뉴스"
    
    msg = f"☕ *오늘의 브리핑*\n_{today} ({weekday_kr}요일)_\n\n"
    msg += f"*🔥 Headline:* {hero_title}\n\n"
    
    for cat in CATEGORIES[:6]:
        items = data.get(cat["key"], [])
        if items:
            title = items[0].get("title", "")
            if len(title) > 50:
                title = title[:50] + "..."
            msg += f"*{cat['icon']} {cat['name']}*\n• {title}\n\n"
    
    if PAGES_URL:
        msg += f"📰 *전체 보기:* {PAGES_URL}\n"
    
    return msg


# ============ Main ============
def main():
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        print("⚠ NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET 환경변수가 필요합니다.")
        print("  https://developers.naver.com 에서 무료 발급")
        sys.exit(1)
    
    print(f"\n{'='*60}")
    print(f"  오늘의 브리핑 (무료 버전) · {datetime.now(KST):%Y-%m-%d %H:%M:%S KST}")
    print(f"{'='*60}\n")
    
    try:
        data = fetch_all_briefing()
        success_count = sum(1 for k in data if data[k])
        print(f"\n[{datetime.now(KST):%H:%M:%S}] 수집 결과: {success_count}/{len(CATEGORIES)}개")
        
        if success_count == 0:
            raise RuntimeError("모든 카테고리 수집 실패 — API 키 확인 필요")
        
        html = generate_html(data)
        
        docs_dir = Path("docs")
        archive_dir = docs_dir / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        
        today_str = datetime.now(KST).strftime("%Y-%m-%d")
        (docs_dir / "index.html").write_text(html, encoding="utf-8")
        (archive_dir / f"{today_str}.html").write_text(html, encoding="utf-8")
        (docs_dir / "data.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        
        print(f"[{datetime.now(KST):%H:%M:%S}] ✓ HTML 생성 완료")
        
        notif_msg = build_notification_message(data)
        send_telegram(notif_msg)
        
        if SENDER_EMAIL:
            send_email(f"☕ 오늘의 브리핑 · {today_str}", html)
        
        print(f"\n{'='*60}")
        print(f"  ✓ 완료 · {datetime.now(KST):%H:%M:%S KST}")
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"\n⚠ 오류 발생: {e}\n")
        if TELEGRAM_BOT_TOKEN:
            send_telegram(f"⚠ 오늘의 브리핑 생성 실패\n\n오류: {str(e)[:300]}")
        raise


if __name__ == "__main__":
    main()
