"""委托单位业务规则：状态流转、资质到期口径、敏感字段变更审计都收在这里。

几条硬规则：
- 单位编码是历史委托与结算记录的归属锚点，一经登记不允许修改、不允许重复；
- 已暂停 / 已终止 / 资质过期的单位，在任何入口都不能登记新的检测委托；
- 资质有效期至按到期日口径判定：到期日当天仍有效，次日零点起算过期；
- 资质编号、结算方式等敏感字段只能由管理员变更，且每一次变更都留审计记录；
- 列表与详情共用同一个序列化出口，看到的状态必然一致。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.services.permission import ROLE_ADMIN, Operator
from app.store import store

MODULE = "client"
AUDIT_MODULE = "client_audit"
REQUIRED_FIELDS = ["单位编码", "单位名称", "单位类型"]
PROFILE_FIELDS = ["单位名称", "单位类型", "联系人", "联系电话"]
SENSITIVE_FIELDS = ["结算方式", "资质编号", "资质有效期至"]
STATUS_ORDER = ["待审核", "合作中", "已暂停", "已终止"]
EXPIRED_STATUS = "资质过期"
TERMINAL_STATUS = "已终止"
# 动作 -> (目标状态, 允许发起的当前状态集合)。已终止是终态，任何动作都拉不回来。
ACTION_RULES: dict[str, tuple[str, set[str]]] = {
    "审核单位": ("合作中", {"待审核"}),
    "暂停合作": ("已暂停", {"合作中"}),
    "恢复合作": ("合作中", {"已暂停"}),
    "终止合作": ("已终止", {"合作中", "已暂停"}),
}


def _today() -> date:
    return date.today()


def parse_date(raw: Any) -> date | None:
    """把入参按 YYYY-MM-DD 解析；解析不了返回 None，由调用方决定怎么报。"""
    try:
        return date.fromisoformat(str(raw or "").strip()[:10])
    except ValueError:
        return None


def qualification_expired(entry: dict[str, Any], today: date | None = None) -> bool:
    """资质是否过期：有有效期且到期日早于今天。到期日当天仍算有效。"""
    expiry = parse_date(entry.get("资质有效期至"))
    return bool(expiry and expiry < (today or _today()))


def effective_status(entry: dict[str, Any], today: date | None = None) -> str:
    """展示口径的状态：合作中但资质已过期的单位，对外一律显示资质过期。"""
    status = str(entry.get("status") or "")
    if status == "合作中" and qualification_expired(entry, today):
        return EXPIRED_STATUS
    return status


def find_client(key: Any) -> dict[str, Any] | None:
    """按单位编码或单位名称定位单位；编码优先，保证归属唯一。"""
    key = str(key or "").strip()
    if not key:
        return None
    for row in store.rows(MODULE):
        if key == str(row.get("单位编码") or ""):
            return row
    for row in store.rows(MODULE):
        if key == str(row.get("单位名称") or ""):
            return row
    return None


def commission_block(entry: dict[str, Any]) -> str | None:
    """新委托拦截口径：返回 None 表示可委托，否则返回可读的拦截原因。"""
    code = entry.get("单位编码")
    status = str(entry.get("status") or "")
    if status == "已终止":
        return f"单位 {code} 已终止合作，任何入口都不能再登记新的检测委托"
    if status == "已暂停":
        return f"单位 {code} 已暂停合作，恢复合作前不能登记新的检测委托"
    if status == "待审核":
        return f"单位 {code} 尚未通过审核，不能登记检测委托"
    if qualification_expired(entry):
        return (
            f"单位 {code} 的资质编号 {entry.get('资质编号') or '（空）'} "
            f"已于 {entry.get('资质有效期至')} 到期，需更新资质并审核后才能继续委托"
        )
    return None


class ClientService:
    def _serialize(self, entry: dict[str, Any], operator: Operator | None = None) -> dict[str, Any]:
        """列表、详情、导出共用的出口：状态与可操作范围在这里一次算清。"""
        row = dict(entry)
        row["单位状态"] = effective_status(entry)
        block = commission_block(entry)
        row["可委托"] = block is None
        row["拦截原因"] = block
        row["可用动作"] = self.allowed_actions(entry, operator)
        return row

    def allowed_actions(self, entry: dict[str, Any], operator: Operator | None) -> list[str]:
        """当前操作员在这条记录上能执行的动作；非管理员一律为空，与后端拦截口径一致。"""
        if operator is None or operator.role != ROLE_ADMIN:
            return []
        current = str(entry.get("status") or "")
        return [action for action, (_, sources) in ACTION_RULES.items() if current in sources]

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
        operator: Operator | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("单位编码", ""))]
        if status:
            # 状态过滤按展示口径走：筛“资质过期”能命中，筛“合作中”不会混入过期单位。
            rows = [row for row in rows if effective_status(row) == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._serialize(row, operator) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int, operator: Operator | None = None) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return self._serialize(entry, operator)

    def create_entry(
        self, values: dict[str, Any], operator: Operator
    ) -> tuple[dict[str, Any] | None, str | None]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        code = str(values.get("单位编码") or "").strip()
        if find_client(code):
            return None, f"单位编码 {code} 已存在，同一单位不能重复登记"
        expiry = str(values.get("资质有效期至") or "").strip()
        if expiry and parse_date(expiry) is None:
            return None, "资质有效期至 需为 YYYY-MM-DD 格式的日期"
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in REQUIRED_FIELDS + PROFILE_FIELDS + SENSITIVE_FIELDS:
            value = values.get(field)
            if value is not None and str(value).strip() != "":
                entry[field] = str(value).strip()
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        self._record(entry, operator, "登记单位", "单位状态", None, entry["status"])
        return self._serialize(entry, operator), None

    def update_entry(
        self, entry_id: int, values: dict[str, Any], operator: Operator
    ) -> tuple[dict[str, Any] | None, str | None]:
        """变更单位资料：逐字段留审计记录；历史委托与结算记录保持原样不动。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"委托单位 {entry_id} 不存在或已归档"
        if entry.get("status") == TERMINAL_STATUS:
            return None, f"单位 {entry.get('单位编码')} 已终止合作，档案已封存，不能再修改"
        if "单位编码" in values and str(values["单位编码"] or "").strip() != str(entry.get("单位编码")):
            return None, "单位编码是历史委托与结算记录的归属锚点，不允许修改"
        changed: list[tuple[str, Any, Any]] = []
        for field in PROFILE_FIELDS + SENSITIVE_FIELDS:
            if field not in values:
                continue
            new = str(values.get(field) or "").strip()
            old = str(entry.get(field) or "").strip()
            if new != old:
                changed.append((field, old, new))
        if not changed:
            return None, "没有需要变更的字段"
        for field, _, new in changed:
            if field == "资质有效期至" and new and parse_date(new) is None:
                return None, "资质有效期至 需为 YYYY-MM-DD 格式的日期"
        for field, old, new in changed:
            entry[field] = new
            self._record(entry, operator, "变更资料", field, old, new)
        return self._serialize(entry, operator), f"已变更 {'、'.join(field for field, _, _ in changed)}，变更记录已留存"

    def run_action(
        self, entry_id: int, action: str, operator: Operator
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"委托单位 {entry_id} 不存在或已归档"
        rule = ACTION_RULES.get(action)
        if rule is None:
            return None, f"动作「{action}」不属于委托单位可执行范围"
        target, sources = rule
        current = str(entry.get("status") or "")
        if current not in sources:
            shown = effective_status(entry)
            return None, (
                f"当前状态「{shown}」不允许执行「{action}」，"
                f"仅 {'、'.join(s for s in STATUS_ORDER if s in sources)} 状态可执行"
            )
        entry["status"] = target
        entry["pending"] = target != TERMINAL_STATUS
        entry["abnormal"] = False
        self._record(entry, operator, action, "单位状态", current, target)
        return self._serialize(entry, operator), f"委托单位已{action}"

    def list_audits(self, entry_id: int) -> list[dict[str, Any]] | None:
        """单条单位的变更履历：谁、什么时候、把哪个字段从什么改成什么。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        code = str(entry.get("单位编码") or "")
        records = [row for row in store.rows(AUDIT_MODULE) if str(row.get("单位编码") or "") == code]
        return sorted(records, key=lambda row: str(row.get("操作时间") or ""), reverse=True)

    def _record(
        self,
        entry: dict[str, Any],
        operator: Operator,
        action: str,
        field: str | None,
        old: Any,
        new: Any,
    ) -> None:
        rows = store.rows(AUDIT_MODULE)
        rows.append({
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "单位编码": entry.get("单位编码"),
            "单位名称": entry.get("单位名称"),
            "动作": action,
            "字段": field,
            "旧值": old,
            "新值": new,
            "操作人": operator.name,
            "操作角色": operator.role,
            "操作时间": datetime.now().isoformat(timespec="seconds"),
        })
