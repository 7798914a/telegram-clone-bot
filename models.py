import asyncpg
import asyncio
from config import PG_CONFIG

_pool = None
_lock = None

async def get_pool():
    global _pool, _lock
    if _lock is None:
        _lock = asyncio.Lock()
    async with _lock:
        if _pool is None:
            _pool = await asyncpg.create_pool(**PG_CONFIG, min_size=5, max_size=50)
    return _pool

async def init_db():
    """初始化所有表"""
    p = await get_pool()
    async with p.acquire() as conn:
        await conn.execute("""
            -- 账号池
            CREATE TABLE IF NOT EXISTS tg_accounts (
                id SERIAL PRIMARY KEY,
                phone TEXT NOT NULL,
                api_id INTEGER NOT NULL,
                api_hash TEXT NOT NULL,
                session_file TEXT,
                status TEXT DEFAULT 'pending',
                is_assigned BOOLEAN DEFAULT FALSE,
                assigned_task_id INTEGER,
                created_at TIMESTAMP DEFAULT NOW()
            );

            -- 克隆任务
            CREATE TABLE IF NOT EXISTS clone_tasks (
                id SERIAL PRIMARY KEY,
                user_telegram_id BIGINT,
                account_id INTEGER,
                source_channel TEXT NOT NULL,
                target_channel TEXT NOT NULL,
                start_msg_id BIGINT,
                max_posts INTEGER DEFAULT 0,
                prefix_text TEXT DEFAULT '',
                suffix_text TEXT DEFAULT '',
                task_type TEXT DEFAULT 'full',
                cloned INTEGER DEFAULT 0,
                skipped INTEGER DEFAULT 0,
                status TEXT DEFAULT 'queued',
                error_msg TEXT,
                last_processed_msg_id BIGINT DEFAULT 0,
                account_ids INTEGER[] DEFAULT '{}',
                current_account_index INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                finished_at TIMESTAMP
            );

            -- 已克隆帖子去重（带唯一约束）
            CREATE TABLE IF NOT EXISTS cloned_posts (
                id SERIAL PRIMARY KEY,
                task_id INTEGER,
                source_msg_id BIGINT NOT NULL,
                target_msg_id BIGINT,
                error TEXT,
                cloned_at TIMESTAMP DEFAULT NOW()
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_cloned_posts_unique ON cloned_posts(task_id, source_msg_id);
            CREATE INDEX IF NOT EXISTS idx_cloned_posts_task ON cloned_posts(task_id);

            -- 错误日志
            CREATE TABLE IF NOT EXISTS clone_errors (
                id SERIAL PRIMARY KEY,
                task_id INTEGER,
                msg_id BIGINT,
                error_type TEXT,
                error_msg TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );

            -- 管理员会话
            CREATE TABLE IF NOT EXISTS admin_sessions (
                id SERIAL PRIMARY KEY,
                token TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                expires_at TIMESTAMP NOT NULL
            );

            -- 用户
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE,
                username TEXT,
                is_vip BOOLEAN DEFAULT FALSE,
                vip_expires_at TIMESTAMP,
                balance DECIMAL(10,2) DEFAULT 0,
                account_mode VARCHAR(20) DEFAULT 'single',
                created_at TIMESTAMP DEFAULT NOW()
            );

            -- 充值
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT,
                amount DECIMAL(10,2),
                amount_cny DECIMAL(10,2),
                status TEXT DEFAULT 'pending',
                note TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                approved_at TIMESTAMP
            );

            -- 价格
            CREATE TABLE IF NOT EXISTS prices (
                id SERIAL PRIMARY KEY,
                type TEXT UNIQUE,
                price DECIMAL(10,2) DEFAULT 0,
                updated_at TIMESTAMP DEFAULT NOW()
            );
            INSERT INTO prices (type, price) VALUES 
                ('full', 5), 
                ('dual', 8),
                ('from_link', 3), 
                ('by_count', 0),
                ('monitor', 0)
            ON CONFLICT (type) DO NOTHING;

            -- 系统设置
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            INSERT INTO settings (key, value) VALUES 
                ('support_link', 'https://t.me/your_support'),
                ('filter_ads', '0'),
                ('filter_buttons', '0'),
                ('filter_links', '0'),
                ('filter_mentions', '0'),
                ('ad_keywords', '广告,赞助,合作,推广'),
                ('max_mentions', '3')
            ON CONFLICT (key) DO NOTHING;

            -- 用户状态
            CREATE TABLE IF NOT EXISTS user_states (
                telegram_id BIGINT PRIMARY KEY,
                mode TEXT,
                updated_at TIMESTAMP DEFAULT NOW()
            );

            -- 用户选择账号
            CREATE TABLE IF NOT EXISTS user_selected_account (
                telegram_id BIGINT PRIMARY KEY,
                account_id INTEGER,
                updated_at TIMESTAMP DEFAULT NOW()
            );

            -- 后台操作日志
            CREATE TABLE IF NOT EXISTS admin_logs (
                id SERIAL PRIMARY KEY,
                action TEXT,
                detail TEXT,
                operator TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );

            -- 删除记录
            CREATE TABLE IF NOT EXISTS deleted_posts (
                id SERIAL PRIMARY KEY,
                channel_id TEXT,
                msg_id BIGINT,
                deleted_by BIGINT,
                reason TEXT,
                deleted_at TIMESTAMP DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_deleted_posts_channel ON deleted_posts(channel_id, msg_id);

            -- 模式配置
            CREATE TABLE IF NOT EXISTS clone_modes (
                id SERIAL PRIMARY KEY,
                mode_key VARCHAR(50) UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                price DECIMAL(10,2) DEFAULT 0,
                need_accounts INTEGER DEFAULT 1,
                is_vip BOOLEAN DEFAULT FALSE,
                is_enabled BOOLEAN DEFAULT TRUE,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
            INSERT INTO clone_modes (mode_key, name, description, price, need_accounts, is_vip, sort_order) VALUES
                ('full', '普通模式', '使用1个账号克隆，可能遇到限速', 5, 1, false, 1),
                ('dual', '双账号模式', '使用2个账号轮替克隆，限速自动切换', 8, 2, false, 2),
                ('multi', '多账号模式', '使用3个以上账号轮替克隆，稳定高速', 0, 3, true, 3),
                ('monitor', '实时监控', '持续监控源频道新帖子，实时同步', 0, 1, true, 4)
            ON CONFLICT (mode_key) DO NOTHING;
        """)
    
    print("✅ 所有表已初始化")

async def log_admin_action(action, detail, operator="admin"):
    """记录后台操作"""
    try:
        p = await get_pool()
        async with p.acquire() as conn:
            await conn.execute(
                "INSERT INTO admin_logs (action, detail, operator) VALUES ($1,$2,$3)",
                action, detail, operator
            )
    except: pass
