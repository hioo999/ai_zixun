# AI News Daily Bot

每天自动搜索 AI 行业资讯，用 DeepSeek 大模型挑选 5 条最有价值的内容，生成结构化 Markdown 报告并提交到 GitHub 仓库。

## 工作原理

1. 从 [AI HOT](https://aihot.virxact.com) API 拉取过去 24 小时的精选 AI 新闻
2. 调用 DeepSeek API 从中挑选 5 条最有价值的资讯，撰写标题、摘要和启示
3. 保存为 `ai_news_YYYY-MM-DD.md` 文件并自动 commit 到仓库
4. （可选）通过 Webhook 推送到微信/钉钉等

## 部署步骤

### 1. 创建 GitHub 仓库

在 GitHub 上新建一个仓库（public 或 private 均可），将本项目代码推上去：

```bash
cd ai-news-bot
git init
git add .
git commit -m "init: AI news daily bot"
git branch -M main
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main
```

### 2. 配置 API Key Secret

进入仓库的 **Settings → Secrets and variables → Actions → New repository secret**：

| Name | Value | 必填 |
|------|-------|------|
| `DEEPSEEK_API_KEY` | 你的 DeepSeek API Key（`sk-...`） | 是 |
| `WEBHOOK_URL` | 推送 webhook 地址（Server酱/PushPlus等） | 否 |

### 3. 手动测试

进入仓库的 **Actions** 页面，选择 "Daily AI News" workflow，点击 **Run workflow** 手动触发一次，确认能正常运行并生成报告文件。

### 4. 自动运行

workflow 默认每天北京时间 9:00 自动运行。如需修改时间，编辑 `.github/workflows/daily-ai-news.yml` 中的 cron 表达式：

```yaml
# 格式: 分 时 日 月 周 (UTC时间)
# 北京时间 9:00 AM = UTC 1:00 AM
- cron: '0 1 * * *'
```

常用时区换算：
- 北京 8:00 → `0 0 * * *`
- 北京 9:00 → `0 1 * * *`
- 北京 14:00 → `0 6 * * *`
- 北京 20:00 → `0 12 * * *`

## 查看结果

- 报告文件会自动 commit 到仓库根目录，格式为 `ai_news_YYYY-MM-DD.md`
- 也可以在 Actions 运行日志中查看完整输出
- 如果配置了 `WEBHOOK_URL`，报告会同时推送到指定地址

## 自定义

- **修改新闻来源**：编辑 `generate_ai_news.py` 中的 `fetch_ai_hot_news()` 函数
- **修改模型**：设置环境变量 `DEEPSEEK_MODEL`（默认 `deepseek-chat`）
- **修改输出格式**：编辑 `synthesize_with_deepseek()` 中的 system prompt
- **修改选取数量**：修改 prompt 中的"挑选5条"

## 费用

DeepSeek V4 Flash 价格极低（缓存命中 0.2 元/百万 Token），每天跑一次成本约 1-3 分钱。
