from telethon import events, Button
from models import get_pool
from okpay import pay_link_usdt
from exchange_rate import get_usd_to_cny
import secrets

def register(bot):
    @bot.on(events.CallbackQuery(data="recharge"))
    async def cb_recharge(event):
        await event.edit("💰 充值\n\n发送：`充值 金额`（人民币）\n例如：`充值 50`")
    
    @bot.on(events.NewMessage(pattern=r'充值\s+(\d+(?:\.\d+)?)'))
    async def cmd_recharge(event):
        if not event.is_private: return
        cny_amount = float(event.pattern_match.group(1))
        rate = await get_usd_to_cny()
        usdt_needed = round(cny_amount / rate, 2)
        unique_id = f"RECHARGE_{event.sender_id}_{secrets.token_hex(4)}"
        result = await pay_link_usdt(usdt_needed, unique_id)
        if result.get("status") == "success":
            pay_url = result["data"]["pay_url"]
            p = await get_pool()
            async with p.acquire() as conn:
                await conn.execute(
                    "INSERT INTO payments (telegram_id, amount, amount_cny, status, note) VALUES ($1,$2,$3,'pending',$4)",
                    event.sender_id, cny_amount, cny_amount, unique_id
                )
            await event.reply(
                f"💰 **充值 ¥{cny_amount}**\n\n汇率：1 USDT = ¥{rate}\n需支付：**{usdt_needed} USDT**\n\n支付后自动到账 ¥{cny_amount}",
                buttons=[
                    [Button.url("💳 去支付", pay_url)],
                    [Button.inline("🔄 检查余额", "my_info")]
                ]
            )
        else:
            await event.reply(f"❌ 创建支付失败：{result.get('msg','未知')}")
    
    @bot.on(events.NewMessage(pattern='💰 余额充值'))
    async def cmd_recharge_btn(event):
        if not event.is_private: return
        await event.reply("💰 充值\n\n发送：`充值 金额`（人民币）\n例如：`充值 50`")