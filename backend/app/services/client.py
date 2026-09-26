"""委托单位业务规则：状态流转、字段校验与筛选口径都收在这里。

关键口径：
- 合作状态（status）只通过动作流转：待审核 -> 合作中 -> 已暂停/已终止，已终止不可再变。
- 展示状态（单位状态）在合作状态之上叠加资质有效期口径：合作中但资质已过期的单位，
  列表与详情都显示「资质过期」，且任何入口都不能再为它登记新的检测委托。
- 资质编号、结算方式等档案字段只允许有权限的角色修改，每一次修改都写变更记录。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.services.permission import Operator, require_permission
from app.store import store

MODULE = "client"
REQUIRED_FIELDS = ["单位编码", "单位名称", "单位类型"]
# 档案字段：登记后可由有权限角色修改，修改必留痕
PROFILE_FIELDS = ["联系人", "联系电话", "结算方式", "资质编号", "资质有效期至"]
STATUS_ORDER = ["待审核", "合作中", "已暂停", "已终止"]
EXPIRED_STATUS = "资质过期"
# 动作 -> (所需权限, 允许的当前状态, 目标状态)
ACTION_RULES = {
    "审核单位": ("client:review", {"待审核"}, "合作中"),
    "暂停合作": ("client:suspend", {"合作中"}, "已暂停"),
    "终止合作": ("client:terminate", {"合作中", "已暂停"}, "已终止"),
}


def parse_date(value: Any) -> date | None:
    """按到期口径解析 YYYY-MM-DD；非法或缺失返回 None。"""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _today(today: date | None) -> date:
    return today if today is not None else date.today()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def qualification_state(entry: dict[str, Any], today: date | None = None) -> str:
    """资质口径：未登记 / 有效 / 已过期。列表、详情、委托拦截都用这一个函数。"""
    if not str(entry.get("资质编号") or "").strip():
        return "未登记"
    expiry = parse_date(entry.get("资质有效期至"))
    if expiry is None:
        return "未登记"
    return "已过期" if expiry < _today(today) else "有效"


def display_status(entry: dict[str, Any], today: date | None = None) -> str:
    """展示状态：合作中但资质过期的单位不再显示合作中。"""
    status = str(entry.get("status") or "")
    if status == "合作中" and qualification_state(entry, today) == "已过期":
        return EXPIRED_STATUS
    return status


def commission_block_reason(entry: dict[str, Any], today: date | None = None) -> str | None:
    """新委托拦截口径：返回 None 表示可委托，否则返回可读的拦截原因。"""
    code = entry.get("单位编码", "?")
    status = str(entry.get("status") or "")
    if status == "待审核":
        return f"委托单位 {code} 尚未审核通过，不能登记新的检测委托"
    if status == "已暂停":
        return f"委托单位 {code} 合作已暂停，不能登记新的检测委托"
    if status == "已终止":
        return f"委托单位 {code} 合作已终止，不能登记新的检测委托"
    state = qualification_state(entry, today)
    if state == "未登记":
        return f"委托单位 {code} 未登记资质编号或有效期，不能登记新的检测委托"
    if state == "已过期":
        return (
            f"委托单位 {code} 的资质编号 {entry.get('资质编号')} "
            f"已于 {entry.get('资质有效期至')} 到期，不能登记新的检测委托"
        )
    return None


def serialize(entry: dict[str, Any], today: date | None = None, *, with_audit: bool = False) -> dict[str, Any]:
    """列表与详情共用的输出口径：同一条单位在任何入口看到的状态都一致。"""
    row = {key: value for key, value in entry.items() if key != "变更记录"}
    row["单位状态"] = display_status(entry, today)
    row["资质状态"] = qualification_state(entry, today)
    reason = commission_block_reason(entry, today)
    row["可委托"] = reason is None
    row["不可委托原因"] = reason or ""
    if with_audit:
        row["变更记录"] = list(entry.get("变更记录") or [])
    return row


def commission_gate(identifier: Any, today: date | None = None, *, field_label: str = "送检单位") -> str | None:
    """任何登记新委托的入口都先过这一关：返回 None 放行，否则返回拦截原因。

    按单位编码（优先）或单位名称定位委托单位，归属不清或状态/资质不允许时拦下。
    """
    service = ClientService()
    text = str(identifier or "").strip()
    if not text:
        return f"检测委托必须归属已登记的委托单位，请填写{field_label}"
    entry = service.find_by_code(text) or service.find_by_name(text)
    if entry is None:
        return f"{field_label}「{text}」尚未登记为委托单位，请先在委托单位模块登记并通过审核"
    return commission_block_reason(entry, today)


class ClientService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
        today: date | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [serialize(row, today) for row in store.rows(MODULE)]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("单位编码", ""))]
        if status:
            rows = [row for row in rows if row.get("单位状态") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int, today: date | None = None) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return serialize(entry, today, with_audit=True)

    def find_by_code(self, code: str) -> dict[str, Any] | None:
        code = code.strip()
        for row in store.rows(MODULE):
            if str(row.get("单位编码", "")).strip() == code:
                return row
        return None

    def find_by_name(self, name: str) -> dict[str, Any] | None:
        name = name.strip()
        for row in store.rows(MODULE):
            if str(row.get("单位名称", "")).strip() == name:
                return row
        return None

    def create_entry(
        self,
        values: dict[str, Any],
        operator: Operator,
        today: date | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        require_permission(operator, "client:create")
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        code = str(values.get("单位编码") or "").strip()
        if self.find_by_code(code):
            return None, f"单位编码 {code} 已存在，同一单位不能重复登记"
        expiry_text = str(values.get("资质有效期至") or "").strip()
        if expiry_text and parse_date(expiry_text) is None:
            return None, "资质有效期至格式应为 YYYY-MM-DD"
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in REQUIRED_FIELDS + PROFILE_FIELDS:
            value = values.get(field)
            if value is not None and str(value).strip() != "":
                entry[field] = str(value).strip()
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        entry["登记人"] = operator.name
        entry["登记时间"] = _now()
        entry["变更记录"] = [self._audit(operator, "登记单位", f"登记委托单位 {code}，状态 待审核")]
        rows.append(entry)
        return serialize(entry, today, with_audit=True), ""

    def run_action(
        self,
        entry_id: int,
        action: str,
        operator: Operator,
        today: date | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"委托单位 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于委托单位可执行范围"
        permission, allowed_from, target = ACTION_RULES[action]
        require_permission(operator, permission)
        current = str(entry.get("status") or "")
        if current not in allowed_from:
            return None, f"当前状态「{display_status(entry, today)}」不允许执行「{action}」"
        if action == "审核单位":
            state = qualification_state(entry, today)
            if state == "未登记":
                return None, "未登记资质编号或有效期，不能审核通过"
            if state == "已过期":
                return None, f"资质编号 {entry.get('资质编号')} 已于 {entry.get('资质有效期至')} 到期，不能审核通过"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = False
        entry.setdefault("变更记录", []).append(
            self._audit(operator, action, f"状态从 {current} 变为 {target}")
        )
        return serialize(entry, today, with_audit=True), f"委托单位已{action}"

    def update_profile(
        self,
        entry_id: int,
        values: dict[str, Any],
        operator: Operator,
        today: date | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        """修改档案字段（资质编号、结算方式等）：只认白名单字段，逐字段留痕。

        单位编码、单位类型、状态等归属与流转字段不可通过此入口改动；
        已终止单位档案冻结。历史委托与结算记录不在此处触及，保持不变。
        """
        require_permission(operator, "client:update")
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"委托单位 {entry_id} 不存在或已归档"
        if entry.get("status") == "已终止":
            return None, "委托单位已终止，档案已冻结，不能再修改"
        unknown = [field for field in values if field not in PROFILE_FIELDS]
        if unknown:
            return None, f"字段 {'、'.join(unknown)} 不允许通过档案修改入口变更"
        expiry_text = str(values.get("资质有效期至") or "").strip()
        if "资质有效期至" in values and expiry_text and parse_date(expiry_text) is None:
            return None, "资质有效期至格式应为 YYYY-MM-DD"
        audits = entry.setdefault("变更记录", [])
        changed: list[str] = []
        for field in PROFILE_FIELDS:
            if field not in values:
                continue
            new_value = str(values.get(field) or "").strip()
            old_value = str(entry.get(field) or "")
            if new_value == old_value:
                continue
            entry[field] = new_value
            changed.append(field)
            audits.append(self._audit(operator, "修改档案", f"{field}：{old_value or '（空）'} -> {new_value or '（空）'}", field=field, old=old_value, new=new_value))
        if not changed:
            return None, "没有需要变更的字段"
        return serialize(entry, today, with_audit=True), f"已更新档案字段：{'、'.join(changed)}"

    @staticmethod
    def _audit(operator: Operator, action: str, note: str, *, field: str = "", old: str = "", new: str = "") -> dict[str, Any]:
        return {
            "时间": _now(),
            "操作人": operator.name,
            "角色": operator.role,
            "动作": action,
            "字段": field,
            "旧值": old,
            "新值": new,
            "说明": note,
        }
