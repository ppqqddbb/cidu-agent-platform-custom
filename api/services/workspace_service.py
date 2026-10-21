import logging

from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.orm import Session

from configs import dify_config
from enums.cloud_plan import CloudPlan
from models.account import Tenant, TenantAccountJoin, TenantAccountRole
from services.account_service import TenantService
from services.authz import AuthzContextService
from services.authz.authorization_service import AuthorizationService
from services.feature_service import FeatureService

logger = logging.getLogger(__name__)


def _set_credit_pool_info(
    tenant_info: dict[str, object], *, quota_limit: int, quota_used: int, exhausted_at: int | None = None
) -> None:
    tenant_info["trial_credits"] = quota_limit
    tenant_info["trial_credits_used"] = quota_used
    if isinstance(exhausted_at, int) and exhausted_at > 0 and quota_limit > 0 and quota_used >= quota_limit:
        tenant_info["trial_credits_exhausted_at"] = exhausted_at


class WorkspaceService:
    @classmethod
    def get_tenant_info(cls, tenant: Tenant, session: Session):
        if not tenant:
            return None
        tenant_info: dict[str, object] = {
            "id": tenant.id,
            "name": tenant.name,
            "plan": tenant.plan,
            "status": tenant.status,
            "created_at": tenant.created_at,
            "trial_end_reason": None,
            "role": "normal",
            "is_super_admin": False,
            "management_mode": "local_managed",
            "allow_local_member_override": False,
            "capabilities": [],
        }

        # Get role of user
        tenant_account_join = session.scalar(
            select(TenantAccountJoin)
            .where(TenantAccountJoin.tenant_id == tenant.id, TenantAccountJoin.account_id == current_user.id)
            .limit(1)
        )
        assert tenant_account_join is not None, "TenantAccountJoin not found"
        tenant_role = AuthorizationService.normalize_role(tenant_account_join.role) or TenantAccountRole.NORMAL
        tenant_info["role"] = tenant_role.value
        tenant_info["is_super_admin"] = TenantService.is_super_admin(current_user)

        try:
            authz_context = AuthzContextService.get_context(
                account_id=current_user.id,
                tenant_id=tenant.id,
                role=tenant_role,
            )
        except Exception:
            logger.exception(
                "failed to build workspace authorization context: tenant_id=%s account_id=%s",
                tenant.id,
                current_user.id,
            )
            authz_context = None

        if authz_context is not None:
            # 中文注释：`role` 还要继续返回给旧前端和旧接口做兼容展示，
            # 但真正面向后续迁移的鉴权输入已经切到 capability 集合。
            tenant_info["management_mode"] = authz_context.management_mode.value
            tenant_info["allow_local_member_override"] = authz_context.allow_local_member_override
            tenant_info["capabilities"] = authz_context.capabilities

        feature = FeatureService.get_features(tenant.id, exclude_vector_space=True)
        can_replace_logo = feature.can_replace_logo

        if can_replace_logo and TenantService.has_roles(
            tenant, [TenantAccountRole.OWNER, TenantAccountRole.ADMIN], session=session
        ):
            base_url = dify_config.FILES_URL
            replace_webapp_logo = (
                f"{base_url}/files/workspaces/{tenant.id}/webapp-logo"
                if tenant.custom_config_dict.get("replace_webapp_logo")
                else None
            )
            remove_webapp_brand = tenant.custom_config_dict.get("remove_webapp_brand", False)

            tenant_info["custom_config"] = {
                "remove_webapp_brand": remove_webapp_brand,
                "replace_webapp_logo": replace_webapp_logo,
            }
        if dify_config.EDITION == "CLOUD":
            tenant_info["next_credit_reset_date"] = feature.next_credit_reset_date

            from services.credit_pool_service import CreditPoolBalance, CreditPoolService

            paid_pool = CreditPoolService.get_pool(tenant_id=tenant.id, pool_type="paid", session=session)
            # if the tenant is not on the sandbox plan and the paid pool is not full, use the paid pool
            if (
                feature.billing.subscription.plan != CloudPlan.SANDBOX
                and paid_pool is not None
                and (paid_pool.quota_limit == -1 or paid_pool.quota_limit > paid_pool.quota_used)
            ):
                exhausted_at = paid_pool.exhausted_at if isinstance(paid_pool, CreditPoolBalance) else None
                _set_credit_pool_info(
                    tenant_info,
                    quota_limit=paid_pool.quota_limit,
                    quota_used=paid_pool.quota_used,
                    exhausted_at=exhausted_at,
                )
            else:
                trial_pool = CreditPoolService.get_pool(tenant_id=tenant.id, pool_type="trial", session=session)
                if trial_pool:
                    exhausted_at = trial_pool.exhausted_at if isinstance(trial_pool, CreditPoolBalance) else None
                    _set_credit_pool_info(
                        tenant_info,
                        quota_limit=trial_pool.quota_limit,
                        quota_used=trial_pool.quota_used,
                        exhausted_at=exhausted_at,
                    )

        return tenant_info
