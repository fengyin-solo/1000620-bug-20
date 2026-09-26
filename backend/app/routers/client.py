"""委托单位接口：维护委托单位，覆盖审核单位、暂停合作、终止合作等动作。

写操作一律先过角色闸：登记允许业务员，变更资料与状态流转仅管理员；
越权调用返回 403 并说明原因，不再静默成功。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.client import ClientService
from app.services.permission import Operator, get_operator, require

router = APIRouter(prefix="/api/client", tags=["委托单位"])

service = ClientService()

LIST_FIELDS = ["单位编码", "单位名称", "单位类型", "联系人", "联系电话", "结算方式", "资质编号", "资质有效期至", "单位状态"]
STATUSES = ["待审核", "合作中", "已暂停", "已终止", "资质过期"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按单位编码检索"),
    status: str | None = Query(default=None, description="待审核、合作中、已暂停、已终止、资质过期"),
    page: int = 1,
    size: int = 20,
    operator: Operator = Depends(get_operator),
) -> PageResult[dict]:
    """按单位编码与状态过滤委托单位列表；状态按展示口径过滤，与详情一致。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size, operator=operator)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries(operator: Operator = Depends(get_operator)) -> dict[str, Any]:
    """导出委托单位清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000, operator=operator)
    return {"module": "client", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int, operator: Operator = Depends(get_operator)) -> dict:
    """读取单条委托单位明细；与列表共用同一套状态口径。"""
    entry = service.get_entry(entry_id, operator)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"委托单位 {entry_id} 不存在或已归档")
    return entry


@router.get("/{entry_id}/audits")
def get_audits(entry_id: int) -> dict[str, Any]:
    """单条单位的变更履历：资质编号、结算方式等关键字段谁改的、什么时候改的。"""
    records = service.list_audits(entry_id)
    if records is None:
        raise HTTPException(status_code=404, detail=f"委托单位 {entry_id} 不存在或已归档")
    return {"total": len(records), "items": records}


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload, operator: Operator = Depends(get_operator)) -> ActionResult:
    """登记一条委托单位；单位编码重复或日期格式不对会被拦下并说明原因。"""
    require(operator, "client:create")
    entry, error = service.create_entry(payload.values, operator)
    if error:
        return ActionResult(ok=False, message=error)
    return ActionResult(ok=True, message="委托单位已登记，待审核", entry=entry)


@router.post("/{entry_id}/update", response_model=ActionResult)
def update_entry(entry_id: int, payload: EntryPayload, operator: Operator = Depends(get_operator)) -> ActionResult:
    """变更单位资料：仅管理员可改，每次变更都留审计记录，历史委托与结算不受影响。"""
    require(operator, "client:update")
    entry, message = service.update_entry(entry_id, payload.values, operator)
    if entry is None:
        return ActionResult(ok=False, message=message or "变更未生效")
    return ActionResult(ok=True, message=message or "委托单位资料已变更", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload, operator: Operator = Depends(get_operator)) -> ActionResult:
    """对单条委托单位执行审核单位、暂停合作、恢复合作、终止合作；仅管理员可执行。"""
    require(operator, "client:action")
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, operator)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
