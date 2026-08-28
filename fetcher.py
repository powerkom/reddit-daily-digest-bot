import json
import random
import re
import ssl
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

TOP_SUBREDDITS = [
    "AskHistorians",          # 历史深度问答
    "WarCollege",             # 军事史/战略
    "AskAnthropology",        # 人类学/文化史
    "ExperiencedDevs",        # 资深开发者经验
    "artificial",             # AI综合讨论
    "startups",               # 初创企业
    "SaaS",                   # 订阅制产品经营
    "EntrepreneurRideAlong",  # 创业过程连载
    "indiehackers",           # 独立开发者
    "DepthHub",               # 全站深度长评论聚合
    "Futurology",             # 未来科技与社会
    "freelance",              # 自由职业
    "shortstories",           # 短篇小说
    "sideproject",            # 个人副业项目
    "urbanfantasy"            # 现代奇幻小说
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
]

SSL_CONTEXT = ssl._create_unverified_context()
CACHE_FILE = "reddit_posts_rich_cache.json"

def clean_html(raw_html):
    if not raw_html:
        return ""
    text = re.sub(r"<[^>]+>", "", raw_html)
    text = (
        text.replace("&quot;", '"')
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&#39;", "'")
    )
    return text.strip()

def fetch_comments_via_rss(permalink, post_selftext, max_comments=5, max_retries=3):
    clean_path = permalink.rstrip("/")
    rss_comment_url = f"https://www.reddit.com{clean_path}.rss?sort=top"
    post_head = post_selftext[:60].strip().lower() if post_selftext else ""

    for attempt in range(1, max_retries + 1):
        req = urllib.request.Request(
            rss_comment_url,
            headers={"User-Agent": random.choice(USER_AGENTS)}
        )
        try:
            # 适度休眠 5~8 秒，云端动态 IP 极其安全
            sleep_time = random.uniform(5.0, 8.0)
            time.sleep(sleep_time)

            with urllib.request.urlopen(req, context=SSL_CONTEXT, timeout=15) as response:
                xml_data = response.read()

            root = ET.fromstring(xml_data)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            comments = []

            for entry in root.findall("atom:entry", ns):
                content_node = entry.find("atom:content", ns)
                raw_content = content_node.text if content_node is not None else ""
                clean_body = clean_html(raw_content)

                author_node = entry.find("atom:author", ns)
                author_name = "匿名用户"
                if author_node is not None:
                    name_node = author_node.find("atom:name", ns)
                    if name_node is not None:
                        author_name = name_node.text.replace("/u/", "")

                if "submitted by" in clean_body:
                    clean_body = clean_body.split("submitted by")[0].strip()

                if post_head and clean_body.lower().startswith(post_head):
                    continue

                if (
                    clean_body
                    and author_name.lower() not in ["automoderator", "bot", "auto-moderator"]
                    and clean_body not in ["[deleted]", "[removed]"]
                    and len(clean_body) >= 20
                ):
                    comments.append({
                        "author": author_name,
                        "body": clean_body[:3500]
                    })
                    if len(comments) >= max_comments:
                        break

            return comments

        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait_time = attempt * 30
                print(f"    ⚠️ 触及 429 频控，休眠 {wait_time} 秒后重试 ({attempt}/{max_retries})...")
                time.sleep(wait_time)
            elif e.code == 403:
                print(f"    ⚠️ 403 阻断，休眠 15 秒...")
                time.sleep(15)
            else:
                break
        except Exception:
            break
    return []

def fetch_rich_subreddit(subreddit_name, max_limit=10, max_retries=3):
    rss_url = f"https://www.reddit.com/r/{subreddit_name}/top.rss?t=day&limit={max_limit}"
    print(f"\n==========================================")
    print(f"正在抓取 r/{subreddit_name}...")

    for attempt in range(1, max_retries + 1):
        req = urllib.request.Request(
            rss_url,
            headers={"User-Agent": random.choice(USER_AGENTS)}
        )

        try:
            with urllib.request.urlopen(req, context=SSL_CONTEXT, timeout=20) as response:
                xml_data = response.read()

            root = ET.fromstring(xml_data)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            valid_posts = []

            for entry in root.findall("atom:entry", ns):
                title = entry.find("atom:title", ns).text
                link = entry.find("atom:link", ns).attrib.get("href", "")
                content_node = entry.find("atom:content", ns)
                raw_content = content_node.text if content_node is not None else ""

                clean_text = clean_html(raw_content)
                if "submitted by" in clean_text:
                    clean_text = clean_text.split("submitted by")[0].strip()

                permalink_match = re.search(r"/r/[^/]+/comments/[^/]+/[^/]+/", link)
                permalink = permalink_match.group(0) if permalink_match else None

                top_comments = []
                if permalink:
                    print(f"  ├─ [拉取评论区]: {title[:20]}...")
                    top_comments = fetch_comments_via_rss(permalink, clean_text, max_comments=5)

                if len(clean_text) < 80 and not top_comments:
                    print(f"  ├─ ⏩ 跳过: 极短无评论水帖")
                    continue

                valid_posts.append({
                    "subreddit": subreddit_name,
                    "title": title,
                    "selftext": clean_text[:4000],
                    "comments": top_comments,
                    "url": link,
                })

                status = f"🔥 捕获 {len(top_comments)} 条回答" if top_comments else "📄 仅正文"
                print(f"  ├─ ✅ 入库 [{status}]: {title[:18]}...")

            print(f"  └─ r/{subreddit_name} 处理完毕，共收集到 {len(valid_posts)} 篇。")
            return valid_posts

        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait_time = attempt * 30
                print(f"  ⚠️ 板块拉取触发 429，休眠 {wait_time} 秒...")
                time.sleep(wait_time)
            else:
                break
        except Exception:
            break

    return []

if __name__ == "__main__":
    all_selected_posts = []
    print("🚀 开始按日全量提取 15 个精选板块...\n")

    for sub in TOP_SUBREDDITS:
        posts = fetch_rich_subreddit(sub, max_limit=10)
        all_selected_posts.extend(posts)
        print(f"  💤 板块间保护性休眠 15 秒...")
        time.sleep(15)

    print("\n" + "=" * 50)
    print(f"🎉 抓取完成！共收集到 {len(all_selected_posts)} 篇深度文章。")

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(all_selected_posts, f, ensure_ascii=False, indent=2)
