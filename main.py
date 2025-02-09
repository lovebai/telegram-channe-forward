#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import re
import requests
from bs4 import BeautifulSoup
from telegram import Bot, InputMediaPhoto

# 配置项
TOKEN = 'bot token'              # 替换为你的 Bot Token
SOURCE_CHANNEL = 'mzt'           # 源频道的用户名，不带 @（需为公开频道）
TARGET_CHANNEL = '@channel'       # 目标频道，需包含 @
CHANNEL_URL = f"https://t.me/s/{SOURCE_CHANNEL}"
CHECK_INTERVAL = 60                   # 每隔多少秒检查一次新消息

# 用于防重复发送：将已处理的最新消息编号存入文件中
LAST_ID_FILE = "last_id.txt"

def get_last_processed_id():
    """读取上次处理的最新消息编号"""
    try:
        with open(LAST_ID_FILE, "r") as f:
            return int(f.read().strip())
    except Exception:
        return 0

def set_last_processed_id(last_id):
    """保存最新处理的消息编号"""
    with open(LAST_ID_FILE, "w") as f:
        f.write(str(last_id))

def fetch_new_images(last_id):
    """
    爬取公开频道页面，解析出新消息中包含的图片链接
    返回列表格式 [(msg_num, [image_url1, image_url2, ...]), ...] 按消息编号升序排列
    """
    try:
        r = requests.get(CHANNEL_URL, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"获取频道页面失败: {e}")
        return []
    
    soup = BeautifulSoup(r.text, "html.parser")
    message_wraps = soup.find_all("div", class_="tgme_widget_message_wrap")
    
    new_images = []
    for wrap in message_wraps:
        # 查找包含 data-post 属性的消息 div
        msg_div = wrap.find("div", class_=lambda x: x and "js-widget_message" in x)
        if not msg_div:
            continue

        data_post = msg_div.get("data-post", "")
        # data-post 格式为 "频道用户名/消息编号"
        if not data_post or "/" not in data_post:
            continue

        try:
            msg_num = int(data_post.split("/")[-1])
        except Exception as e:
            print(f"解析消息编号失败: {e}")
            continue

        if msg_num <= last_id:
            continue

        # 查找消息中所有包含图片的 <a> 标签（支持组合图片）
        photo_tags = wrap.find_all("a", class_="tgme_widget_message_photo_wrap")
        image_urls = []
        for tag in photo_tags:
            style = tag.get("style", "")
            # 样式属性一般形如：background-image: url('https://example.com/xxx.jpg');
            match = re.search(r"url\('(.*?)'\)", style)
            if match:
                image_urls.append(match.group(1))
        
        if image_urls:
            new_images.append((msg_num, image_urls))
    
    # 按消息编号升序排列，保证发送顺序一致
    new_images.sort(key=lambda x: x[0])
    return new_images

async def main():
    bot = Bot(TOKEN)
    last_id = get_last_processed_id()
    print(f"启动程序，当前最后处理的消息编号为 {last_id}")

    while True:
        new_posts = fetch_new_images(last_id)
        if new_posts:
            for msg_num, image_urls in new_posts:
                try:
                    if len(image_urls) > 1:
                        media = [InputMediaPhoto(photo) for photo in image_urls]
                        await bot.send_media_group(chat_id=TARGET_CHANNEL, media=media)
                        print(f"已以相册形式发送消息 {msg_num} 的图片组合，共 {len(image_urls)} 张")
                    else:
                        await bot.send_photo(chat_id=TARGET_CHANNEL, photo=image_urls[0])
                        print(f"已发送消息 {msg_num} 的图片：{image_urls[0]}")
                except Exception as e:
                    print(f"发送消息 {msg_num} 时出错: {e}")
                last_id = msg_num
            set_last_processed_id(last_id)
        else:
            print("暂无新图片。")
        
        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == '__main__':
    asyncio.run(main())
