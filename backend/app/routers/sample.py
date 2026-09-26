"""样品受理接口：登记样品即登记新的检测委托，必须先过委托单位这道闸。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.permission import Operator, get_operator, require
from app.services.sample import SampleService

router = APIRouter(prefix="/api/sample", tags=["样品受理"])

service = SampleService()

LIST_FIELDS = ["样品编号", "样品名称", "样品类别", "单位编码", "送检单位", "送检人", "接收日期", "保存条件", "样品状态"]
STATUSES = ["待受理", "已受理", "已分发", "已退回"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按样品编号检索"),
    status: str | None = Query(default=None, description="待受理、已受理、已分发、已退回"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按样品编号与状态过滤样品受理列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出样品受理清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "sample", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条样品明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"样品 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload, operator: Operator = Depends(get_operator)) -> ActionResult:
    """登记一条样品（新委托）；单位已暂停、已终止或资质过期都会被拦下并说明原因。"""
    require(operator, "sample:create")
    entry, message = service.create_entry(payload.values, operator)
    if entry is None:
        return ActionResult(ok=False, message=message or "登记未生效")
    return ActionResult(ok=True, message="样品已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条样品执行受理样品、分发检测、退回样品；终态记录不允许再改动。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
