# Telegram Channel Forwarder

从多个公开 Telegram 频道复制多图相册、视频及混合媒体到一个目标频道。需要 Python 3.10+。

## 安装与运行

```powershell
python -m pip install -r requirements.txt
Copy-Item config.example.json config.json
# 编辑 config.json 后启动
python main.py
# 自定义配置路径
python main.py --config C:/path/to/config.json
```

Bot 需要目标频道的发消息权限。源频道必须有可访问的公开预览页面 `https://t.me/s/频道名`。

## 配置文件

配置修改后重启程序生效。

| 字段 | 说明 |
| --- | --- |
| bot_token | BotFather 提供的 Bot Token |
| source_channels | 源频道用户名列表，可带 @，不填写链接；重复名称自动合并 |
| target_channel | 目标频道 @用户名或数字 ID，例如 -1001234567890 |
| proxy | null 为直连，或 http://127.0.0.1:7890、socks5://127.0.0.1:1080；支持代理账号密码 |
| check_interval | 轮询间隔秒数，默认 60 |
| request_timeout | 请求超时秒数，默认 30 |
| state_file | 每个源频道的进度文件，相对路径以配置文件目录为基准 |

代理同时用于频道网页请求和 Bot API 请求，不读取系统代理环境变量。真实配置 config.json 和默认进度文件已排除 Git；config.example.json 只放示例。自定义配置或进度文件路径时，请将其加入 .gitignore。

## 转发规则与限制

- 仅一张图片且没有视频的消息跳过；纯文字消息也跳过，并保存进度。
- 多图发送为相册，单视频直接发送，图片和视频混合发送为相册；每批最多 10 项，超过时拆分。
- 发送失败时不跨过失败消息，下轮重试，其他源频道继续处理。
- 首次运行处理公开预览页面当前可见消息，不回溯完整历史。长时间离线或消息更新过快，超出预览窗口的消息可能遗漏。
- 视频必须在公开网页中提供 HTTP(S) 视频地址；未提供地址的视频记录警告并跳过。不支持私有频道。视频能否发送还取决于 Telegram 是否能抓取该地址及文件格式、大小限制。
- 沿用原脚本的媒体复制行为，不复制文字说明和原生转发来源标记。
- 每条处理后原子保存进度。发送后未落盘即退出、网络响应丢失或拆分相册部分失败，重试可能重复发送，不保证严格只发送一次。
- 新进度文件不存在时，旧 last_id.txt 迁移到配置中的第一个源频道，请将原源频道放在第一项。

代理接口参考 [HTTPXRequest 文档](https://docs.python-telegram-bot.org/en/latest/telegram.request.httpxrequest.html)，媒体规则参考 [Telegram Bot API](https://core.telegram.org/bots/api)。

## 测试

```powershell
python -m unittest discover -s tests -v
```
