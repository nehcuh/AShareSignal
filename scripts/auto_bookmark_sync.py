#!/usr/bin/env python3
import os
import json
import requests
from datetime import datetime

# 配置
CAMOFOX_API = "http://localhost:9377"
USER_ID = "user1"
BOOKMARKS_DIR = "/Users/huchen/Projects/KnowledgeBase/02.Cards/Knowledge/AI书签整理"
PROCESSED_IDS_FILE = os.path.join(BOOKMARKS_DIR, ".processed_bookmarks.json")

# 加载已经处理过的书签ID
def load_processed_ids():
    if os.path.exists(PROCESSED_IDS_FILE):
        with open(PROCESSED_IDS_FILE, "r") as f:
            return set(json.load(f))
    return set()

# 保存已经处理过的书签ID
def save_processed_ids(processed_ids):
    with open(PROCESSED_IDS_FILE, "w") as f:
        json.dump(list(processed_ids), f)

# 获取当前页面的书签内容
def get_bookmarks():
    url = f"{CAMOFOX_API}/tabs?userId={USER_ID}"
    resp = requests.get(url)
    tabs = resp.json()
    # 找到书签页的tab
    bookmark_tab = None
    for tab in tabs:
        if "/i/bookmarks" in tab["url"]:
            bookmark_tab = tab
            break
    if not bookmark_tab:
        # 没有找到的话新建tab打开书签页
        create_url = f"{CAMOFOX_API}/tabs"
        resp = requests.post(create_url, json={
            "userId": USER_ID,
            "url": "https://x.com/i/bookmarks"
        })
        bookmark_tab = resp.json()
    
    tab_id = bookmark_tab["tabId"]
    # 滚动加载所有书签
    bookmarks = []
    last_count = 0
    while True:
        # 获取当前页面快照
        snapshot_url = f"{CAMOFOX_API}/tabs/{tab_id}/snapshot?userId={USER_ID}"
        resp = requests.get(snapshot_url)
        snapshot = resp.json()
        snapshot_html = snapshot["snapshot"]
        
        # 提取当前页面的书签
        current_bookmarks = extract_bookmarks_from_snapshot(snapshot_html)
        bookmarks.extend(current_bookmarks)
        bookmarks = list({b["id"]: b for b in bookmarks}.values())  # 去重
        
        if len(bookmarks) == last_count:
            # 没有新内容了，加载完成
            break
        last_count = len(bookmarks)
        
        # 滚动加载更多
        scroll_url = f"{CAMOFOX_API}/tabs/{tab_id}/scroll"
        requests.post(scroll_url, json={
            "userId": USER_ID,
            "direction": "down",
            "amount": 1000
        })
    
    return bookmarks

# 从快照中提取书签信息
def extract_bookmarks_from_snapshot(snapshot):
    import re
    bookmarks = []
    # 匹配每个书签article
    pattern = re.compile(r'article\s+"(.*?)\s+认证账号\s+@(\w+)\s+(\d+月\d+日)\s+(.*?)\s+(\d+\s+回复、.*?次观看)"[^>]*?/url:\s*(https://x.com/\w+/status/\d+)', re.DOTALL)
    matches = pattern.findall(snapshot)
    for match in matches:
        author_name, author_id, publish_date, content, stats, url = match
        bookmark_id = url.split("/")[-1]
        bookmarks.append({
            "id": bookmark_id,
            "author_name": author_name.strip(),
            "author_id": author_id.strip(),
            "publish_date": publish_date.strip(),
            "content": content.strip(),
            "url": url.strip(),
            "stats": stats.strip()
        })
    return bookmarks

# 自动分类书签，生成markdown内容
def categorize_and_generate_md(bookmark):
    content = bookmark["content"].lower()
    # 判断分类
    category = None
    if any(keyword in content for keyword in ["ai", "llm", "模型", "openclaw", "harness", "agent", "智能体", "prompt", "研究", "深度学习", "机器学习", "算法"]):
        if any(keyword in content for keyword in ["工具", "开源", "github", "cli", "插件", "框架"]):
            category = "7. AI工具&开源项目.md"
        elif any(keyword in content for keyword in ["多agent", "架构", "harness", "openclaw", "hermes"]):
            category = "2. AI核心技术-Harness&OpenClaw.md"
        elif any(keyword in content for keyword in ["安全", "风险", "漏洞", "攻击"]):
            category = "3. AI核心技术-学习资源&安全.md"
        elif any(keyword in content for keyword in ["研究方法", "prompt", "学习方法", "方法论"]):
            category = "4. 研究方法论.md"
        elif any(keyword in content for keyword in ["创业", "副业", "赚钱", "商业化", "落地"]):
            category = "5. AI商业案例.md"
        else:
            category = "3. AI核心技术-学习资源&安全.md"
    elif any(keyword in content for keyword in ["钱", "理财", "公积金", "投资", "省钱", "技巧", "生活"]):
        category = "6. 生活实用知识.md"
    else:
        # 其他分类暂时归到生活类
        category = "6. 生活实用知识.md"
    
    # 生成markdown条目
    md_content = f"""
### {bookmark['content'].split('。')[0]}
- 核心内容：{bookmark['content']}
- 作者：{bookmark['author_name']}（@{bookmark['author_id']}）
- 发布时间：{bookmark['publish_date']}
- 来源：{bookmark['url']}
"""
    return category, md_content

# 把内容追加到对应的markdown文件
def append_to_category_file(category, md_content):
    file_path = os.path.join(BOOKMARKS_DIR, category)
    with open(file_path, "a") as f:
        f.write(md_content)

# 主函数
def main():
    print(f"[{datetime.now()}] 开始整理推特书签...")
    # 加载已经处理过的ID
    processed_ids = load_processed_ids()
    print(f"已处理过的书签数量：{len(processed_ids)}")
    
    # 获取所有书签
    bookmarks = get_bookmarks()
    print(f"获取到的总书签数量：{len(bookmarks)}")
    
    # 过滤新书签
    new_bookmarks = [b for b in bookmarks if b["id"] not in processed_ids]
    print(f"新书签数量：{len(new_bookmarks)}")
    
    if not new_bookmarks:
        print("没有新的书签需要处理，退出。")
        return
    
    # 处理每个新书签
    for bookmark in new_bookmarks:
        print(f"处理书签：{bookmark['id']} - {bookmark['content'][:30]}...")
        category, md_content = categorize_and_generate_md(bookmark)
        append_to_category_file(category, md_content)
        processed_ids.add(bookmark["id"])
    
    # 保存处理过的ID
    save_processed_ids(processed_ids)
    print(f"[{datetime.now()}] 书签整理完成，共处理{len(new_bookmarks)}条新书签。")

if __name__ == "__main__":
    main()
