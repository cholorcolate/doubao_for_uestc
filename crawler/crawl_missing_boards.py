"""
爬取缺失的板块
"""

import os
import sys
import time
from uestc_bbs_crawler import UESTCBBSrawler

# 缺失的板块
MISSING_BOARDS = [2, 46, 55, 74, 114, 115, 118, 140, 149, 208, 244, 312, 313, 334, 888]
BOARD_NAMES = {
    2: '站务公告', 46: '站务综合', 55: '视觉艺术', 74: '音乐空间',
    114: '文人墨客', 115: '军事国防', 118: '体坛风云', 140: '动漫时代',
    149: '影视天地', 208: '社团交流中心', 244: '成电骑迹', 312: '跑步家园',
    313: '鹊桥', 334: '情系舞缘', 888: '投资理财'
}

def main():
    # 登录
    username = os.environ.get("BBS_USER", "Linduer")
    password = os.environ.get("BBS_PASS")
    
    if not password:
        print("请设置 BBS_PASS 环境变量")
        return
    
    crawler = UESTCBBSrawler()
    if not crawler.login(username, password):
        print("登录失败")
        return
    
    print(f"开始爬取 {len(MISSING_BOARDS)} 个缺失板块...")
    
    total_threads = 0
    for i, fid in enumerate(MISSING_BOARDS, 1):
        name = BOARD_NAMES.get(fid, str(fid))
        print(f"\n[{i}/{len(MISSING_BOARDS)}] 处理板块: {name} (fid={fid})")
        
        # 保存板块信息
        board_info = {"fid": str(fid), "name": name, "url": f"https://bbs.uestc.edu.cn/forum.php?mod=forumdisplay&fid={fid}"}
        crawler.save_board(board_info)
        
        # 爬取帖子列表（所有页面）
        threads = crawler.crawl_board(str(fid), max_pages=100)
        total_threads += len(threads)
        
        # 爬取帖子内容
        if threads:
            print(f"  开始爬取帖子内容...")
            for j, thread in enumerate(threads, 1):
                print(f"    [{j}/{len(threads)}] {thread['title'][:30]}...")
                crawler.crawl_thread(thread["tid"])
                time.sleep(0.3)
        
        time.sleep(1)
    
    print(f"\n爬取完成! 共爬取 {total_threads} 个帖子")

if __name__ == "__main__":
    main()
