"""
DAMM v1 数据接口（官方）。

实测来源：https://docs.meteora.ag/developer-guides/damm-v1/api-reference/overview
  - 基础地址: https://damm-api.meteora.ag   （限频 10 RPS）
  - 池列表:   GET /pools/search?page={0-based?实测 1-based 可用}&size={实测上限约 300}
  - 注意:     GET /pools 需要 address 参数，无法用于全池列举。

池列表响应字段（实测）:
  {data:[{
     pool_address, pool_token_mints:[mint_x, mint_y],
     pool_token_amounts:[...], pool_token_usd_amounts:[...],
     pool_tvl, trading_volume(24h), fee_volume(24h),
     weekly_trading_volume, weekly_fee_volume,
     accumulated_trading_volume, accumulated_fee_volume,
     total_fee_pct(配置手续费率%), apr, trade_apy, created_at(秒), pool_type, pool_name
  }], page, total_count}

重要限制：DAMM v1 接口【不返回代币名称、符号与市值】，
必须通过 Jupiter 备用接口按 mint 补齐（见 providers/jupiter.py），
并在结果中标注数据来源。

关于指标口径（实测）：
  - DAMM 的 `apr` 为“静态年化”（按日费/TVL×365，简单年化，百分比）。
  - `trade_apy` 为按日复利的年化百分比。
  与 DLMM 的 `apr`（等于当日 Fees/TVL 百分比）口径不同，不可混用。
"""

from __future__ import annotations

from typing import Any, Optional

from ..api_client import HttpClient
from ..config import POOL_TYPE_DAMM_V1
from ..models import PoolRecord, TokenInfo


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fetch_pools_page(client: HttpClient, page: int, size: int) -> dict:
    """获取一页 DAMM v1 池列表（/pools/search 支持无过滤全量分页）。"""
    return client.get_json("/pools/search", params={"page": page, "size": size})


def fetch_pool(client: HttpClient, pool_address: str) -> Optional[dict]:
    """获取单个 DAMM v1 池的实时状态（/pools?address= 返回数组）。"""
    resp = client.get_json("/pools", params={"address": pool_address})
    if isinstance(resp, list) and resp:
        return resp[0]
    return None


def _pool_price(raw: dict) -> Optional[float]:
    """由 USD 金额与代币数量推算池价（token_y 每单位 token_x 的价格）。"""
    amounts = raw.get("pool_token_amounts") or []
    usd = raw.get("pool_token_usd_amounts") or []
    if len(amounts) < 2 or len(usd) < 2:
        return None
    try:
        ax, ay = float(amounts[0]), float(amounts[1])
        ux, uy = float(usd[0]), float(usd[1])
        if ax <= 0 or uy <= 0:
            return None
        price_x = ux / ax      # token_x 的 USD 价
        price_y = uy / ay      # token_y 的 USD 价
        if price_y <= 0:
            return None
        return price_x / price_y
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def parse_pool(raw: dict) -> PoolRecord:
    """将 DAMM v1 原始池对象标准化为 PoolRecord（代币详情需另行补齐）。"""
    mints = raw.get("pool_token_mints") or ["", ""]
    mints = (list(mints) + ["", ""])[:2]

    tvl = _num(raw.get("pool_tvl"))
    fees_24h = _num(raw.get("fee_volume"))

    fee_tvl: Optional[float] = None
    if tvl and fees_24h is not None and tvl > 0:
        fee_tvl = fees_24h / tvl * 100.0

    created = raw.get("created_at")
    try:
        created_s = int(created) if created is not None else None
    except (TypeError, ValueError):
        created_s = None

    return PoolRecord(
        pool_address=raw.get("pool_address") or "",
        pool_type=POOL_TYPE_DAMM_V1,
        name=raw.get("pool_name") or "",
        token_x=TokenInfo(
            mint=mints[0], 
            source="pending",
            holders=None,
            top10_holders=None,
            dev_holders=None,
            freeze_auth=None,
            mint_auth=None,
        ),
        token_y=TokenInfo(
            mint=mints[1], 
            source="pending",
            holders=None,
            top10_holders=None,
            dev_holders=None,
            freeze_auth=None,
            mint_auth=None,
        ),
        tvl=tvl,
        volume_24h=_num(raw.get("trading_volume")),
        fees_24h=fees_24h,
        fee_rate_pct=_num(raw.get("total_fee_pct")),
        fee_tvl_ratio_24h=fee_tvl,
        price=_pool_price(raw),
        price_change_24h=None,
        apr=_num(raw.get("apr")),
        apy=None,
        created_at=created_s,
        data_source="damm-api.meteora.ag",
        open_positions=None,  # DAMM API doesn't provide open positions data
    )
