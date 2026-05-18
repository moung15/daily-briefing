"""
=============================================================
  오늘의 브리핑 - 완전 무료 + 이메일 호환 버전
=============================================================
  
  v2 변경사항:
  - 이메일 전용 HTML 템플릿 추가 (테이블 + 인라인 스타일)
  - 회사 웹메일/Gmail/Outlook/네이버메일 모두 호환
  - 웹용은 기존 디자인 유지 (GitHub Pages)
  
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
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
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
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = text.replace("\u200b", "").strip()
    return text


def html_escape(text):
    if not text:
        return ""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def relative_time(pub_date_str):
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
        "seoul.co.kr": "서울신문", "munhwa.com": "문화일보",
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
            "title": title, "description": description,
            "link": link, "source": source, "time": rel_time,
        })
    return items


def fetch_all_briefing():
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


# ============ EMAIL HTML (테이블 기반, 모든 메일 클라이언트 호환) ============
def generate_email_html(data):
    """이메일 전용 HTML - 테이블 레이아웃 + 100% 인라인 스타일"""
    now = datetime.now(KST)
    weekday_kr = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]
    date_full = f"{now.year}년 {now.month}월 {now.day}일 ({weekday_kr})"
    generated_at = now.strftime("%Y-%m-%d %H:%M KST")
    
    # Hero
    top_items = data.get("top", [])
    if top_items:
        hero = top_items[0]
        hero_title = html_escape(hero.get("title", "오늘의 브리핑"))
        hero_desc = html_escape(hero.get("description", ""))
        hero_link = html_escape(hero.get("link", "#"))
        hero_source = html_escape(hero.get("source", ""))
        hero_time = html_escape(hero.get("time", ""))
        hero_meta = f"{hero_source} · {hero_time}" if hero_source else hero_time
    else:
        hero_title = "오늘의 브리핑"
        hero_desc = "12개 카테고리 한국 주요 뉴스"
        hero_link = "#"
        hero_meta = ""
    
    # Category sections
    cat_sections = ""
    for idx, cat in enumerate(CATEGORIES):
        items = data.get(cat["key"], [])
        if not items:
            continue
        
        # 주요뉴스 카테고리는 첫번째 항목이 hero와 중복되므로 스킵
        display_items = items[1:] if cat["key"] == "top" else items
        if not display_items:
            continue
        
        items_rows = ""
        for item in display_items[:3]:
            title = html_escape(item.get("title", ""))
            desc = html_escape(item.get("description", ""))
            link = html_escape(item.get("link", "#"))
            source = html_escape(item.get("source", ""))
            ttime = html_escape(item.get("time", ""))
            
            meta_text = f"<b>{source}</b> &nbsp;·&nbsp; {ttime}" if source else ttime
            
            items_rows += f"""
            <tr>
              <td style="padding: 14px 0; border-bottom: 1px dotted #d6cdb8;">
                <a href="{link}" target="_blank" style="text-decoration: none; color: #1a1612; display: block;">
                  <div style="font-family: 'Noto Serif KR', 'Apple SD Gothic Neo', '맑은 고딕', Georgia, serif; font-weight: bold; font-size: 16px; color: #1a1612; line-height: 1.4; margin-bottom: 6px;">{title}</div>
                  <div style="font-family: 'Noto Serif KR', 'Apple SD Gothic Neo', '맑은 고딕', serif; font-size: 13px; color: #4a3f33; line-height: 1.65; margin-bottom: 8px;">{desc}</div>
                  <div style="font-family: 'Apple SD Gothic Neo', '맑은 고딕', Arial, sans-serif; font-size: 11px; color: #7a6a55;">{meta_text}</div>
                </a>
              </td>
            </tr>
            """
        
        roman_num = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"][idx]
        
        cat_sections += f"""
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom: 30px; border-collapse: collapse;">
          <tr>
            <td style="padding: 0 0 12px 0; border-bottom: 2px solid #1a1612;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td>
                    <span style="font-family: Georgia, serif; font-style: italic; font-size: 13px; color: #7a6a55;">{roman_num}.</span>
                    &nbsp;
                    <span style="font-family: 'Noto Serif KR', 'Apple SD Gothic Neo', serif; font-weight: bold; font-size: 22px; color: #1a1612;">{cat['name']}</span>
                    &nbsp;
                    <span style="font-family: 'Apple SD Gothic Neo', Arial, sans-serif; font-size: 12px; color: #a8231f; font-weight: bold;">{cat['han']}</span>
                    <br>
                    <span style="font-family: Georgia, serif; font-style: italic; font-size: 12px; color: #7a6a55; padding-left: 22px;">{cat['en']}</span>
                  </td>
                  <td align="right" valign="top" style="font-size: 22px; color: #7a6a55;">{cat['icon']}</td>
                </tr>
              </table>
            </td>
          </tr>
          {items_rows}
        </table>
        """
    
    pages_link_html = ""
    if PAGES_URL:
        pages_link_html = f"""
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top: 24px;">
          <tr>
            <td align="center">
              <a href="{html_escape(PAGES_URL)}" target="_blank" style="display: inline-block; padding: 14px 28px; background-color: #1a1612; color: #f4ede0; text-decoration: none; font-family: 'Apple SD Gothic Neo', Arial, sans-serif; font-size: 14px; font-weight: bold; letter-spacing: 0.05em;">
                → 전체 페이지에서 보기
              </a>
            </td>
          </tr>
        </table>
        """
    
    return f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>오늘의 브리핑 · {date_full}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f4ede0; font-family: 'Noto Serif KR', 'Apple SD Gothic Neo', '맑은 고딕', Georgia, serif;">

<table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#f4ede0" style="background-color: #f4ede0; padding: 30px 10px;">
<tr><td align="center">

<table width="640" cellpadding="0" cellspacing="0" border="0" bgcolor="#f4ede0" style="background-color: #f4ede0; max-width: 640px; width: 100%;">

<!-- MASTHEAD -->
<tr><td style="padding: 30px 40px 24px; border-top: 4px double #1a1612; border-bottom: 1px solid #1a1612; text-align: center;">
  <div style="font-family: Georgia, serif; font-style: italic; font-size: 11px; color: #7a6a55; letter-spacing: 0.25em; text-transform: uppercase; margin-bottom: 8px;">
    ◆ &nbsp; Your Personal Morning Press &nbsp; ◆
  </div>
  <h1 style="font-family: 'Noto Serif KR', 'Apple SD Gothic Neo', serif; font-weight: 900; font-size: 46px; margin: 6px 0; color: #1a1612; line-height: 1; letter-spacing: -0.02em;">
    오늘의 <span style="color: #a8231f;">브리핑</span>
  </h1>
  <div style="font-family: Georgia, serif; font-style: italic; font-size: 14px; color: #4a3f33; margin-top: 10px;">
    Twelve Categories — Free &amp; Auto-Generated
  </div>
  <div style="font-family: 'Apple SD Gothic Neo', Arial, sans-serif; font-size: 12px; color: #7a6a55; margin-top: 12px; letter-spacing: 0.05em;">
    {date_full} &nbsp; · &nbsp; Edition {(now - datetime(now.year, 1, 1, tzinfo=KST)).days + 1:03d}
  </div>
</td></tr>

<!-- HERO -->
<tr><td style="padding: 30px 40px 0;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#1a1612" style="background-color: #1a1612;">
    <tr>
      <td style="padding: 32px 30px;">
        <div style="font-family: Georgia, serif; font-style: italic; font-size: 11px; color: #ffb8b5; letter-spacing: 0.3em; text-transform: uppercase; margin-bottom: 14px;">
          Today's Headline
        </div>
        <a href="{hero_link}" target="_blank" style="text-decoration: none;">
          <div style="font-family: 'Noto Serif KR', 'Apple SD Gothic Neo', serif; font-weight: 900; font-size: 22px; color: #f4ede0; line-height: 1.35; margin: 0 0 14px;">{hero_title}</div>
        </a>
        <div style="font-family: 'Apple SD Gothic Neo', '맑은 고딕', Arial, sans-serif; font-size: 13px; color: #d6cdb8; line-height: 1.7; margin: 0 0 14px;">{hero_desc}</div>
        <div style="font-family: 'Apple SD Gothic Neo', Arial, sans-serif; font-size: 11px; color: #ffb8b5; letter-spacing: 0.1em; text-transform: uppercase;">{hero_meta}</div>
      </td>
    </tr>
  </table>
</td></tr>

<!-- CATEGORIES -->
<tr><td style="padding: 30px 40px 0;">
  {cat_sections}
</td></tr>

<!-- ACTION BUTTON -->
<tr><td style="padding: 0 40px;">
  {pages_link_html}
</td></tr>

<!-- FOOTER -->
<tr><td style="padding: 30px 40px 40px; border-top: 2px solid #1a1612; text-align: center;">
  <div style="font-family: 'Noto Serif KR', serif; font-weight: bold; font-size: 13px; color: #a8231f; letter-spacing: 0.15em; margin-bottom: 10px;">自動發行</div>
  <p style="font-family: 'Apple SD Gothic Neo', '맑은 고딕', Arial, sans-serif; font-size: 12px; color: #4a3f33; line-height: 1.7; margin: 0;">
    이 브리핑은 <b>매일 오전 8시 KST 자동 발송</b>됩니다.<br>
    Naver Search API · GitHub Actions · 100% 무료 운영<br>
    <span style="font-family: 'Courier New', monospace; font-size: 11px; color: #7a6a55;">{generated_at}</span>
  </p>
</td></tr>

</table>

</td></tr>
</table>

</body>
</html>
"""


