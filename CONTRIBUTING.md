# Contributing

WXBridge aims to be a small, portable, read-only local adapter—not a second implementation of the entire WeChat client.

1. Use Python 3.11+ and run `python -m unittest discover -s tests -v`.
2. Include tests with synthetic messages; **never** commit personal chats, credentials, database files, or real usernames.
3. Keep queries read-only, limit results and maintain explicit provenance and history-coverage labels.
4. No GUI clicking, sending, deletion, injection, key extraction, or scraping the user's complete social graph in a pull request without explicit project discussion.
5. Document compatibility against the exact WeChat and provider versions actually tested. Do not claim a version works without evidence.
6. Keep README and PLAN accurate as changes land; cite upstream project licenses when incorporating code.

This is an independent project and is not affiliated with WeChat/Tencent.
