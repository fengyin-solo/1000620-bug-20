"""操作员与角色权限：每个写操作都要先过这道闸，越权直接 403 并说明原因。

前端通过 `X-Operator-Name` / `X-Operator-Role` 请求头声明当前操作员；
请求头只能携带拉丁字符，中文按 URL 百分号编码传输，这里负责解码；
未声明或角色无法识别时按最低权限（业务员）处理，绝不默认放行。
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import unquote

from fastapi import Header, HTTPException

ROLE_SALES = "业务员"
ROLE_ADMIN = "管理员"
KNOWN_ROLES = {ROLE_SALES, ROLE_ADMIN}

# 权限点 -> 允许的角色集合。没有列出的权限点默认只有管理员能执行。
PERMISSIONS: dict[str, set[str]] = {
    "client:create": {ROLE_SALES, ROLE_ADMIN},
    "client:update": {ROLE_ADMIN},
    "client:action": {ROLE_ADMIN},
    "sample:create": {ROLE_SALES, ROLE_ADMIN},
    "settlement:create": {ROLE_SALES, ROLE_ADMIN},
}


@dataclass(frozen=True)
class Operator:
    """一次请求的操作员身份：谁、以什么角色在操作。"""

    name: str
    role: str


def get_operator(
    x_operator_name: str | None = Header(default=None),
    x_operator_role: str | None = Header(default=None),
) -> Operator:
    """从请求头解析操作员；角色缺失或不在名册时降级为业务员（最低权限）。"""
    name = unquote((x_operator_name or "").strip()) or "未登记操作员"
    role = unquote((x_operator_role or "").strip())
    if role not in KNOWN_ROLES:
        role = ROLE_SALES
    return Operator(name=name, role=role)


def require(operator: Operator, permission: str) -> None:
    """校验操作员是否持有权限点；越权时抛 403，消息里写清谁被什么拦住。"""
    allowed = PERMISSIONS.get(permission, {ROLE_ADMIN})
    if operator.role not in allowed:
        raise HTTPException(
            status_code=403,
            detail=(
                f"操作员「{operator.name}」（{operator.role}）无权执行该操作，"
                f"需要角色：{'、'.join(sorted(allowed))}"
            ),
        )
