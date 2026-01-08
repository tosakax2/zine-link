"""
Gigazine RSS to Discord Bot
GigazineのRSSフィードを取得し、新着記事をDiscord Webhookで投稿する
"""

import os
import re
import json
import feedparser
import requests
from datetime import datetime

# 設定
GIGAZINE_RSS_URL = "https://gigazine.net/news/rss_2.0/"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GIST_TOKEN = os.environ.get("GIST_TOKEN")
GIST_ID = os.environ.get("GIST_ID")
STATE_FILENAME = "gigazine_state.json"


def get_state_from_gist() -> dict:
    """Gistから最終投稿状態を取得"""
    if not GIST_TOKEN or not GIST_ID:
        print("Warning: Gist credentials not set, skipping state check")
        return {"last_posted_ids": []}
    
    headers = {
        "Authorization": f"token {GIST_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        response = requests.get(
            f"https://api.github.com/gists/{GIST_ID}",
            headers=headers
        )
        response.raise_for_status()
        
        gist_data = response.json()
        if STATE_FILENAME in gist_data.get("files", {}):
            content = gist_data["files"][STATE_FILENAME]["content"]
            return json.loads(content)
    except Exception as e:
        print(f"Error fetching state from Gist: {e}")
    
    return {"last_posted_ids": []}


def save_state_to_gist(state: dict) -> None:
    """Gistに状態を保存"""
    if not GIST_TOKEN or not GIST_ID:
        return
    
    headers = {
        "Authorization": f"token {GIST_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    payload = {
        "files": {
            STATE_FILENAME: {
                "content": json.dumps(state, ensure_ascii=False, indent=2)
            }
        }
    }
    
    try:
        response = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        print("State saved to Gist")
    except Exception as e:
        print(f"Error saving state to Gist: {e}")


def strip_html_tags(text: str) -> str:
    """HTMLタグを除去してプレーンテキストに変換"""
    if not text:
        return ""
    # HTMLタグを除去
    clean = re.sub(r'<[^>]+>', '', text)
    # HTMLエンティティをデコード
    clean = clean.replace('&nbsp;', ' ')
    clean = clean.replace('&amp;', '&')
    clean = clean.replace('&lt;', '<')
    clean = clean.replace('&gt;', '>')
    clean = clean.replace('&quot;', '"')
    clean = clean.replace('&#39;', "'")
    # 余分な空白を整理
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean


def fetch_rss() -> list[dict]:
    """GigazineのRSSフィードを取得してパース"""
    feed = feedparser.parse(GIGAZINE_RSS_URL)
    articles = []
    
    for entry in feed.entries[:10]:  # 最新10件まで
        # サムネイル画像を取得
        image = None
        if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
            image = entry.media_thumbnail[0].get('url')
        elif hasattr(entry, 'enclosures') and entry.enclosures:
            for enc in entry.enclosures:
                if enc.get('type', '').startswith('image/'):
                    image = enc.get('href')
                    break
        
        # サマリーからHTMLタグを除去
        raw_summary = entry.get("summary", "")
        clean_summary = strip_html_tags(raw_summary)
        if len(clean_summary) > 200:
            clean_summary = clean_summary[:200] + "..."
        
        articles.append({
            "id": entry.get("id", entry.link),
            "title": strip_html_tags(entry.title),
            "link": entry.link,
            "published": entry.get("published", ""),
            "summary": clean_summary,
            "image": image
        })
    
    return articles


def post_to_discord(article: dict) -> bool:
    """Discord Webhookで記事を投稿"""
    if not DISCORD_WEBHOOK_URL:
        print("Error: DISCORD_WEBHOOK_URL not set")
        return False
    
    embed = {
        "title": article["title"],
        "url": article["link"],
        "description": article["summary"],
        "color": 0xFF6600,  # Gigazineのオレンジ色
        "footer": {
            "text": "GIGAZINE"
        },
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # 大きな画像として表示（thumbnailではなくimage）
    if article.get("image"):
        embed["image"] = {"url": article["image"]}
    
    payload = {
        "embeds": [embed]
    }
    
    try:
        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json=payload
        )
        response.raise_for_status()
        print(f"Posted: {article['title']}")
        return True
    except Exception as e:
        print(f"Error posting to Discord: {e}")
        return False


def main():
    print("=== Gigazine to Discord Bot ===")
    print(f"Time: {datetime.now().isoformat()}")
    
    # 現在の状態を取得
    state = get_state_from_gist()
    posted_ids = set(state.get("last_posted_ids", []))
    
    # RSS取得
    articles = fetch_rss()
    print(f"Fetched {len(articles)} articles from RSS")
    
    # 新着記事を投稿（古い順に）
    new_articles = [a for a in articles if a["id"] not in posted_ids]
    new_articles.reverse()  # 古い順にする
    
    print(f"New articles to post: {len(new_articles)}")
    
    posted_count = 0
    for article in new_articles:
        if post_to_discord(article):
            posted_ids.add(article["id"])
            posted_count += 1
    
    # 状態を保存（最新100件のIDを保持）
    all_ids = list(posted_ids)
    state["last_posted_ids"] = all_ids[-100:]  # 最新100件のみ保持
    save_state_to_gist(state)
    
    print(f"=== Done: {posted_count} articles posted ===")


if __name__ == "__main__":
    main()
