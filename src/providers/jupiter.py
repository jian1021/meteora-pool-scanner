"""
Jupiter 代币接口（备用，用于补齐 DAMM v1 缺失的代币名称/符号/市值）。

实测来源：https://lite-api.jup.ag/tokens/v2/search?query={mint1,mint2,...}
  （支持逗号分隔批量查询，无需 API Key）

响应为数组，字段（实测）:
  [{id, name, symbol, decimals, circSupply, totalSupply, fdv, mcap,
    usdPrice, stats24h:{priceChange,...}, ...}]

用途：
  - 市值：优先 mcap（流通市值），无则用 fdv，并标注口径。
  - 24h 涨跌幅：stats24h.priceChange。
所有通过本接口获得的数据均在记录中标注来源 jupiter，满足“备用 API 需记录来源”要求。
"""

from __future__ import annotations

from typing import Iterable, Optional

from ..api_client import HttpClient
from ..models import TokenInfo

SOURCE = "jupiter"
_BATCH_SIZE = 100


def _to_token(item: dict) -> TokenInfo:
    mcap = item.get("mcap")
    fdv = item.get("fdv")
    mcap_f = float(mcap) if isinstance(mcap, (int, float)) else None
    fdv_f = float(fdv) if isinstance(fdv, (int, float)) else None
    stats24 = item.get("stats24h") or {}
    pc = stats24.get("priceChange")
    return TokenInfo(
        mint=item.get("id") or item.get("address") or "",
        name=item.get("name") or "",
        symbol=item.get("symbol") or "",
        market_cap=mcap_f,
        fdv=fdv_f,
        price=float(item["usdPrice"]) if isinstance(item.get("usdPrice"), (int, float)) else None,
        price_change_24h=float(pc) if isinstance(pc, (int, float)) else None,
        market_cap_type="market_cap" if (mcap_f and mcap_f > 0) else ("fdv" if (fdv_f and fdv_f > 0) else ""),
        source=SOURCE,
    )


def fetch_tokens(client: HttpClient, mints: Iterable[str]) -> dict[str, TokenInfo]:
    """批量查询代币信息，返回 {mint: TokenInfo}。自动去重与分批。"""
    unique = [m for m in dict.fromkeys(mints) if m]
    result: dict[str, TokenInfo] = {}
    for i in range(0, len(unique), _BATCH_SIZE):
        chunk = unique[i : i + _BATCH_SIZE]
        try:
            resp = client.get_json("/tokens/v2/search", params={"query": ",".join(chunk)})
        except Exception:  # noqa: BLE001 - 备用接口失败不应中断主流程
            continue
        if not isinstance(resp, list):
            continue
        for item in resp:
            if not isinstance(item, dict):
                continue
            tok = _to_token(item)
            if tok.mint:
                result[tok.mint] = tok
    return result
