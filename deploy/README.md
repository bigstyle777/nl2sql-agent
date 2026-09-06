# 部署指南

## 方案一：Hugging Face Space（免费，推荐先跑通）

1. 注册/登录 Hugging Face，新建 Space：
   - SDK 选 **Streamlit**，App file 填 `src/ui/app.py`，硬件选免费 CPU
2. 把本仓库推送到 Space 远程：
   ```bash
   git remote add space https://huggingface.co/spaces/<你的用户名>/nl2sql-agent
   git push space main --force
   ```
3. 配置 Secrets（Space 页面 → Settings → Variables and secrets）：
   - `LLM_PROVIDER` = `deepseek`
   - `LLM_API_KEY` = 你的 Key
   - `DEMO_SCALE` = `0.3`（免费 CPU 建库更快；想要全量数据可去掉）
   - 可选：`LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`（开启调用追踪）
4. 首次启动会自动生成业务库（`DEMO_SCALE=0.3` 约 30 秒），无需上传数据库文件。

> 常见问题：Space 的 README.md 必须带 SDK 元信息。网页创建 Space 时会自动生成
> frontmatter，推送覆盖后若启动报错，把下面三行补到 README.md 开头即可：
>
> ```
> ---
> sdk: streamlit
> app_file: src/ui/app.py
> ---
> ```

## 方案二：国内云服务器（访问快，适合给国内面试官演示）

```bash
# 服务器上（Python 3.11）
git clone https://github.com/bigstyle777/nl2sql-agent.git
cd nl2sql-agent
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python data/generator.py            # 生成业务库
cp .env.example .env                # 填入 API Key

# 前台试跑
streamlit run src/ui/app.py --server.port 8501

# 常驻运行（nohup 或 systemd）
nohup streamlit run src/ui/app.py --server.port 8501 --server.address 0.0.0.0 &
```

安全提示：公网部署务必加访问控制（Nginx Basic Auth 或安全组白名单），
否则你的 API Key 会被陌生人消耗。
