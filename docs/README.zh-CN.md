# WXBridge 使用说明

WXBridge 是供 CCM、Codex 和本地用户调用的 Windows **只读微信数据库查询工具**。当前默认读取方式为 `cached-key`：缓存的是经过 Windows DPAPI 保护的数据库解密密钥，**不是聊天记录**。每次查询直接读取微信电脑端已保存的本地数据库；不保证能取得微信服务器上尚未同步的新消息。

无参数运行只展示帮助，不检测密钥和消息是否可读。调用方应直接执行查询，成功时处理结果，失败时根据具体错误判断。不需要为了跨工作区读取微信，先进入 WXBridge 开发工作区；CCM 的连接错误也不等于沙箱授权请求。

## 调用示例

```powershell
& "C:\path\to\WXBridge\WXBridge.exe"
& "C:\path\to\WXBridge\WXBridge.exe" sessions --limit 20
& "C:\path\to\WXBridge\WXBridge.exe" contacts --keyword "示例"
& "C:\path\to\WXBridge\WXBridge.exe" messages --chat "example_wxid" --limit 20
& "C:\path\to\WXBridge\WXBridge.exe" articles --chat "gh_example" --limit 20
& "C:\path\to\WXBridge\WXBridge.exe" media-read --chat "example_wxid" --message-id "message__message_3.db:602"
```

EXE 必须与 `_wxbridge_runtime` 目录放在一起。另有 `snapshot` 模式，可读取用户事先准备的离线明文 SQLite 副本，但不会自动解密原始数据库。

`media-read` 仅定位已下载的**文件附件**，在原目录内核对大小、MD5；不负责下载文件或解析 PDF。 `media-status` 只检查本地图片、语音缓存的可用性。 `articles` 只解析链接、标题、摘要等元数据，不抓取外部网页正文。

WXBridge 不提供发消息、修改联系人、点赞评论、微信界面自动化或自动下载能力；不会在常规读取时扫描微信进程内存来获取新密钥。更多技术细节见 [README](../README.md)、[安全说明](../SECURITY.md)、[EXE 构建](EXE_BUILD.md)。
