from telethon import Button

def main_menu():
    return [
        [Button.inline("🚀 创建克隆任务", "create_clone")],
        [Button.inline("📋 我的任务", "my_tasks")],
        [Button.inline("👤 我的信息", "my_info")],
        [Button.inline("💰 余额充值", "recharge")],
        [Button.inline("🎧 联系客服", "support")]
    ]

def back_button():
    return [[Button.inline("🔙 返回", "back")]]

def bottom_buttons():
    """底部固定按钮（用于所有消息）"""
    return [
        Button.text("📋 创建任务", resize=True),
        Button.text("👤 我的信息", resize=True),
        Button.text("💰 余额充值", resize=True),
        Button.text("🎧 联系客服", resize=True)
    ]
