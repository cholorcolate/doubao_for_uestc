"""
清水河畔论坛爬虫
用于爬取 https://bbs.uestc.edu.cn 的所有信息
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import os
import re
from urllib.parse import urljoin, urlparse
import hashlib


class UESTCBBSrawler:
    def __init__(self):
        self.base_url = "https://bbs.uestc.edu.cn"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Referer": self.base_url,
        })
        self.logged_in = False
        self.data_dir = "data"
        self._ensure_data_dir()
    
    def _ensure_data_dir(self):
        """确保数据目录存在"""
        for subdir in ["boards", "threads", "posts", "users"]:
            os.makedirs(os.path.join(self.data_dir, subdir), exist_ok=True)
    
    def login(self, username, password):
        """登录论坛"""
        print(f"正在登录... 用户名: {username}")
        
        # 获取登录页面
        login_url = f"{self.base_url}/member.php?mod=logging&action=login"
        response = self.session.get(login_url)
        
        if response.status_code != 200:
            print(f"获取登录页面失败: {response.status_code}")
            return False
        
        # 解析登录表单
        soup = BeautifulSoup(response.text, "html.parser")
        
        # 获取formhash
        formhash_input = soup.find("input", {"name": "formhash"})
        if not formhash_input:
            print("未找到formhash")
            return False
        formhash = formhash_input["value"]
        
        # 构建登录数据
        login_data = {
            "formhash": formhash,
            "referer": self.base_url,
            "loginfield": "username",
            "username": username,
            "password": password,
            "questionid": "0",
            "answer": "",
            "cookietime": "2592000",
            "handlekey": "login",
        }
        
        # 提交登录
        login_submit_url = f"{self.base_url}/member.php?mod=logging&action=login&loginsubmit=yes&handlekey=login"
        response = self.session.post(login_submit_url, data=login_data)
        
        # 检查登录结果
        if "欢迎您回来" in response.text or username in response.text:
            print("登录成功!")
            self.logged_in = True
            return True
        elif "密码错误" in response.text or "用户名不存在" in response.text:
            print("登录失败: 用户名或密码错误")
            return False
        else:
            # 可能需要验证码
            print("登录可能需要验证码，尝试继续...")
            if "安全验证" in response.text or "验证码" in response.text:
                print("检测到验证码，请手动处理")
                return False
            # 检查cookie是否包含登录标识
            if "v3hW_2132_" in str(self.session.cookies):
                print("登录成功 (通过cookie检测)")
                self.logged_in = True
                return True
            return False
    
    def get_page(self, url, retries=3):
        """获取页面内容"""
        for i in range(retries):
            try:
                response = self.session.get(url, timeout=10)
                if response.status_code == 200:
                    return response.text
                else:
                    print(f"请求失败: {url}, 状态码: {response.status_code}")
            except Exception as e:
                print(f"请求异常: {url}, 错误: {e}")
            time.sleep(1)
        return None
    
    def parse_boards(self):
        """解析所有板块"""
        print("正在解析板块列表...")
        
        html = self.get_page(f"{self.base_url}/forum.php")
        if not html:
            return []
        
        soup = BeautifulSoup(html, "html.parser")
        boards = []
        
        # 查找所有板块链接
        # Discuz论坛的板块通常在特定的表格或div中
        board_links = soup.find_all("a", href=re.compile(r"forum\.php\?mod=forumdisplay&fid=\d+"))
        
        seen_fids = set()
        for link in board_links:
            href = link.get("href", "")
            match = re.search(r"fid=(\d+)", href)
            if match:
                fid = match.group(1)
                if fid not in seen_fids:
                    seen_fids.add(fid)
                    name = link.get_text(strip=True)
                    if name:
                        boards.append({
                            "fid": fid,
                            "name": name,
                            "url": urljoin(self.base_url, href)
                        })
        
        print(f"找到 {len(boards)} 个板块")
        return boards
    
    def parse_thread_list(self, fid, page=1):
        """解析板块下的帖子列表"""
        if page == 1:
            url = f"{self.base_url}/forum.php?mod=forumdisplay&fid={fid}"
        else:
            url = f"{self.base_url}/forum.php?mod=forumdisplay&fid={fid}&page={page}"
        
        html = self.get_page(url)
        if not html:
            return [], False
        
        soup = BeautifulSoup(html, "html.parser")
        threads = []
        
        # 查找帖子列表
        # Discuz论坛帖子通常在id为threadlist的div中
        threadlist = soup.find("div", {"id": "threadlist"})
        if not threadlist:
            # 尝试其他选择器
            threadlist = soup.find("div", {"id": "threadlistts"})
        
        if threadlist:
            # 查找所有帖子行
            thread_rows = threadlist.find_all("li", {"id": re.compile(r"normalthread_\d+")})
            
            for row in thread_rows:
                thread_id = re.search(r"normalthread_(\d+)", row.get("id", "")).group(1)
                
                # 获取帖子标题
                title_link = row.find("a", {"class": "s xst"})
                if not title_link:
                    title_link = row.find("a", href=re.compile(r"viewthread.*tid=\d+"))
                
                if title_link:
                    title = title_link.get_text(strip=True)
                    thread_url = urljoin(self.base_url, title_link.get("href", ""))
                    
                    # 获取作者
                    author_elem = row.find("a", {"class": "xw1"})
                    author = author_elem.get_text(strip=True) if author_elem else ""
                    
                    # 获取回复数和查看数
                    nums = row.find_all("td", {"class": "num"})
                    replies = 0
                    views = 0
                    if nums:
                        num_links = nums[0].find_all("a")
                        if num_links:
                            replies = int(num_links[0].get_text(strip=True) or 0)
                        view_em = nums[0].find("em")
                        if view_em:
                            views = int(view_em.get_text(strip=True) or 0)
                    
                    threads.append({
                        "tid": thread_id,
                        "title": title,
                        "url": thread_url,
                        "author": author,
                        "replies": replies,
                        "views": views,
                        "fid": fid,
                    })
        
        # 检查是否有下一页
        has_next = False
        pager = soup.find("div", {"class": "pg"})
        if pager:
            next_link = pager.find("a", {"class": "nxt"})
            if next_link:
                has_next = True
        
        return threads, has_next
    
    def parse_thread(self, tid):
        """解析帖子内容"""
        url = f"{self.base_url}/forum.php?mod=viewthread&tid={tid}"
        html = self.get_page(url)
        if not html:
            return None
        
        soup = BeautifulSoup(html, "html.parser")
        
        # 获取帖子标题
        title_elem = soup.find("span", {"id": "thread_subject"})
        if not title_elem:
            title_elem = soup.find("h1")
        title = title_elem.get_text(strip=True) if title_elem else ""
        
        posts = []
        
        # 查找所有回复
        post_list = soup.find_all("div", {"id": re.compile(r"post_\d+")})
        
        for post_div in post_list:
            post_id_match = re.search(r"post_(\d+)", post_div.get("id", ""))
            if not post_id_match:
                continue
            post_id = post_id_match.group(1)
            
            # 获取作者
            author_elem = post_div.find("a", {"class": "xw1"})
            author = author_elem.get_text(strip=True) if author_elem else ""
            
            # 获取时间
            time_elem = post_div.find("em", {"id": f"authorposton{post_id}"})
            if not time_elem:
                time_elem = post_div.find("em", {"id": re.compile(r"authorposton")})
            post_time = time_elem.get_text(strip=True) if time_elem else ""
            
            # 获取内容
            content_elem = post_div.find("td", {"class": "t_f"})
            if not content_elem:
                content_elem = post_div.find("div", {"class": "t_f"})
            if not content_elem:
                content_elem = post_div.find("td", {"id": f"postmessage_{post_id}"})
            content = content_elem.get_text(strip=True) if content_elem else ""
            
            # 获取楼层
            floor_elem = post_div.find("a", {"class": "floor"})
            if not floor_elem:
                floor_elem = post_div.find("strong", {"class": "y"})
            floor = floor_elem.get_text(strip=True) if floor_elem else ""
            
            posts.append({
                "post_id": post_id,
                "author": author,
                "time": post_time,
                "content": content,
                "floor": floor,
            })
        
        # 获取帖子信息
        thread_info = {
            "tid": tid,
            "title": title,
            "posts": posts,
            "total_posts": len(posts),
        }
        
        return thread_info
    
    def save_board(self, board_info):
        """保存板块信息"""
        filepath = os.path.join(self.data_dir, "boards", f"board_{board_info['fid']}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(board_info, f, ensure_ascii=False, indent=2)
    
    def save_threads(self, fid, threads):
        """保存帖子列表"""
        filepath = os.path.join(self.data_dir, "threads", f"threads_{fid}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(threads, f, ensure_ascii=False, indent=2)
    
    def save_thread(self, thread_info):
        """保存帖子内容"""
        filepath = os.path.join(self.data_dir, "posts", f"thread_{thread_info['tid']}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(thread_info, f, ensure_ascii=False, indent=2)
    
    def crawl_board(self, fid, max_pages=10):
        """爬取一个板块的所有帖子"""
        print(f"正在爬取板块 {fid}...")
        
        all_threads = []
        page = 1
        
        while page <= max_pages:
            print(f"  爬取第 {page} 页...")
            threads, has_next = self.parse_thread_list(fid, page)
            
            if not threads:
                break
            
            all_threads.extend(threads)
            
            if not has_next:
                break
            
            page += 1
            time.sleep(0.5)  # 礼貌性延迟
        
        # 保存帖子列表
        if all_threads:
            self.save_threads(fid, all_threads)
            print(f"  板块 {fid} 共爬取 {len(all_threads)} 个帖子")
        
        return all_threads
    
    def crawl_thread(self, tid):
        """爬取一个帖子的完整内容"""
        thread_info = self.parse_thread(tid)
        if thread_info:
            self.save_thread(thread_info)
            return thread_info
        return None
    
    def crawl_all(self, max_pages_per_board=5, crawl_content=True):
        """爬取所有内容"""
        # 1. 获取所有板块
        boards = self.parse_boards()
        
        # 保存板块列表
        boards_file = os.path.join(self.data_dir, "boards_list.json")
        with open(boards_file, "w", encoding="utf-8") as f:
            json.dump(boards, f, ensure_ascii=False, indent=2)
        
        print(f"\n共找到 {len(boards)} 个板块")
        
        # 2. 爬取每个板块
        total_threads = 0
        for i, board in enumerate(boards, 1):
            print(f"\n[{i}/{len(boards)}] 处理板块: {board['name']} (fid={board['fid']})")
            self.save_board(board)
            
            # 爬取帖子列表
            threads = self.crawl_board(board["fid"], max_pages_per_board)
            total_threads += len(threads)
            
            # 爬取帖子内容
            if crawl_content and threads:
                print(f"  开始爬取帖子内容...")
                for j, thread in enumerate(threads[:10], 1):  # 每个板块只爬前10个帖子
                    print(f"    [{j}/{min(len(threads), 10)}] {thread['title'][:30]}...")
                    self.crawl_thread(thread["tid"])
                    time.sleep(0.3)
            
            time.sleep(1)  # 板块间延迟
        
        print(f"\n爬取完成! 共爬取 {total_threads} 个帖子")
    
    def crawl_specific(self, fids=None, tids=None, max_pages=10):
        """爬取指定的板块或帖子"""
        if fids:
            for fid in fids:
                print(f"\n爬取板块 {fid}...")
                threads = self.crawl_board(fid, max_pages)
                for thread in threads:
                    self.crawl_thread(thread["tid"])
                    time.sleep(0.3)
        
        if tids:
            for tid in tids:
                print(f"\n爬取帖子 {tid}...")
                self.crawl_thread(tid)
                time.sleep(0.3)


def main():
    """主函数"""
    crawler =UESTCBBSrawler()
    
    # 登录
    username = "Linduer"
    password = input("请输入密码: ")
    
    if not crawler.login(username, password):
        print("登录失败，请检查账号密码")
        return
    
    # 选择爬取模式
    print("\n请选择爬取模式:")
    print("1. 爬取所有板块和帖子")
    print("2. 爬取指定板块")
    print("3. 爬取指定帖子")
    print("4. 只爬取板块列表")
    
    choice = input("请输入选择 (1-4): ").strip()
    
    if choice == "1":
        crawler.crawl_all(max_pages_per_board=5, crawl_content=True)
    elif choice == "2":
        fids = input("请输入板块ID (多个用逗号分隔): ").strip().split(",")
        crawler.crawl_specific(fids=fids, max_pages=10)
    elif choice == "3":
        tids = input("请输入帖子ID (多个用逗号分隔): ").strip().split(",")
        crawler.crawl_specific(tids=tids)
    elif choice == "4":
        boards = crawler.parse_boards()
        boards_file = os.path.join(crawler.data_dir, "boards_list.json")
        with open(boards_file, "w", encoding="utf-8") as f:
            json.dump(boards, f, ensure_ascii=False, indent=2)
        print(f"板块列表已保存到 {boards_file}")
    else:
        print("无效选择")


if __name__ == "__main__":
    main()
