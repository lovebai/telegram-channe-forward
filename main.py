#!/usr/bin/env python3
"""从多个公开频道转发多图和视频。"""
import argparse
import asyncio
import json
import logging
import re
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from telegram import Bot, InputMediaPhoto, InputMediaVideo
from telegram.request import HTTPXRequest

LOG = logging.getLogger(__name__)


def load_config(path):
    path = Path(path).resolve()
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    token = config.get("bot_token")
    if not isinstance(token, str) or not token.strip() or token == "YOUR_BOT_TOKEN":
        raise ValueError("请在配置文件中填写 bot_token")
    target = config.get("target_channel")
    if type(target) not in (str, int) or not target:
        raise ValueError("target_channel 必须是 @频道用户名或数字频道 ID")
    sources = config.get("source_channels")
    if not isinstance(sources, list) or not sources:
        raise ValueError("source_channels 必须是非空频道列表")
    channels = []
    for source in sources:
        if not isinstance(source, str) or not re.fullmatch(r"@?[A-Za-z0-9_]+", source):
            raise ValueError("源频道请填写用户名，不要填写链接")
        source = source.lstrip("@").lower()
        if source not in channels:
            channels.append(source)
    config["source_channels"] = channels
    for key, default in (("check_interval", 60), ("request_timeout", 30)):
        value = config.setdefault(key, default)
        if type(value) not in (int, float) or not 0 < value < float("inf"):
            raise ValueError(f"{key} 必须是正数")
    proxy = config.setdefault("proxy", None)
    if proxy is not None:
        if not isinstance(proxy, str):
            raise ValueError("proxy 必须是代理 URL 或 null")
        parsed = urlparse(proxy)
        if parsed.scheme not in ("http", "https", "socks5", "socks5h") or not parsed.hostname:
            raise ValueError("proxy 必须是 HTTP、HTTPS 或 SOCKS5 代理 URL")
    config["state_file"] = path.parent / config.get("state_file", "state.json")
    return config


def load_state(path, sources):
    if path.exists():
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state, dict) or any(type(v) is not int or v < 0 for v in state.values()):
            raise ValueError("进度文件格式错误")
        return state
    legacy = path.parent / "last_id.txt"
    return {sources[0]: int(legacy.read_text().strip())} if legacy.exists() else {}


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temporary.replace(path)


def parse_posts(html, channel, last_id):
    posts = {}
    for message in BeautifulSoup(html, "html.parser").select(".tgme_widget_message[data-post]"):
        source, _, number = message.get("data-post", "").rpartition("/")
        if source.lower() != channel.lower() or not number.isdigit() or int(number) <= last_id:
            continue
        media = []
        for tag in message.select("a.tgme_widget_message_photo_wrap, video"):
            if tag.name == "video":
                child = tag.find("source", src=True)
                url = tag.get("src") or (child.get("src") if child else None)
                kind = "video"
            else:
                match = re.search(r"url\(\s*['\"]?(.*?)['\"]?\s*\)", tag.get("style", ""))
                url = match.group(1) if match else None
                kind = "photo"
            if url and url.startswith(("https://", "http://")) and (kind, url) not in media:
                media.append((kind, url))
        unavailable = bool(message.select(".tgme_widget_message_video_player, video")) and not any(k == "video" for k, _ in media)
        posts[int(number)] = (media, unavailable)
    return [(number, *posts[number]) for number in sorted(posts)]


def fetch_posts(session, channel, last_id, timeout):
    response = session.get(f"https://t.me/s/{channel}", timeout=timeout)
    response.raise_for_status()
    return parse_posts(response.text, channel, last_id)


async def send_post(bot, target, media):
    if not media or (len(media) == 1 and media[0][0] == "photo"):
        return
    for offset in range(0, len(media), 10):
        chunk = media[offset:offset + 10]
        if len(chunk) == 1:
            kind, url = chunk[0]
            if kind == "video":
                await bot.send_video(chat_id=target, video=url, supports_streaming=True)
            else:
                await bot.send_photo(chat_id=target, photo=url)
        else:
            items = [InputMediaVideo(url, supports_streaming=True) if kind == "video" else InputMediaPhoto(url) for kind, url in chunk]
            await bot.send_media_group(chat_id=target, media=items)


async def poll_once(bot, session, config, state):
    for channel in config["source_channels"]:
        try:
            posts = await asyncio.to_thread(fetch_posts, session, channel, state.get(channel, 0), config["request_timeout"])
        except requests.RequestException as exc:
            LOG.warning("获取频道 %s 失败（%s），下轮重试", channel, type(exc).__name__)
            continue
        for number, media, unavailable in posts:
            if unavailable:
                LOG.warning("%s/%s 视频无公开下载链接，跳过", channel, number)
            else:
                try:
                    await send_post(bot, config["target_channel"], media)
                except Exception as exc:
                    LOG.warning("发送 %s/%s 失败（%s），下轮重试", channel, number, type(exc).__name__)
                    break
            state[channel] = number
            save_state(config["state_file"], state)
            LOG.info("已处理 %s/%s", channel, number)


async def main(config_path):
    config = load_config(config_path)
    state = load_state(config["state_file"], config["source_channels"])
    request = HTTPXRequest(proxy=config["proxy"], read_timeout=config["request_timeout"],
                           connect_timeout=config["request_timeout"], httpx_kwargs={"trust_env": False})
    with requests.Session() as session:
        session.trust_env = False
        if config["proxy"]:
            session.proxies.update({"http": config["proxy"], "https": config["proxy"]})
        async with Bot(config["bot_token"], request=request) as bot:
            LOG.info("开始监控 %s", ", ".join(config["source_channels"]))
            while True:
                await poll_once(bot, session, config, state)
                await asyncio.sleep(config["check_interval"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        asyncio.run(main(args.config))
    except KeyboardInterrupt:
        LOG.info("程序已停止")
