import httpx

async def get_usd_to_cny():
    """获取 USD → CNY 实时汇率"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://open.er-api.com/v6/latest/USD")
            data = resp.json()
            if data.get("result") == "success":
                return float(data["rates"]["CNY"])
    except:
        pass
    return 7.0
