"""
全池扫描编排（文档 2.2 全池扫描）。

特性：
  - 自动分页获取 DLMM（游标式）与 DAMM v1（页码式）池列表，尽可能遍历全部可访问页面。
  - 按池地址去重。
  - 记录首次发现时间 / 最后更新时间 / 数据来源。
  - 扫描进度回调、失败重试（在 HttpClient 内）、断点续扫（DLMM 记录游标，DAMM 记录页码）。
  - API 异常记录到 api_errors，绝不生成模拟数据。
  - DAMM v1 缺失的代币名称/市值通过 Jupiter 备用接口补齐（带缓存，标注来源）。
  - DLMM 的持仓/授权/开仓人数等字段由 pool-discovery 接口随池数据一次性返回，无需外部富集。
"""

from __future__ import annotations

import math
import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from . import config
from .api_client import ApiError, HttpClient
from .db import Database
from .models import PoolRecord, TokenInfo
from .providers import damm_v1, dlmm, jupiter

ProgressCb = Callable[[dict], None]


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class TokenResolver:
    """DAMM v1 代币信息补齐器：内存缓存 + DB 缓存 + Jupiter 备用接口。"""

    def __init__(self, db: Database, client: HttpClient):
        self.db = db
        self.client = client
        self.cache: dict[str, TokenInfo] = {}

    def resolve(self, mints: list[str]) -> dict[str, TokenInfo]:
        need = [m for m in dict.fromkeys(mints) if m and m not in self.cache]
        if need:
            from_db = self.db.get_tokens(need)
            self.cache.update(from_db)
            still = [m for m in need if m not in self.cache]
            if still:
                fetched = jupiter.fetch_tokens(self.client, still)
                if fetched:
                    self.cache.update(fetched)
                    self.db.upsert_tokens(fetched)
                for m in still:
                    if m not in self.cache:
                        self.cache[m] = TokenInfo(mint=m, source="jupiter-missing")
        return {m: self.cache.get(m, TokenInfo(mint=m)) for m in mints}