# ============ WEB HTML (GitHub Pages용 - 기존 유지) ============
WEB_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>오늘의 브리핑 · {date_short}</title>
<meta name="theme-color" content="#1a1612">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;500;700;900&family=Pretendard:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400&family=Playfair+Display:ital,wght@0,700;1,400&display=swap" rel="stylesheet">
<style>
:root{{--paper:#f4ede0;--ink:#1a1612;--ink-soft:#4a3f33;--ink-light:#7a6a55;--seal-red:#a8231f;--line:rgba(26,22,18,0.18);--line-soft:rgba(26,22,18,0.08);}}
*{{box-sizing:border-box;margin:0;padding:0;}}
html,body{{background:var(--paper);color:var(--ink);font-family:'Noto Serif KR',Georgia,serif;line-height:1.7;}}
.container{{max-width:1280px;margin:0 auto;padding:36px 28px 60px;}}
.masthead{{border-top:4px double var(--ink);border-bottom:1px solid var(--ink);padding:18px 0 14px;margin-bottom:8px;}}
.masthead-top{{display:flex;justify-content:space-between;font-family:'Pretendard',sans-serif;font-size:11px;letter-spacing:0.12em;text-transform:uppercase;color:var(--ink-soft);margin-bottom:18px;flex-wrap:wrap;gap:12px;}}
.title-block{{text-align:center;}}
.eyebrow{{font-family:'Playfair Display',serif;font-style:italic;font-size:13px;letter-spacing:0.3em;color:var(--ink-light);text-transform:uppercase;margin-bottom:4px;}}
.masthead h1{{font-family:'Noto Serif KR',serif;font-weight:900;font-size:clamp(38px,6vw,64px);letter-spacing:-0.02em;line-height:1;margin:4px 0;}}
.masthead h1 .accent{{color:var(--seal-red);}}
.masthead-subtitle{{font-family:'Playfair Display',serif;font-style:italic;font-size:15px;color:var(--ink-soft);margin-top:6px;}}
.masthead-bottom{{display:flex;justify-content:space-between;margin-top:18px;padding-top:14px;border-top:1px solid var(--line);font-family:'Pretendard',sans-serif;font-size:12px;color:var(--ink-soft);flex-wrap:wrap;gap:12px;}}
.hero{{background:var(--ink);color:var(--paper);padding:36px 40px;margin:24px 0 32px;position:relative;overflow:hidden;}}
.hero-content{{position:relative;z-index:1;}}
.hero-eyebrow{{font-family:'Playfair Display',serif;font-style:italic;font-size:12px;color:#ffb8b5;letter-spacing:0.3em;text-transform:uppercase;margin-bottom:12px;}}
.hero h2{{font-family:'Noto Serif KR',serif;font-weight:900;font-size:clamp(24px,3vw,32px);line-height:1.3;margin-bottom:14px;}}
.hero a.hero-link{{color:inherit;text-decoration:none;}}
.hero p{{font-family:'Pretendard',sans-serif;font-size:14px;line-height:1.7;opacity:0.85;max-width:800px;}}
.hero .hero-meta{{font-family:'Pretendard',sans-serif;font-size:11px;color:#ffb8b5;letter-spacing:0.1em;margin-top:14px;text-transform:uppercase;opacity:0.7;}}
.news-grid{{display:grid;grid-template-columns:repeat(12,1fr);gap:0;}}
.category{{padding:28px 26px;border:1px solid var(--line);margin:-0.5px;background:var(--paper);display:flex;flex-direction:column;}}
.category:nth-child(1){{grid-column:span 7;background:rgba(168,35,31,0.04);}}
.category:nth-child(2){{grid-column:span 5;}}
.category:nth-child(3),.category:nth-child(4),.category:nth-child(5){{grid-column:span 4;}}
.category:nth-child(6),.category:nth-child(7){{grid-column:span 6;}}
.category:nth-child(8){{grid-column:span 5;}}
.category:nth-child(9){{grid-column:span 4;}}
.category:nth-child(10){{grid-column:span 3;}}
.category:nth-child(11){{grid-column:span 4;}}
.category:nth-child(12){{grid-column:span 8;}}
.cat-header{{display:flex;justify-content:space-between;padding-bottom:14px;margin-bottom:18px;border-bottom:2px solid var(--ink);}}
.cat-title{{display:flex;align-items:baseline;gap:10px;}}
.cat-num{{font-family:'Playfair Display',serif;font-style:italic;font-size:13px;color:var(--ink-light);}}
.cat-name{{font-family:'Noto Serif KR',serif;font-weight:800;font-size:22px;}}
.cat-name .han{{font-size:14px;color:var(--seal-red);font-weight:700;margin-left:4px;vertical-align:super;}}
.cat-en{{font-family:'Playfair Display',serif;font-style:italic;font-size:12px;color:var(--ink-light);margin-top:4px;}}
.cat-icon{{font-size:22px;color:var(--ink-light);}}
.news-item{{padding:14px 0;border-bottom:1px dotted var(--line-soft);}}
.news-item a{{color:inherit;text-decoration:none;display:block;}}
.news-item a:hover .news-headline{{color:var(--seal-red);}}
.news-headline{{font-family:'Noto Serif KR',serif;font-weight:700;color:var(--ink);font-size:15.5px;line-height:1.45;margin-bottom:6px;}}
.news-summary{{font-family:'Noto Serif KR',serif;font-size:13px;color:var(--ink-soft);line-height:1.65;margin-bottom:6px;}}
.news-meta{{font-family:'Pretendard',sans-serif;font-size:11px;color:var(--ink-light);display:flex;gap:8px;}}
.news-meta .source{{font-weight:600;}}
@media(max-width:900px){{.container{{padding:20px 16px 50px;}}.news-grid{{display:block;}}.category,.category:nth-child(n){{grid-column:span 12;margin:0;}}.masthead h1{{font-size:42px;}}}}
</style>
</head>
<body>
<div class="container">
  <header class="masthead">
    <div class="masthead-top">
      <span>{date_full}</span><span>Edition {edition}</span><span>Seoul · Korea</span>
    </div>
    <div class="title-block">
      <div class="eyebrow">Your Personal Morning Press</div>
      <h1>오늘의 <span class="accent">브리핑</span></h1>
      <div class="masthead-subtitle">Twelve Categories — Free &amp; Auto-Generated</div>
    </div>
    <div class="masthead-bottom">
      <div style="font-family:'IBM Plex Mono',monospace;">{generated_at}</div>
      <div style="font-family:'Playfair Display',serif;font-style:italic;">Free. Daily. Delivered.</div>
    </div>
  </header>
  {hero_html}
  <section class="news-grid">{categories_html}</section>
</div>
</body></html>
"""


def render_web_category(cat, items, idx):
    num_roman = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"][idx]
    if not items:
        items_html = '<div style="text-align:center;padding:20px;color:#7a6a55;">— 데이터 없음 —</div>'
    else:
        items_html = ""
        for item in items:
            link = html_escape(item.get("link", "#"))
            title = html_escape(item.get("title", ""))
            desc = html_escape(item.get("description", ""))
            source = html_escape(item.get("source", ""))
            ttime = html_escape(item.get("time", ""))
            meta = (f'<span class="source">{source}</span><span>·</span><span>{ttime}</span>'
                    if source else f'<span>{ttime}</span>')
            items_html += f'''
            <div class="news-item">
              <a href="{link}" target="_blank" rel="noopener">
                <div class="news-headline">{title}</div>
                <div class="news-summary">{desc}</div>
                <div class="news-meta">{meta}</div>
              </a>
            </div>'''
    return f'''
    <article class="category">
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
    </article>'''


def generate_web_html(data):
    now = datetime.now(KST)
    weekday_kr = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]
    date_full = f"{now.year}년 {now.month}월 {now.day}일 ({weekday_kr})"
    date_short = now.strftime("%Y-%m-%d")
    start = datetime(now.year, 1, 1, tzinfo=KST)
    edition = (now - start).days + 1
    generated_at = now.strftime("%Y-%m-%d %H:%M KST")
    
    top_items = data.get("top", [])
    if top_items:
        top = top_items[0]
        meta = " · ".join(filter(None, [top.get("source", ""), top.get("time", "")]))
        hero_html = f'''
        <section class="hero">
          <div class="hero-content">
            <div class="hero-eyebrow">Today's Headline</div>
            <a href="{html_escape(top.get("link", "#"))}" target="_blank" class="hero-link">
              <h2>{html_escape(top.get("title", ""))}</h2>
            </a>
            <p>{html_escape(top.get("description", ""))}</p>
            <div class="hero-meta">{html_escape(meta)}</div>
          </div>
        </section>'''
    else:
        hero_html = '<section class="hero"><div class="hero-content"><h2>오늘의 브리핑</h2></div></section>'
    
    categories_html = ""
    for idx, cat in enumerate(CATEGORIES):
        items = data.get(cat["key"], [])
        categories_html += render_web_category(cat, items, idx)
    
    return WEB_HTML_TEMPLATE.format(
        date_short=date_short, date_full=date_full,
        edition=f"{edition:03d}", generated_at=generated_at,
        hero_html=hero_html, categories_html=categories_html,
    )


# ============ Notifications ============
def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    body = {"chat_id": TELEGRAM_CHAT_ID, "text": message,
            "parse_mode": "Markdown", "disable_web_page_preview": False}
    try:
        req = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=30).read()
        print(f"[{datetime.now(KST):%H:%M:%S}] ✓ Telegram 발송 완료")
        return True
    except Exception as e:
        print(f"⚠ Telegram 실패: {e}")
        return False


def send_email(subject, html_body):
    """이메일 발송 - text/html + text/plain 둘 다 첨부 (호환성 ↑)"""
    if not all([SENDER_EMAIL, SENDER_PASSWORD, RECIPIENT_EMAIL]):
        return False
    
    # multipart/alternative: HTML 못 읽는 클라이언트는 plain text로 fallback
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr(("오늘의 브리핑", SENDER_EMAIL))
    msg["To"] = RECIPIENT_EMAIL
    
    # Plain text fallback
    plain_text = "오늘의 브리핑이 도착했습니다.\n\n" + (f"전체 보기: {PAGES_URL}" if PAGES_URL else "")
    msg.attach(MIMEText(plain_text, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    
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
        sys.exit(1)
    
    print(f"\n{'='*60}")
    print(f"  오늘의 브리핑 (무료 v2) · {datetime.now(KST):%Y-%m-%d %H:%M:%S KST}")
    print(f"{'='*60}\n")
    
    try:
        data = fetch_all_briefing()
        success_count = sum(1 for k in data if data[k])
        print(f"\n[{datetime.now(KST):%H:%M:%S}] 수집: {success_count}/{len(CATEGORIES)}개")
        
        if success_count == 0:
            raise RuntimeError("모든 카테고리 수집 실패")
        
        # 1. Web HTML (GitHub Pages용)
        web_html = generate_web_html(data)
        
        docs_dir = Path("docs")
        archive_dir = docs_dir / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        today_str = datetime.now(KST).strftime("%Y-%m-%d")
        
        (docs_dir / "index.html").write_text(web_html, encoding="utf-8")
        (archive_dir / f"{today_str}.html").write_text(web_html, encoding="utf-8")
        (docs_dir / "data.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        
        print(f"[{datetime.now(KST):%H:%M:%S}] ✓ Web HTML 생성 완료")
        
        # 2. Email HTML (이메일 전용, 테이블 기반)
        email_html = generate_email_html(data)
        
        # 3. 알림 발송
        send_telegram(build_notification_message(data))
        
        if SENDER_EMAIL:
            send_email(f"☕ 오늘의 브리핑 · {today_str}", email_html)
        
        print(f"\n{'='*60}")
        print(f"  ✓ 완료 · {datetime.now(KST):%H:%M:%S KST}")
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"\n⚠ 오류: {e}\n")
        if TELEGRAM_BOT_TOKEN:
            send_telegram(f"⚠ 오늘의 브리핑 생성 실패\n\n오류: {str(e)[:300]}")
        raise


if __name__ == "__main__":
    main()
