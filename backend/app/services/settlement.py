"""检测结算业务规则：状态流转、字段校验与筛选口径都收在这里。

登记结算单同样属于为单位建立新的业务记录：先过委托单位门禁，
暂停/终止或资质过期的单位不能新开结算单；已确认的历史结算记录不被改动。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.services.client import commission_gate
from app.services.permission import Operator, require_permission
from app.store import store

MODULE = "settlement"
REQUIRED_FIELDS = ["结算单号", "委托单位", "结算周期"]
STATUS_ORDER = ["待核对", "核对中", "已确认", "已收款", "有争议"]
ACTION_RULES = {"发起核对": "核对中", "确认结算": "已收款", "标记争议": "有争议"}
NEGATIVE_ACTIONS = []


class SettlementService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("结算单号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(
        self,
        values: dict[str, Any],
        operator: Operator,
        today: date | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        require_permission(operator, "settlement:create")
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        blocked = commission_gate(values.get("委托单位"), today, field_label="委托单位")
        if blocked:
            return None, blocked
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["委托单位"] = str(values.get("委托单位") or "").strip()
        entry["登记人"] = operator.name
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, ""

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"结算单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于检测结算可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"结算单已{action}"
