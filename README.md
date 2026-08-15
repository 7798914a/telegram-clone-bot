# telegram-clone-bot
Telegram 频道克隆机器人，支持多账号、媒体组、过滤规则及代理配置。

联系方式  https://t.me/vvvvvcp
官方电报频道 https://t.me/btbcc

<img width="1170" height="1311" alt="8f518dbe569598b26e94b0179980c370" src="https://github.com/user-attachments/assets/5dd2a004-4abf-4ab3-ab43-6aa97c79712d" />
<img width="1170" height="1311" alt="8f518dbe569598b26e94b0179980c370" src="https://github.com/user-attachments/assets/3fd02258-aefd-4a8e-93a4-71caa8cc5aad" />
一、环境要求
操作系统：Linux (Ubuntu/Debian 推荐)

Python：3.10 或更高版本

PostgreSQL：12 或更高版本

Redis：5 或更高版本

Telegram 账号：至少一个用于克隆的普通用户账号（需要 API ID / API Hash）

服务器：能够稳定访问 Telegram 网络

二、克隆代码并安装依赖
1. 获取代码
将您的克隆系统代码上传到服务器目录，例如 /www/wwwroot/collector。
如果使用 Git，可执行：

bash
cd /www/wwwroot
git clone <your-repo-url> collector
cd collector
2. 创建 Python 虚拟环境（推荐）
bash
python3 -m venv venv
source venv/bin/activate
3. 安装 Python 依赖
bash
pip install -r requirements.txt
如果没有 requirements.txt，请手动安装常用依赖：

bash
pip install telethon asyncpg redis fastapi uvicorn jinja2 python-socks
三、安装并配置 PostgreSQL
1. 安装 PostgreSQL
bash
apt update
apt install postgresql postgresql-contrib
2. 创建数据库和用户
bash
sudo -u postgres psql
在 psql 中执行：

sql
CREATE DATABASE clonebot;
CREATE USER cloneuser WITH PASSWORD 'your_strong_password';
GRANT ALL PRIVILEGES ON DATABASE clonebot TO cloneuser;
3. 初始化表结构
您需要将数据库迁移 SQL 导入到 clonebot 数据库。如果项目中有 schema.sql 或迁移脚本，请执行；如果没有，请使用我们之前提供的 clone_tasks 表结构。
一个最小化的表结构示例（请根据实际调整）：

sql
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
您可以根据实际代码中的模型定义进行调整。

四、安装并启动 Redis
bash
apt install redis-server
systemctl enable redis-server
systemctl start redis-server
五、配置文件设置
在项目根目录下创建或编辑 config.py，以下为必填配置项：

python
# Telegram Bot Token
BOT_TOKEN = "123456789:ABCdef..."

# API ID 和 API Hash（从 my.telegram.org 获取）
API_ID = 38835328
API_HASH = "814822151f2b158e015906d1f2c99e73"

# 存储频道 ID（用于保存采集结果，如果有）
STORAGE_CHANNEL_ID = -1001234567890

# 管理员 Telegram ID
ADMIN_ID = 123456789

# 会话文件存储目录
SESSION_DIR = "sessions"

# 数据库连接字符串（PostgreSQL）
DATABASE_URL = "postgresql://cloneuser:your_strong_password@localhost:5432/clonebot"

# Redis 连接
REDIS_HOST = "localhost"
REDIS_PORT = 6379
如果您使用环境变量，可将上述配置改为从环境变量读取。

六、配置 Telegram 账号（克隆用账号）
在后台管理页面（启动后）添加 tg_accounts，填写手机号、API ID、API Hash。

系统会通过 Telegram 发送验证码，请按提示完成登录。

账号登录成功后，状态变为 connected，即可用于克隆任务。

七、启动克隆系统
1. 启动主进程
bash
cd /www/wwwroot/collector
source venv/bin/activate
python3 start.py
如果希望后台运行：

bash
nohup python3 start.py > bot.log 2>&1 &
2. 访问后台管理
默认后台地址：http://your_server_ip:8000
使用您在数据库中设置的管理员账号登录（默认用户名：admin，密码：admin123，请务必修改）。

八、常见配置选项说明
配置项	作用
BOT_TOKEN	机器人令牌，从 @BotFather 获取
API_ID / API_HASH	用于登录用户账号（克隆账号）
STORAGE_CHANNEL_ID	存储频道的 ID，用于临时保存采集内容或中转
ADMIN_ID	管理员 Telegram ID，用于接收通知和管理
DATABASE_URL	PostgreSQL 连接字符串
SESSION_DIR	存放用户账号 session 文件的目录
REDIS_HOST / REDIS_PORT	Redis 连接信息，用于任务队列
九、系统启动后需要完成的事项
添加克隆账号：在后台“账号管理”中添加至少一个 Telegram 账号并登录成功。

添加价格套餐：在后台“价格管理”中设置普通、双账号、删除帖子等价格。

配置过滤设置：在后台“广告过滤设置”中配置链接/用户名/关键词过滤。

测试克隆：从 Telegram 私聊 Bot，点击“创建任务”，按提示操作。

十、注意事项
请确保服务器网络能稳定连接 Telegram（可能需要使用代理）。

建议为每个克隆账号配置独立代理，避免 IP 限速。

定期备份 PostgreSQL 数据库。

如果遇到限速（FloodWaitError），请降低任务频率或增加账号
