"""Authorization helpers for capability-based workspace access control."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol

from werkzeug.exceptions import Forbidden

from models.account import TenantAccountRole


class CapabilityContext(Protocol):
    capabilities: list[str]


def _merge_capabilities(*groups: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({capability for group in groups for capability in group}))


WORKSPACE_BASE_CAPABILITIES = (
    "workspace.view",
    "workspace.switch",
    "workspace.member.list",
)

# 中文注释：这里先按“尽量不收紧旧权限”的原则冻结 role -> capability 映射，
# 这样 Phase 2 把鉴权入口切到 capability 时，不会因为映射过窄先引入行为回归。
NORMAL_CAPABILITIES = _merge_capabilities(
    WORKSPACE_BASE_CAPABILITIES,
    (
        "app.read",
        "workflow.read",
        "dataset.list",
        "dataset.read",
        "model_provider.read",
        "plugin.read",
        "workspace.file.manage",
    ),
)

EDITOR_CAPABILITIES = _merge_capabilities(
    NORMAL_CAPABILITIES,
    (
        "app.create",
        "app.update",
        "app.delete",
        "app.copy",
        "app.export",
        "app.publish",
        "app.api.manage",
        "app.site.manage",
        "app.site.token.reset",
        "workflow.write",
        "workflow.debug.run",
        "workflow.publish",
        "dataset.create",
        "dataset.update",
        "dataset.delete",
        "dataset.permission.manage",
        "dataset.document.manage",
        "dataset.api_key.read",
        "dataset.api_key.create",
        "dataset.api_key.delete",
        "workspace.file.manage",
    ),
)

DATASET_OPERATOR_CAPABILITIES = _merge_capabilities(
    WORKSPACE_BASE_CAPABILITIES,
    (
        "dataset.list",
        "dataset.read",
        "dataset.update",
        "dataset.permission.manage",
        "dataset.document.manage",
        "dataset.api_key.read",
        "plugin.read",
        "model_provider.read",
    ),
)

ADMIN_CAPABILITIES = _merge_capabilities(
    EDITOR_CAPABILITIES,
    (
        "workspace.settings.update",
        "workspace.branding.update",
        "workspace.member.invite",
        "workspace.member.remove",
        "workspace.member.role.update",
        "model_provider.credential.manage",
        "model_provider.preference.manage",
        "plugin.install",
        "plugin.debug",
        "plugin.policy.manage",
        "plugin.preference.manage",
    ),
)

OWNER_CAPABILITIES = _merge_capabilities(
    ADMIN_CAPABILITIES,
    (
        "workspace.member.remove",
        "workspace.member.role.update",
        "workspace.owner.transfer",
    ),
)


class AuthorizationService:
    """Translate legacy roles into capabilities and evaluate capability checks."""

    # 中文注释：过渡期里 `TenantAccountJoin.role` 只作为兼容输入，
    # 统一先映射成 capability，再让控制器和后续新接口按 capability 判定。
    ROLE_CAPABILITY_MAP: dict[TenantAccountRole, tuple[str, ...]] = {
        TenantAccountRole.OWNER: OWNER_CAPABILITIES,
        TenantAccountRole.ADMIN: ADMIN_CAPABILITIES,
        TenantAccountRole.EDITOR: EDITOR_CAPABILITIES,
        TenantAccountRole.NORMAL: NORMAL_CAPABILITIES,
        TenantAccountRole.DATASET_OPERATOR: DATASET_OPERATOR_CAPABILITIES,
    }

    @staticmethod
    def normalize_role(role: TenantAccountRole | str | None) -> TenantAccountRole | None:
        if role is None:
            return None
        if isinstance(role, TenantAccountRole):
            return role
        try:
            return TenantAccountRole(role)
        except ValueError:
            return None

    @classmethod
    def normalize_capabilities(cls, capabilities: Sequence[str] | None) -> list[str]:
        if not capabilities:
            return []
        return sorted({capability.strip() for capability in capabilities if capability and capability.strip()})

    @classmethod
    def get_capabilities_for_role(cls, role: TenantAccountRole | str | None) -> list[str]:
        normalized_role = cls.normalize_role(role)
        if normalized_role is None:
            return []
        return list(cls.ROLE_CAPABILITY_MAP.get(normalized_role, ()))

    @classmethod
    def can(cls, context: CapabilityContext, capability: str) -> bool:
        return capability in context.capabilities

    @classmethod
    def can_any(cls, context: CapabilityContext, capabilities: Sequence[str]) -> bool:
        capability_set = set(context.capabilities)
        return any(capability in capability_set for capability in capabilities)

    @classmethod
    def require(cls, context: CapabilityContext, capability: str) -> None:
        if not cls.can(context, capability):
            raise Forbidden()

    @classmethod
    def require_any(cls, context: CapabilityContext, capabilities: Sequence[str]) -> None:
        if not cls.can_any(context, capabilities):
            raise Forbidden()
