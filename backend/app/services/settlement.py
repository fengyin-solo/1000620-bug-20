"""检测结算业务规则：结算单必须归属到名册内的单位，终态记录不可再改。

- 新开结算单必须能定位到名册里的委托单位；已终止合作的单位只能核对历史
  结算，不能再开新单；
- 已收款是终态：历史结算记录一旦收款确认即封存，任何动作都不能再改动；
- 列表与详情共用同一个序列化出口，看到的状态与可执行动作一致。
"""
from __future__ import annotations

from typing import Any

from app.services.client import find_client
from app.services.permission import Operator
from app.store import store

MODULE = "settlement"
REQUIRED_FIELDS = ["结算单号", "委托单位", "结算周期"]
STATUS_ORDER = ["待核对", "核对中", "已确认", "已收款", "有争议"]
# 动作 -> (目标状态, 允许发起的当前状态集合)。已收款为终态，历史结算记录不可再改。
ACTION_RULES: dict[str, tuple[str, set[str]]] = {
    "发起核对": ("核对中", {"待核对"}),
    "确认结算": ("已收款", {"核对中", "有争议"}),
    "标记争议": ("有争议", {"核对中"}),
}
EDITABLE_FIELDS = ["结算周期", "检测项数", "应收金额", "已收金额", "开票状态"]


def _allowed_actions(entry: dict[str, Any]) -> list[str]:
    current = str(entry.get("status") or "")
    return [action for action, (_, sources) in ACTION_RULES.items() if current in sources]


def _serialize(entry: dict[str, Any]) -> dict[str, Any]:
    row = dict(entry)
    row["结算状态"] = str(entry.get("status") or "")
    row["可用动作"] = _allowed_actions(entry)
    return row


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
        return [_serialize(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return _serialize(entry)

    def create_entry(
        self, values: dict[str, Any], operator: Operator
    ) -> tuple[dict[str, Any] | None, str | None]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        client = find_client(values.get("委托单位"))
        if client is None:
            return None, "委托单位未在名册中登记，结算单必须归属到已登记的单位"
        if client.get("status") == "已终止":
            return None, f"单位 {client.get('单位编码')} 已终止合作，只能核对历史结算，不能新开结算单"
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in REQUIRED_FIELDS + EDITABLE_FIELDS:
            value = values.get(field)
            if value is not None and str(value).strip() != "":
                entry[field] = value
        # 归属锚点落为单位编码，委托单位只存当时名称的快照。
        entry["单位编码"] = str(client.get("单位编码") or "")
        entry["委托单位"] = str(client.get("单位名称") or "")
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return _serialize(entry), None

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"结算单 {entry_id} 不存在或已归档"
        rule = ACTION_RULES.get(action)
        if rule is None:
            return None, f"动作「{action}」不属于检测结算可执行范围"
        target, sources = rule
        current = str(entry.get("status") or "")
        if current not in sources:
            return None, (
                f"当前状态「{current}」不允许执行「{action}」，"
                f"仅 {'、'.join(s for s in STATUS_ORDER if s in sources)} 状态可执行"
            )
        entry["status"] = target
        entry["pending"] = target != "已收款"
        entry["abnormal"] = action == "标记争议"
        return _serialize(entry), f"结算单已{action}"
