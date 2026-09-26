"""样品受理业务规则：登记即新委托，必须先过委托单位这道闸。

样品受理是检测委托的登记入口：受理前必须能定位到名册里的委托单位，
且该单位当前可委托（合作中、资质在有效期内）；已分发 / 已退回是终态，
历史委托记录不再允许改动。
"""
from __future__ import annotations

from typing import Any

from app.services.client import commission_block, find_client
from app.services.permission import Operator
from app.store import store

MODULE = "sample"
REQUIRED_FIELDS = ["样品编号", "样品名称", "样品类别"]
STATUS_ORDER = ["待受理", "已受理", "已分发", "已退回"]
# 动作 -> (目标状态, 允许发起的当前状态集合)。已分发、已退回为终态，历史委托不可再改。
ACTION_RULES: dict[str, tuple[str, set[str]]] = {
    "受理样品": ("已受理", {"待受理"}),
    "分发检测": ("已分发", {"已受理"}),
    "退回样品": ("已退回", {"待受理"}),
}


def _allowed_actions(entry: dict[str, Any]) -> list[str]:
    current = str(entry.get("status") or "")
    return [action for action, (_, sources) in ACTION_RULES.items() if current in sources]


def _serialize(entry: dict[str, Any]) -> dict[str, Any]:
    row = dict(entry)
    row["样品状态"] = str(entry.get("status") or "")
    row["可用动作"] = _allowed_actions(entry)
    return row


class SampleService:
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
            rows = [row for row in rows if keyword in str(row.get("样品编号", ""))]
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
        anchor = str(values.get("单位编码") or values.get("送检单位") or "").strip()
        if not anchor:
            return None, "缺少必填字段：单位编码（或送检单位），委托必须归属到名册内的单位"
        client = find_client(anchor)
        if client is None:
            return None, "送检单位未在委托单位名册中登记，请先在委托单位模块登记并通过审核"
        block = commission_block(client)
        if block:
            return None, block
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in REQUIRED_FIELDS:
            entry[field] = str(values.get(field) or "").strip()
        # 归属锚点落为单位编码，送检单位只存当时名称的快照，后续单位改名不回写历史委托。
        entry["单位编码"] = str(client.get("单位编码") or "")
        entry["送检单位"] = str(client.get("单位名称") or "")
        for field in ("送检人", "接收日期", "保存条件"):
            if values.get(field):
                entry[field] = str(values.get(field)).strip()
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return _serialize(entry), None

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"样品 {entry_id} 不存在或已归档"
        rule = ACTION_RULES.get(action)
        if rule is None:
            return None, f"动作「{action}」不属于样品受理可执行范围"
        target, sources = rule
        current = str(entry.get("status") or "")
        if current not in sources:
            return None, (
                f"当前状态「{current}」不允许执行「{action}」，"
                f"仅 {'、'.join(s for s in STATUS_ORDER if s in sources)} 状态可执行"
            )
        entry["status"] = target
        entry["pending"] = target not in {"已分发", "已退回"}
        entry["abnormal"] = False
        return _serialize(entry), f"样品已{action}"
