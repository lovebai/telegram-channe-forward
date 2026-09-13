# Telegram Channel Forwarder

通过 Bot 将多个公开 Telegram 源频道的多图相册、视频和混合媒体复制到一个目标频道。频道、Bot Token、代理及轮询参数均通过 JSON 配置，无需修改代码。

## 功能

- 多源频道：按配置顺序轮询，各频道独立保存进度。
- 代理：支持 HTTP、HTTPS、SOCKS5 和 SOCKS5h，同时用于公开网页抓取和 Bot API 请求。
- 媒体转发：支持多图、单视频和图片与视频混合相册。
- 单图过滤：源消息只有一张图片且没有视频时不转发。
- 失败重试：发送失败不推进该消息的进度，下轮重试，其他频道继续处理。

## 使用前准备

- 安装 Python 3.10 或更新版本。
- 准备 Bot Token，将 Bot 加入目标频道并授予发布消息权限。
- 源频道必须有可访问的公开预览页面，例如 `https://t.me/s/source_channel_a`。不支持私有频道或需要登录才能查看的媒体。

## 快速开始

在项目目录执行以下命令。建议使用虚拟环境，避免与其他项目的依赖冲突。

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# 仅首次创建配置；已有 config.json 时跳过复制
Copy-Item config.example.json config.json
```

编辑 `config.json`，填写真实的 Bot Token、源频道和目标频道，然后启动：

```powershell
.\.venv\Scripts\python.exe main.py
```

### Linux / macOS

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
# 仅首次创建配置；已有 config.json 时跳过复制
cp config.example.json config.json
# 编辑 config.json 后启动
.venv/bin/python main.py
```

按 `Ctrl+C` 停止程序。修改配置后需要重启才能生效。

## 配置说明

完整示例见 [config.example.json](config.example.json)：

```json
{
  "bot_token": "YOUR_BOT_TOKEN",
  "source_channels": ["source_channel_a", "source_channel_b"],
  "target_channel": "@target_channel",
  "proxy": null,
  "check_interval": 60,
  "request_timeout": 30,
  "state_file": "state.json"
}
```

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `bot_token` | 必填 | 替换为真实 Bot Token |
| `source_channels` | 必填 | 非空源频道用户名列表，可带 `@`，不能填写链接；忽略大小写并去重 |
| `target_channel` | 必填 | 目标频道 `@用户名`，或 JSON 数字形式的频道 ID，如 `-1001234567890` |
| `proxy` | `null` | 直连或代理 URL，见下方示例 |
| `check_interval` | `60` | 每轮处理完成后的等待秒数，必须大于 0 |
| `request_timeout` | `30` | 网页请求超时，以及 Bot API 的连接、读取超时秒数，必须大于 0 |
| `state_file` | `"state.json"` | 进度文件路径；相对路径以配置文件所在目录为基准 |

JSON 中的字符串使用双引号，不要添加注释或末尾多余的逗号。Windows 文件路径可以使用 `/`，或将反斜杠写成 `\\`。

程序默认读取 `main.py` 同目录下的 `config.json`，也可指定配置：

```powershell
.\.venv\Scripts\python.exe main.py --config C:/path/to/config.json
```

### 代理示例

将配置中的 `proxy` 设置为以下任意一种：

| 连接方式 | 配置值 |
| --- | --- |
| 直连 | `null` |
| HTTP 代理 | `"http://127.0.0.1:7890"` |
| HTTPS 代理 | `"https://proxy.example.com:8443"` |
| SOCKS5 代理 | `"socks5://127.0.0.1:1080"` |
| SOCKS5h 代理 | `"socks5h://127.0.0.1:1080"` |
| 带认证的代理 | `"http://username:password@127.0.0.1:7890"` |

填写代理服务实际监听的地址和端口。程序不读取系统代理环境变量；`null` 表示直连。`requirements.txt` 已包含 SOCKS 所需的可选依赖。

## 转发规则

| 源消息内容 | 处理方式 |
| --- | --- |
| 纯文字或无可识别媒体 | 跳过并记录进度 |
| 只有一张图片，没有视频 | 跳过并记录进度 |
| 两张或更多图片 | 发送图片相册 |
| 单个可获取链接的视频 | 发送视频 |
| 多个视频、图片与视频混合 | 发送媒体相册 |
| 检测到视频但没有任何可用视频链接 | 记录警告，整条消息跳过并记录进度 |

相册按每批最多 10 项拆分，最后一批若仅剩一项则单独发送。因此，多图消息拆分后可能出现单张图片发送，这不属于源单图消息。只复制媒体，不复制文字说明或原生转发来源标记。

## 进度与重试

进度文件以源频道用户名为键，保存最后处理的消息编号，例如：

```json
{
  "source_channel_a": 123,
  "source_channel_b": 456
}
```