class Scanner:
    def __init__(
        self,
        db: Database,
        *,
        dlmm_client: Optional[HttpClient] = None,
        dlmm_kline_client: Optional[HttpClient] = None,
        damm_client: Optional[HttpClient] = None,
        jupiter_client: Optional[HttpClient] = None,
    ):
        self.db = db
        # 池列表/池详情：pool-discovery 接口
        self.dlmm = dlmm_client or HttpClient(
            base_url=config.DLMM_BASE_URL,
            requests_per_second=config.DLMM_RPS,
            timeout=config.HTTP_TIMEOUT,
            max_retries=config.HTTP_MAX_RETRIES,
        )
        # K 线：dlmm.datapi 接口
        self.dlmm_kline = dlmm_kline_client or HttpClient(
            base_url=config.DLMM_KLINE_BASE_URL,
            requests_per_second=config.DLMM_RPS,
            timeout=config.HTTP_TIMEOUT,
            max_retries=config.HTTP_MAX_RETRIES,
        )
        self.damm = damm_client or HttpClient(
            base_url=config.DAMM_BASE_URL,
            requests_per_second=config.DAMM_RPS,
            timeout=config.HTTP_TIMEOUT,
            max_retries=config.HTTP_MAX_RETRIES,
        )
        self.jupiter = jupiter_client or HttpClient(
            base_url=config.JUPITER_BASE_URL,
            requests_per_second=config.JUPITER_RPS,
            timeout=config.HTTP_TIMEOUT,
            max_retries=config.HTTP_MAX_RETRIES,
        )
        self.resolver = TokenResolver(db, self.jupiter)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.progress: dict[str, dict] = {}

    # ------------------------------------------------------------------ 控制
    def request_stop(self) -> None:
        self._stop.set()

    def reset_stop(self) -> None:
        self._stop.clear()

    def is_running(self) -> bool:
        with self._lock:
            return any(p.get("state") == "running" for p in self.progress.values())

    # ------------------------------------------------------------------ 扫描
    def scan(
        self,
        pool_types: Optional[list[str]] = None,
        *,
        resume: bool = True,
        max_pages: Optional[int] = None,
        progress_cb: Optional[ProgressCb] = None,
        enrich_tokens: bool = True,
    ) -> dict:
        """扫描指定池类型。返回各类型的最终进度字典。"""
        pool_types = pool_types or list(config.SUPPORTED_POOL_TYPES)
        results: dict[str, dict] = {}
        for pt in pool_types:
            if self._stop.is_set():
                break
            if pt == config.POOL_TYPE_DLMM:
                results[pt] = self._scan_dlmm(resume, max_pages, progress_cb, enrich_tokens)
            elif pt == config.POOL_TYPE_DAMM_V1:
                results[pt] = self._scan_damm(resume, max_pages, progress_cb, enrich_tokens)
        return results

    def _emit(self, prog: dict, cb: Optional[ProgressCb]) -> None:
        with self._lock:
            self.progress[prog["pool_type"]] = dict(prog)
        if cb:
            cb(dict(prog))

    def _init_progress(self, pool_type: str, resume: bool) -> dict:
        existing = {r["pool_type"]: r for r in self.db.get_scan_status()}
        row = existing.get(pool_type)
        start_page = 1
        if resume and row and row.get("state") in ("error", "stopped", "running"):
            start_page = int(row.get("last_position") or 0) + 1
        elif resume and row:
            # 已完成过，重新从头扫描以刷新数据
            start_page = 1
        return {
            "pool_type": pool_type,
            "state": "running",
            "start_page": start_page,
            "pages_scanned": 0,
            "total_pages": None,
            "discovered": 0,
            "processed": 0,
            "failures": 0,
            "last_position": start_page - 1,
            "total_available": None,
            "message": "",
        }

    def _scan_dlmm(self, resume, max_pages, cb, enrich) -> dict:
        pt = config.POOL_TYPE_DLMM
        prog = self._init_progress(pt, resume)
        seen: set[str] = set()
        # 断点续扫：pool-discovery 为游标分页，未完成扫描从上次游标继续。
        cursor: Optional[str] = None
        if resume:
            row = {r["pool_type"]: r for r in self.db.get_scan_status()}.get(pt)
            if row and row.get("state") in ("error", "stopped", "running"):
                cursor = self.db.get_setting(f"cursor:{pt}") or None
        self.db.update_scan_status(pt, state="running", note="扫描 DLMM 中")
        self._emit(prog, cb)

        while True:
            if self._stop.is_set():
                prog["state"] = "stopped"
                prog["message"] = "用户已停止"
                break
            if max_pages is not None and prog["pages_scanned"] >= max_pages:
                prog["state"] = "stopped"
                prog["message"] = f"达到本页数上限 {max_pages}"
                break

            try:
                resp = dlmm.fetch_pools_page(
                    self.dlmm, after_key=cursor, page_size=config.DLMM_PAGE_SIZE
                )
            except ApiError as exc:
                self.db.log_api_error(pool_type=pt, endpoint="/pools",
                                      attempt=self.dlmm.max_retries, message=str(exc))
                prog["failures"] += 1
                prog["state"] = "error"
                prog["message"] = f"DLMM 第 {prog['pages_scanned'] + 1} 页请求失败：{exc}"
                break

            data = resp.get("data") or []
            total = resp.get("total")
            if total is not None:
                prog["total_available"] = int(total)
                prog["total_pages"] = int(math.ceil(total / config.DLMM_PAGE_SIZE)) if total else 1

            if not data:
                prog["state"] = "done"
                break

            for raw in data:
                try:
                    rec = dlmm.parse_pool(raw)
                except Exception:  # noqa: BLE001 - 单条解析失败不应中断
                    prog["failures"] += 1
                    continue
                if not rec.pool_address:
                    continue
                seen.add(rec.pool_address)
                rec.first_seen = _now_iso()
                rec.last_updated = _now_iso()
                self.db.upsert_pool(rec)
                prog["processed"] += 1

            prog["discovered"] = len(seen)
            prog["pages_scanned"] += 1
            prog["last_position"] = prog["pages_scanned"]
            next_cursor = resp.get("after_key")
            self.db.set_setting(f"cursor:{pt}", next_cursor or "")
            self.db.update_scan_status(
                pt, pages_scanned=prog["pages_scanned"], pools_discovered=prog["discovered"],
                pools_processed=prog["processed"], failures=prog["failures"],
                last_position=prog["last_position"], total_available=prog["total_available"],
                last_scan_time=_now_iso(), state="running", note="扫描 DLMM 中",
            )
            self._emit(prog, cb)

            if not resp.get("has_more") or not next_cursor:
                prog["state"] = "done"
                break
            cursor = next_cursor

        if prog["state"] == "done":
            self.db.set_setting(f"cursor:{pt}", "")
        self._finalize(pt, prog, cb)
        return prog

    def _scan_damm(self, resume, max_pages, cb, enrich) -> dict:
        pt = config.POOL_TYPE_DAMM_V1
        prog = self._init_progress(pt, resume)
        page = prog["start_page"]
        seen: set[str] = set()
        self.db.update_scan_status(pt, state="running", note="扫描 DAMM v1 中")
        self._emit(prog, cb)

        while True:
            if self._stop.is_set():
                prog["state"] = "stopped"
                prog["message"] = "用户已停止"
                break
            if max_pages is not None and prog["pages_scanned"] >= max_pages:
                prog["state"] = "stopped"
                prog["message"] = f"达到本页数上限 {max_pages}"
                break

            try:
                resp = damm_v1.fetch_pools_page(self.damm, page, config.DAMM_PAGE_SIZE)
            except ApiError as exc:
                self.db.log_api_error(pool_type=pt, endpoint="/pools/search",
                                      attempt=self.damm.max_retries, message=str(exc))
                prog["failures"] += 1
                prog["state"] = "error"
                prog["message"] = f"第 {page} 页请求失败：{exc}"
                break

            data = resp.get("data") or []
            total = resp.get("total_count")
            if total is not None:
                prog["total_available"] = int(total)
                prog["total_pages"] = int(math.ceil(total / config.DAMM_PAGE_SIZE)) if total else 1

            if not data:
                prog["state"] = "done"
                prog["last_position"] = page
                break

            records: list[PoolRecord] = []
            for raw in data:
                try:
                    rec = damm_v1.parse_pool(raw)
                except Exception:  # noqa: BLE001
                    prog["failures"] += 1
                    continue
                if rec.pool_address:
                    records.append(rec)

            if enrich and records:
                mints = [r.token_x.mint for r in records] + [r.token_y.mint for r in records]
                try:
                    token_map = self.resolver.resolve(mints)
                    for rec in records:
                        rec.token_x = token_map.get(rec.token_x.mint, rec.token_x)
                        rec.token_y = token_map.get(rec.token_y.mint, rec.token_y)
                except Exception as exc:  # noqa: BLE001 - 备用接口失败不阻断主流程
                    self.db.log_api_error(pool_type=pt, endpoint="/tokens/v2/search",
                                          attempt=0, message=f"代币补齐失败：{exc}")

            for rec in records:
                seen.add(rec.pool_address)
                rec.first_seen = _now_iso()
                rec.last_updated = _now_iso()
                self.db.upsert_pool(rec)
                prog["processed"] += 1

            prog["discovered"] = len(seen)
            prog["pages_scanned"] += 1
            prog["last_position"] = page
            self.db.update_scan_status(
                pt, pages_scanned=prog["pages_scanned"], pools_discovered=prog["discovered"],
                pools_processed=prog["processed"], failures=prog["failures"],
                last_position=prog["last_position"], total_available=prog["total_available"],
                last_scan_time=_now_iso(), state="running", note="扫描 DAMM v1 中",
            )
            self._emit(prog, cb)

            if prog["total_pages"] and page >= prog["total_pages"]:
                prog["state"] = "done"
                break
            page += 1

        self._finalize(pt, prog, cb)
        return prog

    def _finalize(self, pool_type: str, prog: dict, cb: Optional[ProgressCb]) -> None:
        if prog["state"] == "running":
            prog["state"] = "done"
        self.db.update_scan_status(
            pool_type, pages_scanned=prog["pages_scanned"], pools_discovered=prog["discovered"],
            pools_processed=prog["processed"], failures=prog["failures"],
            last_position=prog["last_position"], total_available=prog["total_available"],
            last_scan_time=_now_iso(), state=prog["state"], note=prog.get("message", ""),
        )
        self._emit(prog, cb)
