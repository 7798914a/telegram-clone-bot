import os
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

# =====================================================
# Telegram Bot 配置
# =====================================================
# Bot Token，从 @BotFather 获取
BOT_TOKEN = os.getenv("BOT_TOKEN")

# 管理员 Telegram 数字 ID（例如 6212164114）
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))

# =====================================================
# 支付配置（可选，若启用支付功能请填写）
# =====================================================
OKPAY_APP_ID = ""          # 支付平台 App ID
OKPAY_TOKEN = ""           # 支付平台 Token
OKPAY_API_URL = "https://api.okaypay.me/shop"
OKPAY_CALLBACK_URL = None  # 启动时自动设置，无需手动填写

# =====================================================
# Redis 配置
# =====================================================
REDIS_CONFIG = {
    "host": os.getenv("REDIS_HOST", "localhost"),
    "port": int(os.getenv("REDIS_PORT", "6379")),
    "db": int(os.getenv("REDIS_DB", "0")),
}

# =====================================================
# PostgreSQL 配置
# =====================================================
PG_CONFIG = {
    "host": os.getenv("PG_HOST", "localhost"),
    "port": int(os.getenv("PG_PORT", "5432")),
    "database": os.getenv("PG_DATABASE", "cloner"),
    "user": os.getenv("PG_USER", "cloner"),
    "password": os.getenv("PG_PASSWORD", ""),   # 必填，数据库密码
}

# =====================================================
# 路径配置
# =====================================================
# 当前目录
COLLECTOR_DIR = os.path.dirname(os.path.abspath(__file__))

# 账号 session 文件存放目录，自动创建
SESSION_DIR = os.path.join(COLLECTOR_DIR, "sessions")
os.makedirs(SESSION_DIR, exist_ok=True)

# =====================================================
# 技术支持
# =====================================================
# 如有部署问题，请联系 Telegram: @vvvvvcp