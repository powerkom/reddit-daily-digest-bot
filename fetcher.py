import json
import random
import re
import ssl
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

# sub.md 精选 15 个版块[cite: 4]
TOP_SUBREDDITS = [
    "AskHistorians",          # 历史深度问答[cite: 4]
    "WarCollege",             # 军事史/战略[cite: 4]
    "AskAnthropology",        # 人类学/文化史[cite: 4]
    "ExperiencedDevs",        # 资深开发者经验[cite: 4]
    "artificial",             # AI综合讨论[cite: 4]
    "startups",               # 初创企业[cite: 4]
    "SaaS",                   # 订阅制产品经营[cite: 4]
    "EntrepreneurRideAlong",  # 创业过程连载[cite: 4]
    "indiehackers",           # 独立开发者[cite: 4]
    "DepthHub",               # 全站深度长评论聚合[cite: 4]
    "Futurology",             # 未来科技与社会[cite: 4]
    "freelance",              # 自由职业[cite: 4]
    "shortstories",           # 短篇小说[cite: 4]
    "sideproject",            # 个人副业项目[cite: 4]
    "urbanfantasy"            # 现代奇幻小说[cite: 4]
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
]

SSL_CONTEXT = ssl._create_unverified_context()
CACHE_FILE = "reddit_posts_rich_cache.json"

def clean_html(raw_html):
    """清理 RSS 节点中的 HTML 标签并还原字符[cite: 3, 5]"""
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
    """提取高赞回答（抓取上限提升至 5 条，带极长随机冷却）[cite: 8]"""
    clean_path = permalink.rstrip("/")
    rss_comment_url = f"https://www.reddit.com{clean_path}.rss?sort=top"

    # 用于去重的正文特征识别码[cite: 8]
    post_head = post_selftext[:60].strip().lower() if post_selftext else ""

    for attempt in range(1, max_retries + 1):
        req = urllib.request.Request(
            rss_comment_url,
            headers={"User-Agent": random.choice(USER_AGENTS)}
        )
        try:
            # 🌟 调整点 1：评论间休眠拉长至 15 ~ 25 秒，极大降低被风控概率[cite: 5]
            sleep_time = random.uniform(15.0, 25.0)
            time.sleep(sleep_time)

            with urllib.request.urlopen(req, context=SSL_CONTEXT, timeout=20) as response:
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

                # 跳过与原帖正文完全重复的快照节点[cite: 8]
                if post_head and clean_body.lower().startswith(post_head):
                    continue

                # 过滤自动机器人与垃圾回复
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
                    # 🌟 调整点 2：上限满足 5 条即停止[cite: 8]
                    if len(comments) >= max_comments:
                        break

            return comments

        except urllib.error.HTTPError as e:
            if e.code == 429:
                # 🌟 调整点 3：遇到 429 深度休眠 120s, 240s, 360s[cite: 5]
                wait_time = attempt * 120
                print(f"    ⚠️ 触及频控阀值(429)，进入深度休眠 {wait_time} 秒后重试 ({attempt}/{max_retries})...")
                time.sleep(wait_time)
            elif e.code == 403:
                print(f"    ⚠️ 403 阻断，休眠 30 秒后重试 ({attempt}/{max_retries})...")
                time.sleep(30)
            else:
                break
        except Exception:
            break
    return []

def fetch_rich_subreddit(subreddit_name, max_limit=15, max_retries=3):
    """按日抓取板块长帖与独立评论"""
    rss_url = f"https://www.reddit.com/r/{subreddit_name}/top.rss?t=day&limit={max_limit}"
    print(f"\n==========================================")
    print(f"正在抓取 r/{subreddit_name} (超长间隔极高成功率模式)...")

    for attempt in range(1, max_retries + 1):
        req = urllib.request.Request(
            rss_url,
            headers={"User-Agent": random.choice(USER_AGENTS)}
        )

        try:
            with urllib.request.urlopen(req, context=SSL_CONTEXT, timeout=25) as response:
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

                # 提取最多 5 条去重后的真实高赞评论[cite: 8]
                top_comments = []
                if permalink:
                    print(f"  ├─ [拉取评论区 (目标至多5条)]: {title[:20]}...")
                    top_comments = fetch_comments_via_rss(permalink, clean_text, max_comments=5)

                # 过滤无意义水帖
                if len(clean_text) < 80 and not top_comments:
                    print(f"  ├─ ⏩ 跳过: 极短无评论水贴")
                    continue

                valid_posts.append({
                    "subreddit": subreddit_name,
                    "title": title,
                    "selftext": clean_text[:4000],
                    "comments": top_comments,
                    "url": link,
                })

                status = f"🔥 捕获 {len(top_comments)} 条真实独立回答" if top_comments else "📄 仅正文"
                print(f"  ├─ ✅ 入库 [{status}]: {title[:18]}...")

            print(f"  └─ r/{subreddit_name} 处理完毕，共收集到 {len(valid_posts)} 篇。")
            return valid_posts

        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait_time = attempt * 120
                print(f"  ⚠️ 版块拉取触发 429，休眠 {wait_time} 秒重试 ({attempt}/{max_retries})...")
                time.sleep(wait_time)
            else:
                print(f"  ❌ HTTP 报错: {e.code}")
                break
        except Exception as e:
            print(f"  ❌ 抓取异常: {e}")
            break

    return []

if __name__ == "__main__":
    all_selected_posts = []

    print("🚀 开始按日全量提取 15 个精选版块（极速降频 / 允许耗时 1-2 小时）...\n")

    for sub in TOP_SUBREDDITS:
        posts = fetch_rich_subreddit(sub, max_limit=15)
        all_selected_posts.extend(posts)
        
        # 🌟 调整点 4：版块间强制休眠 60 秒（1 分钟）[cite: 5]
        print(f"  💤 版块间保护性休眠 60 秒，等待风控清零...")
        time.sleep(60)

    print("\n" + "=" * 50)
    print(f"🎉 每日例行抓取完成！共收集到 {len(all_selected_posts)} 篇深度长帖。")

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(all_selected_posts, f, ensure_ascii=False, indent=2)

    print(f"📁 含有真实高赞回答的数据已成功写入缓存: {CACHE_FILE}")