from fastapi import Request
from fastapi.responses import JSONResponse
from okpay import verify
from models import get_pool
import json

def register(app):
    @app.post("/okpay/callback")
    async def okpay_callback(request: Request):
        # 尝试多种格式解析
        body = None
        content_type = request.headers.get("content-type", "")
        
        try:
            if "application/json" in content_type:
                body = await request.json()
            else:
                # form 格式
                form = await request.form()
                body = dict(form)
                # 如果有 data 字段是 JSON 字符串，解析
                if "data" in body and isinstance(body["data"], str):
                    try:
                        body["data"] = json.loads(body["data"])
                    except:
                        pass
                # 数值转换
                if "code" in body:
                    body["code"] = int(body["code"])
                if "id" in body:
                    body["id"] = int(body["id"])
                if "data" in body and isinstance(body["data"], dict):
                    if "status" in body["data"]:
                        body["data"]["status"] = int(body["data"]["status"])
        except:
            return JSONResponse({"status": "error", "msg": "parse error"}, status_code=400)
        
        # 验签
        if not verify(body):
            return JSONResponse({"status": "error", "msg": "bad sign"}, status_code=400)
        
        data = body.get("data", {})
        order_id = data.get("order_id")
        amount = float(data.get("amount", 0))
        status = data.get("status")
        type_ = data.get("type")
        unique_id = data.get("unique_id", "")
        
        if type_ == "deposit" and status == 1:
            p = await get_pool()
            async with p.acquire() as conn:
                # 找 pending 订单
                pending = await conn.fetchrow(
                    "SELECT * FROM payments WHERE status='pending' AND note LIKE $1 ORDER BY id DESC LIMIT 1",
                    f"%{unique_id}%"
                )
                if not pending:
                    # 尝试按金额匹配
                    pending = await conn.fetchrow(
                        "SELECT * FROM payments WHERE status='pending' AND amount=$1 ORDER BY id DESC LIMIT 1",
                        amount
                    )
                if pending:
                    await conn.execute(
                        "UPDATE users SET balance = balance + $1 WHERE telegram_id=$2",
                        pending["amount"], pending["telegram_id"]
                    )
                    await conn.execute(
                        "UPDATE payments SET status='approved', approved_at=NOW() WHERE id=$1",
                        pending["id"]
                    )
        
        return JSONResponse({"status": "success"})
