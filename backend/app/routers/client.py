"""委托单位接口：维护委托单位，覆盖审核单位、暂停合作、终止合作等动作。

所有写操作都要求请求头携带操作角色（X-Operator-Role）与操作人（X-Operator-Name），
越权调用返回 403 并说明缺少的权限，不静默放行。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.client import ClientService
from app.services.permission import PermissionDenied, resolve_operator

router = APIRouter(prefix="/api/client", tags=["委托单位"])

service = ClientService()

LIST_FIELDS = ["单位编码", "单位名称", "单位类型", "联系人", "联系电话", "结算方式", "资质编号", "资质有效期至", "单位状态"]
STATUSES = ["待审核", "合作中", "资质过期", "已暂停", "已终止"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按单位编码检索"),
    status: str | None = Query(default=None, description="待审核、合作中、资质过期、已暂停、已终止"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按单位编码与状态过滤委托单位列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出委托单位清单：返回当前过滤条件下的全量数据，口径与列表一致。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "client", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条委托单位明细（含变更记录）；状态口径与列表一致。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"委托单位 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(
    payload: EntryPayload,
    x_operator_role: str | None = Header(default=None),
    x_operator_name: str | None = Header(default=None),
) -> ActionResult:
    """登记一条委托单位；缺字段、编码重复或角色越权时都说明原因。"""
    operator = resolve_operator(x_operator_role, x_operator_name)
    try:
        entry, message = service.create_entry(payload.values, operator)
    except PermissionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="委托单位已登记，待审核", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(
    entry_id: int,
    payload: EntryPayload,
    x_operator_role: str | None = Header(default=None),
    x_operator_name: str | None = Header(default=None),
) -> ActionResult:
    """对单条委托单位执行审核单位、暂停合作、终止合作；不允许的动作会被拦下并说明原因。"""
    operator = resolve_operator(x_operator_role, x_operator_name)
    action = str(payload.values.get("action") or "").strip()
    try:
        entry, message = service.run_action(entry_id, action, operator)
    except PermissionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.put("/{entry_id}", response_model=ActionResult)
def update_profile(
    entry_id: int,
    payload: EntryPayload,
    x_operator_role: str | None = Header(default=None),
    x_operator_name: str | None = Header(default=None),
) -> ActionResult:
    """修改资质编号、结算方式等档案字段；逐字段写变更记录，归属字段不可改。"""
    operator = resolve_operator(x_operator_role, x_operator_name)
    try:
        entry, message = service.update_profile(entry_id, payload.values, operator)
    except PermissionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
