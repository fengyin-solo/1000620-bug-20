"""操作角色与权限：所有需要鉴权的业务入口共用这一套口径。

角色由前端会话通过请求头携带（非 ASCII 值按 URL 百分号编码传输），
路由层只负责解析并传给服务层；越权时抛出 PermissionDenied，由路由层转成 403，绝不静默放行。
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import unquote

# 权限点 -> 可读说明，用于拒绝时给出人能看懂的的原因
PERMISSION_LABELS = {
    "client:create": "登记委托单位",
    "client:review": "审核委托单位",
    "client:suspend": "暂停合作",
    "client:terminate": "终止合作",
    "client:update": "修改单位档案（资质编号、结算方式等）",
    "sample:create": "登记检测委托（样品受理）",
    "settlement:create": "登记结算单",
}

# 角色 -> 权限点集合；未在表内的角色没有任何权限
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "业务员": frozenset({"client:create", "sample:create", "settlement:create"}),
    "审核员": frozenset({"client:review"}),
    "管理员": frozenset({
        "client:create",
        "client:review",
        "client:suspend",
        "client:terminate",
        "client:update",
        "sample:create",
        "settlement:create",
    }),
}


class PermissionDenied(PermissionError):
    """当前角色无权执行目标操作。"""


@dataclass(frozen=True)
class Operator:
    """一次操作的责任人：谁（姓名）、以什么角色操作。"""

    name: str
    role: str


def resolve_operator(role: str | None, name: str | None) -> Operator:
    """把请求头里的角色与姓名整理成 Operator；缺省时给可读占位，方便审计追溯。

    请求头只允许 ASCII，中文角色名按 URL 百分号编码传输，这里统一解码。
    """
    return Operator(
        name=unquote((name or "").strip()) or "未登记操作员",
        role=unquote((role or "").strip()),
    )


def require_permission(operator: Operator, permission: str) -> None:
    """校验角色是否持有权限点；不持有就抛出 PermissionDenied 并说明缺什么权限。"""
    if permission in ROLE_PERMISSIONS.get(operator.role, frozenset()):
        return
    label = PERMISSION_LABELS.get(permission, permission)
    role = operator.role or "未识别"
    raise PermissionDenied(f"角色「{role}」无权{label}，请换用有权限的角色或联系管理员")