- 每个频道按消息编号从小到大处理，处理成功或按规则跳过后保存进度。
- 网页请求失败时，下轮重新获取该频道；发送失败时，本轮停止处理该频道后续消息，继续其他频道。
- 没有进度或进度为 `0` 时，首次运行只处理近期预览页。有正整数进度时，使用 `?after=消息ID` 向后翻页，每轮每频道最多抓取 5 页，按编号升序处理；下一轮从已保存进度继续，直到追上最新消息。消息编号无需连续，已删除或不公开的消息无法恢复。
- 新进度文件不存在时，会读取配置目录下的旧 `last_id.txt`，将进度归到第一个源频道。旧版升级时请将原源频道放在列表第一项。
- 进度通过临时文件替换保存。网络响应丢失、发送后保存前退出、拆分相册部分失败，都可能导致重试时重复发送。
- 请勿让多个进程共用一个进度文件。需要重新处理时，先停止程序并备份进度，再调整对应频道的编号；这可能重新发送该编号之后的历史消息。

### 手动指定历史续传起点

先停止程序，再修改配置中 `state_file` 指向的文件，例如：

```json
{
  "botmzt": 22169
}
```

重启后从 **大于 22169** 的消息开始分页补发，不包含 22169 本身。若要包含该条，可设为 `22168`。相册在公开网页中以一条帖子呈现，可能包含多个消息编号；建议使用帖子链接中的编号作为续传边界。多个频道各自设置，不要删除其他频道需要保留的进度。程序运行期间修改不会立即生效，且可能被内存中的进度覆盖。

历史补发同样应用单图过滤和失败重试规则；每轮五页处理完后等待 `check_interval` 秒继续。公开页面不可访问或 Telegram 改变预览接口时，无法保证补齐历史。

## 视频支持范围

程序从公开网页中的 `<video>` 或 `<source>` 提取 HTTP(S) 视频链接，再通过 Bot 发送。遇到 `webpage_curl_failed` 等明确的远程链接抓取错误时，程序通过配置的代理下载当前批次媒体，并以文件上传方式重试；图片同样支持此回退。不登录 Telegram 账号；以普通文档附件发布且没有可解析视频标签的文件不在当前支持范围内。

能否成功发送取决于网页是否公开完整媒体链接、Telegram 是否能访问该链接，以及文件格式和大小是否被接受。公开预览可能只展示部分媒体，转发结果以实际解析到的内容为准。配置的代理用于本程序请求，不会改变 Telegram 服务端抓取视频链接的网络环境，但下载后上传的回退可以绕过服务端抓取失败。下载在内存中进行，本程序限制单张图片为 10 MiB、单个视频为 50 MiB；空响应、HTML 页面或超出限制时保留失败进度。权限错误和不确定是否发送成功的网络超时不会触发该回退。

## 常见问题

| 现象 | 检查方法 |
| --- | --- |
| 提示找不到 `config.json` | 从示例复制配置，或使用 `--config` 指定路径 |
| 提示填写 `bot_token` | 将示例占位符替换为真实 Token |
| Bot 启动或发送失败 | 检查 Token、目标频道标识、Bot 发布权限和网络连接；启动失败后需手动重新运行 |
| 获取频道失败 | 检查源频道用户名、公开预览页面和代理地址是否可用 |
| 提示缺少 SOCKS 依赖 | 使用运行程序的同一个 Python 执行 `-m pip install -r requirements.txt` |
| 视频没有转发 | 查看是否出现无公开下载链接的警告，或是否因发送失败等待重试 |
| 修改配置后没有变化 | 停止并重新启动程序 |
| 提示进度文件格式错误 | 停止程序，检查进度 JSON 是否为频道名到非负整数的映射 |

发送失败日志会显示异常类型、服务端具体原因及图片/视频数量，并隐藏 Token、代理地址和媒体 URL。仅有 `BadRequest` 无法判断根因；应结合冒号后的原因排查：`Chat not found` 检查目标频道与 Bot 是否已加入，`not enough rights` 检查发布权限，`Failed to get HTTP URL content` 检查媒体链接是否能被 Telegram 获取。失败消息保留进度，不会自动跳过。

## 项目文件

| 文件 | 用途 |
| --- | --- |
| [main.py](main.py) | 配置加载、网页解析、媒体发送及轮询 |
| [config.example.json](config.example.json) | 可提交的配置模板 |
| `config.json` | 本地真实配置，已排除 Git |
| `state.json` | 默认进度文件，已排除 Git |
| [requirements.txt](requirements.txt) | 运行依赖及 SOCKS 支持 |
| [tests/test_main.py](tests/test_main.py) | 解析、过滤、相册拆分、进度及失败隔离测试 |

自定义真实配置或进度文件名时，也应将其加入 `.gitignore`，避免提交 Token、代理密码和运行状态。

## 测试

Windows：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Linux / macOS：

```sh
.venv/bin/python -m unittest discover -s tests -v
```

测试通过模拟请求和 Bot 调用验证逻辑，不会向真实频道发送消息，也不能替代真实网络和频道权限验证。
