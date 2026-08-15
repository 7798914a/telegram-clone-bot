import hashlib
import hmac
import time
import secrets
import httpx
from config import OKPAY_APP_ID, OKPAY_TOKEN, OKPAY_API_URL, OKPAY_CALLBACK_URL

def build_base(params):
    filtered = {}
    for k, v in params.items():
        if k == "sign": continue
        if v is None or v == "": continue
        if isinstance(v, bool):
            filtered[k] = "true" if v else "false"
        elif isinstance(v, dict):
            for dk, dv in v.items():
                if dv is None or dv == "": continue
                filtered[f"{k}.{dk}"] = "true" if dv is True else "false" if dv is False else str(dv)
        else:
            filtered[k] = str(v)
    sorted_keys = sorted(filtered.keys())
    return "&".join(f"{k}={filtered[k]}" for k in sorted_keys)

def sign(params, token=OKPAY_TOKEN):
    base = build_base(params)
    return hmac.new(token.encode(), base.encode(), hashlib.sha256).hexdigest().upper()

def verify(payload, token=OKPAY_TOKEN):
    sign_value = payload.get("sign", "")
    calculated = sign(payload, token)
    return hmac.compare_digest(sign_value, calculated)

def signed_request(params):
    params["id"] = OKPAY_APP_ID
    params["timestamp"] = int(time.time())
    params["nonce"] = secrets.token_hex(16)
    params["sign"] = sign(params)
    return params

async def pay_link(amount, unique_id, callback_url=None):
    params = signed_request({
        "amount": str(amount),
        "coin": "CNY",
        "unique_id": unique_id,
        "callback_url": callback_url or OKPAY_CALLBACK_URL,
    })
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{OKPAY_API_URL}/payLink", data=params)
        return resp.json()

async def check_deposit(unique_id):
    params = signed_request({"unique_id": unique_id})
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{OKPAY_API_URL}/checkDeposit", data=params)
        return resp.json()


async def pay_link_usdt(amount, unique_id, callback_url=None):
    """创建 USDT 支付链接"""
    params = signed_request({
        "amount": str(amount),
        "coin": "USDT",
        "unique_id": unique_id,
        "callback_url": callback_url or OKPAY_CALLBACK_URL,
    })
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{OKPAY_API_URL}/payLink", data=params)
        return resp.json()

async def check_transfer_by_txid(txid):
    """用平台订单号查单"""
    params = signed_request({"txid": txid})
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{OKPAY_API_URL}/checkTransferByTxid", data=params)
        return resp.json()
