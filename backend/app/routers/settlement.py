"""检测结算接口：维护结算单，覆盖发起核对、确认结算、标记争议等动作。

登记结算单需携带操作角色，且委托单位必须通过合作状态与资质门禁。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.permission import PermissionDenied, resolve_operator
from app.services.settlement import SettlementService

router = APIRouter(prefix="/api/settlement", tags=["检测结算"])

service = SettlementService()

LIST_FIELDS = ["结算单号", "委托单位", "结算周期", "检测项数", "应收金额", "已收金额", "开票状态", "结算状态"]
STATUSES = ["待核对", "核对中", "已确认", "已收款", "有争议"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按结算单号检索"),
    status: str | None = Query(default=None, description="待核对、核对中、已确认、已收款、有争议"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按结算单号与状态过滤检测结算列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出检测结算清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "settlement", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条结算单明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"结算单 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(
    payload: EntryPayload,
    x_operator_role: str | None = Header(default=None),
    x_operator_name: str | None = Header(default=None),
) -> ActionResult:
    """登记一条结算单；单位未登记、合作暂停/终止或资质过期都会被拦下并说明原因。"""
    operator = resolve_operator(x_operator_role, x_operator_name)
    try:
        entry, message = service.create_entry(payload.values, operator)
    except PermissionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="结算单已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条结算单执行发起核对、确认结算、标记争议；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
