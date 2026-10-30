# WXBridge 使用说明

WXBridge 是严格只读的微信本地数据访问工具。仅在 6v 部署一个公开的
`WXBridge.exe`，两台 Windows 机器分别运行同样的 Python HTTP API。
noha 不需要 EXE。旧版 WXBridge CLI 已删除，**上游 CLI 未修改**。

## 四个命令

```powershell
WXBridge.exe                                  # 无参数显示帮助
WXBridge.exe chats                            # 最近 20 个聊天
WXBridge.exe chats --keyword "狂人"           # 查人或群
WXBridge.exe messages --chat "狂人"           # 最近 30 条消息
WXBridge.exe messages --chat "狂人" --keyword "论文"
WXBridge.exe files --chat "狂人"              # 最近 20 个附件元数据
WXBridge.exe files --chat "狂人" --id "message__message_3.db:602"
WXBridge.exe moments                          # 最近 20 条朋友圈
WXBridge.exe moments --interactions           # 朋友圈互动
WXBridge.exe --account work chats             # 指定账号（可配置别名）
```

不会自动下载文件；`files --id` 返回已下载文件的本机路径，交给 CCM
在返回的 `environment_id` 对应的电脑上读取。`chats`、`messages`、
`files`、`moments` 的 `--limit` 都有默认值，并可用 `--offset` 继续查找。
按昵称查找优先精确匹配；只有模糊搜索结果唯一时才自动解析，重名或多结果会报错。

## 账号和机器

EXE 会联系两端 API 取得账号候选信息，自动选择目标环境，不提供
`--node`、`--env` 或 `--environment` 参数。默认账号及别名可写在
6v 的 `.state/accounts.json` 中，格式见根目录 README。

重要限制：依据微信进程、本机 DPAPI 缓存所属账号、只读窗口大小识别
主窗口/扫码登录窗口，推断“候选账号”，并**不能严格证明微信已登录**。
登录状态只有 `online` 和 `offline`：没有主窗口的明确证据（包括登录页、隐藏窗口、状态含糊）一律判为 `offline`，不会再返回 `unknown`。API 不可达作为通信错误单独处理；另一台机器已明确在线时允许继续路由，两台都明确在线则报冲突。输出仍会标记
`loginVerified:false`。两端都确认同一账号在线时直接报冲突；仅一端确认在线时可以使用该端，另一端 API 不可达也不再直接阻断查询。

配置、部署与安全说明见 [REMOTE_API.md](REMOTE_API.md)、
[EXE_BUILD.md](EXE_BUILD.md) 和根目录 [README.md](../README.md)。
