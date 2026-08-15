# telegram-clone-bot

Telegram 频道克隆机器人，支持多账号、媒体组、过滤规则及代理配置。

## 📞 联系方式

- 联系客服：https://t.me/vvvvvcp
- 官方电报频道：https://t.me/btbcc

---

## 一、环境要求

- 操作系统：Linux (Ubuntu/Debian 推荐)
- Python：3.10 或更高版本
- PostgreSQL：12 或更高版本
- Redis：5 或更高版本
- Telegram 账号：至少一个用于克隆的普通用户账号（需要 API ID / API Hash）
- 服务器：能够稳定访问 Telegram 网络

---

## 二、克隆代码并安装依赖

### 1. 获取代码

```bash
cd /www/wwwroot
git clone <your-repo-url> collector
cd collector
```

### 2. 创建 Python 虚拟环境

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

如果没有 requirements.txt，请手动安装：

```bash
pip install telethon asyncpg redis fastapi uvicorn jinja2 python-socks
```

---

## 三、安装并配置 PostgreSQL

### 1. 安装 PostgreSQL

```bash
apt update
apt install postgresql postgresql-contrib
```

### 2. 创建数据库和用户

```bash
sudo -u postgres psql
```

在 psql 中执行：

```sql
CREATE DATABASE clonebot;
CREATE USER cloneuser WITH PASSWORD 'your_strong_password';
GRANT ALL PRIVILEGES ON DATABASE clonebot TO cloneuser;
```

### 3. 初始化表结构

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE,
    username TEXT,
    balance NUMERIC DEFAULT 0,
    is_vip BOOLEAN DEFAULT FALSE,
    is_blocked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE tg_accounts (
    id SERIAL PRIMARY KEY,
    phone TEXT,
    username TEXT,
    api_id INTEGER,
    api_hash TEXT,
    status TEXT DEFAULT 'pending',
    is_assigned BOOLEAN DEFAULT FALSE,
    assigned_task_id INTEGER,
    proxy_type TEXT,
    proxy_host TEXT,
    proxy_port INTEGER,
    proxy_username TEXT,
    proxy_password TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE clone_tasks (
    id SERIAL PRIMARY KEY,
    user_telegram_id BIGINT,
    account_id INTEGER,
    source_channel TEXT,
    target_channel TEXT,
    task_type TEXT DEFAULT 'full',
    status TEXT DEFAULT 'checking',
    max_posts INTEGER DEFAULT 0,
    cloned INTEGER DEFAULT 0,
    skipped INTEGER DEFAULT 0,
    last_processed_msg_id BIGINT,
    start_msg_id BIGINT,
    error_msg TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    finished_at TIMESTAMP
);

CREATE TABLE cloned_posts (
    id SERIAL PRIMARY KEY,
    task_id INTEGER,
    source_msg_id BIGINT,
    target_msg_id BIGINT,
    cloned_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(task_id, source_msg_id)
);

CREATE TABLE user_states (
    telegram_id BIGINT PRIMARY KEY,
    mode TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE user_selected_account (
    telegram_id BIGINT PRIMARY KEY,
    account_id INTEGER
);

CREATE TABLE user_selected_backup (
    telegram_id BIGINT PRIMARY KEY,
    backup_account_id INTEGER
);

CREATE TABLE user_selected_backup_multi (
    telegram_id BIGINT PRIMARY KEY,
    backup_account_ids JSONB
);

CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

---

## 四、安装并启动 Redis

```bash
apt install redis-server
systemctl enable redis-server
systemctl start redis-server
```

---

## 五、配置文件设置

在项目根目录创建 `.env` 文件：

```env
BOT_TOKEN=123456789:ABCdef...
ADMIN_USER_ID=6212164114

PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=cloner
PG_USER=cloner
PG_PASSWORD=your_strong_password

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
```

---

## 六、配置 Telegram 账号

1. 启动后访问后台管理页面。
2. 在"账号管理"中添加账号，填写手机号、API ID、API Hash。
3. 按提示输入验证码完成登录。
4. 登录成功后状态显示为 `connected`，即可使用。

---

## 七、启动克隆系统

### 1. 启动主进程

```bash
cd /www/wwwroot/collector
source venv/bin/activate
python3 start.py
```

后台运行：

```bash
nohup python3 start.py > bot.log 2>&1 &
```

### 2. 访问后台管理

默认地址：http://your_server_ip:8000

---

## 八、常见配置项说明

| 配置项 | 作用 |
|---|---|
| BOT_TOKEN | 机器人令牌，从 @BotFather 获取 |
| API_ID / API_HASH | 用于登录用户账号（克隆账号） |
| STORAGE_CHANNEL_ID | 存储频道的 ID，用于临时保存采集内容或中转 |
| ADMIN_ID | 管理员 Telegram ID，用于接收通知和管理 |
| DATABASE_URL | PostgreSQL 连接字符串 |
| SESSION_DIR | 存放用户账号 session 文件的目录 |
| REDIS_HOST / REDIS_PORT | Redis 连接信息，用于任务队列 |

---

## 九、启动后必做事项

1. 添加至少一个克隆账号并登录。
2. 在"价格管理"中设置套餐价格。
3. 在"广告过滤设置"中配置链接/用户名/关键词过滤。
4. 从 Telegram 私聊 Bot，点击"创建任务"进行测试。

---

## 十、注意事项

- 请确保服务器网络能稳定连接 Telegram。
- 建议为每个克隆账号配置独立代理，避免 IP 限速。
- 定期备份数据库和 `sessions/` 目录。

---

## 📞 技术支持

- Telegram: @vvvvvcp
- 官方频道: @btbcc
