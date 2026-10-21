'use client'

import type { TenantManagementMode } from '@/models/common'
import { useAtomValue } from 'jotai'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@langgenius/dify-ui/button'
import { cn } from '@langgenius/dify-ui/cn'
import { Switch } from '@langgenius/dify-ui/switch'
import { toast } from '@langgenius/dify-ui/toast'
import Input from '@/app/components/base/input'
import { currentWorkspaceAtom } from '@/context/workspace-state'
import {
  useCreateTenantBySuperAdmin,
  useSyncTenantManagement,
  useTenantAdminTenants,
  useTenantManagementInfo,
  useUpdateTenantManagement,
} from '@/service/use-tenant-management'

const formatUnixTimestamp = (timestamp: number | null | undefined): string => {
  if (!timestamp)
    return '-'

  return new Date(timestamp * 1000).toLocaleString()
}

const TenantManagementPage = () => {
  const { t: rawT } = useTranslation()
  const t = useCallback(
    (key: string, options?: Record<string, unknown>) =>
      (rawT as unknown as (key: string, options?: Record<string, unknown>) => string)(key, options),
    [rawT],
  )
  const currentWorkspace = useAtomValue(currentWorkspaceAtom)
  const isCurrentWorkspaceSuperAdmin = currentWorkspace.is_super_admin === true
  const canViewCurrentTenantManagement = isCurrentWorkspaceSuperAdmin === true

  const { data, isPending } = useTenantManagementInfo(canViewCurrentTenantManagement)
  const adminTenantsQuery = useTenantAdminTenants(canViewCurrentTenantManagement)
  const updateMutation = useUpdateTenantManagement()
  const syncMutation = useSyncTenantManagement()
  const createTenantMutation = useCreateTenantBySuperAdmin()

  const [managementMode, setManagementMode] = useState<TenantManagementMode>('local_managed')
  const [allowLocalMemberOverride, setAllowLocalMemberOverride] = useState(false)
  const [externalTenantId, setExternalTenantId] = useState('')
  const [newTenantName, setNewTenantName] = useState('')
  const [newTenantManagementMode, setNewTenantManagementMode] = useState<TenantManagementMode>('local_managed')
  const [newTenantAllowOverride, setNewTenantAllowOverride] = useState(false)
  const [newTenantExternalId, setNewTenantExternalId] = useState('')

  useEffect(() => {
    if (!data)
      return
    setManagementMode(data.management_mode)
    setAllowLocalMemberOverride(data.allow_local_member_override)
    setExternalTenantId(data.external_tenant_binding?.external_tenant_id ?? '')
  }, [data])

  const canManage = canViewCurrentTenantManagement
  const canSync = canManage && !!data?.has_external_binding
  const adminTenants = adminTenantsQuery.data?.tenants ?? []

  const handleSave = () => {
    if (managementMode === 'external_managed' && !externalTenantId.trim()) {
      toast.error(t('tenantManagement.externalTenantIdRequired', { ns: 'common' }))
      return
    }

    updateMutation.mutate({
      management_mode: managementMode,
      allow_local_member_override: allowLocalMemberOverride,
      external_tenant_id: externalTenantId.trim() || undefined,
    }, {
      onSuccess: () => {
        toast.success(t('actionMsg.modifiedSuccessfully', { ns: 'common' }))
      },
      onError: (error) => {
        toast.error(error.message || t('actionMsg.modifiedUnsuccessfully', { ns: 'common' }))
      },
    })
  }

  const handleSync = () => {
    syncMutation.mutate(undefined, {
      onSuccess: () => {
        toast.success(t('tenantManagement.syncSuccess', { ns: 'common' }))
      },
      onError: (error) => {
        toast.error(error.message || t('tenantManagement.syncFailed', { ns: 'common' }))
      },
    })
  }

  const handleCreateTenant = () => {
    const tenantName = newTenantName.trim()
    const tenantExternalId = newTenantExternalId.trim()
    if (!tenantName) {
      toast.error(t('errorMsg.fieldRequired', { ns: 'common', field: t('tenantManagement.adminNameLabel', { ns: 'common' }) }))
      return
    }
    if (newTenantManagementMode === 'external_managed' && !tenantExternalId) {
      toast.error(t('tenantManagement.externalTenantIdRequired', { ns: 'common' }))
      return
    }

    createTenantMutation.mutate({
      name: tenantName,
      management_mode: newTenantManagementMode,
      allow_local_member_override: newTenantManagementMode === 'external_managed' ? newTenantAllowOverride : false,
      external_tenant_id: tenantExternalId || undefined,
    }, {
      onSuccess: () => {
        toast.success(t('tenantManagement.adminCreateSuccess', { ns: 'common' }))
        setNewTenantName('')
        setNewTenantManagementMode('local_managed')
        setNewTenantAllowOverride(false)
        setNewTenantExternalId('')
      },
      onError: (error) => {
        toast.error(error.message || t('actionMsg.modifiedUnsuccessfully', { ns: 'common' }))
      },
    })
  }

  if (!canViewCurrentTenantManagement) {
    return (
      <div className="rounded-xl border border-divider-subtle bg-components-panel-bg p-4 system-sm-regular text-text-tertiary">
        {t('tenantManagement.permissionDenied', { ns: 'common' })}
      </div>
    )
  }

  if (isPending) {
    return (
      <div className="rounded-xl border border-divider-subtle bg-components-panel-bg p-4 system-sm-regular text-text-tertiary">
        {t('loading', { ns: 'common' })}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {isCurrentWorkspaceSuperAdmin && (
        <div className="rounded-xl border border-divider-subtle bg-components-panel-bg p-4">
          <div className="system-md-semibold text-text-primary">{t('tenantManagement.adminTitle', { ns: 'common' })}</div>
          <div className="mt-1 system-sm-regular text-text-tertiary">{t('tenantManagement.adminDescription', { ns: 'common' })}</div>

          <div className="mt-4 rounded-xl border border-divider-subtle p-3">
            <div className="system-sm-medium text-text-primary">{t('tenantManagement.adminCreateTitle', { ns: 'common' })}</div>
            <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
              <div>
                <div className="mb-1 system-xs-medium-uppercase text-text-tertiary">{t('tenantManagement.adminNameLabel', { ns: 'common' })}</div>
                <Input
                  value={newTenantName}
                  onChange={e => setNewTenantName(e.target.value)}
                  placeholder={t('tenantManagement.adminNamePlaceholder', { ns: 'common' })}
                />
              </div>
              <div>
                <div className="mb-1 system-xs-medium-uppercase text-text-tertiary">{t('tenantManagement.modeLabel', { ns: 'common' })}</div>
                <div className="inline-flex rounded-lg border border-divider-subtle p-1">
                  {(['local_managed', 'external_managed'] as TenantManagementMode[]).map(mode => (
                    <button
                      key={mode}
                      type="button"
                      className={cn(
                        'rounded-md px-3 py-1.5 system-sm-medium text-text-secondary',
                        newTenantManagementMode === mode && 'bg-state-base-active text-components-menu-item-text-active',
                      )}
                      onClick={() => {
                        setNewTenantManagementMode(mode)
                        if (mode === 'local_managed')
                          setNewTenantAllowOverride(false)
                      }}
                    >
                      {mode === 'local_managed'
                        ? t('tenantManagement.modeLocal', { ns: 'common' })
                        : t('tenantManagement.modeExternal', { ns: 'common' })}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <div className="mb-1 system-xs-medium-uppercase text-text-tertiary">{t('tenantManagement.externalTenantIdLabel', { ns: 'common' })}</div>
                <Input
                  value={newTenantExternalId}
                  onChange={e => setNewTenantExternalId(e.target.value)}
                  placeholder={t('tenantManagement.externalTenantIdPlaceholder', { ns: 'common' })}
                />
              </div>
              <div className="flex items-center justify-between rounded-lg border border-divider-subtle p-3">
                <div>
                  <div className="system-sm-medium text-text-primary">{t('tenantManagement.allowOverrideLabel', { ns: 'common' })}</div>
                  <div className="mt-0.5 system-xs-regular text-text-tertiary">{t('tenantManagement.allowOverrideDesc', { ns: 'common' })}</div>
                </div>
                <Switch
                  checked={newTenantAllowOverride}
                  onCheckedChange={setNewTenantAllowOverride}
                  disabled={newTenantManagementMode !== 'external_managed'}
                  aria-label={t('tenantManagement.allowOverrideLabel', { ns: 'common' })}
                />
              </div>
            </div>
            <div className="mt-3">
              <Button
                variant="primary"
                loading={createTenantMutation.isPending}
                onClick={handleCreateTenant}
              >
                {t('tenantManagement.adminCreateAction', { ns: 'common' })}
              </Button>
            </div>
          </div>

          <div className="mt-4 rounded-xl border border-divider-subtle p-3">
            <div className="mb-3 system-sm-medium text-text-primary">{t('tenantManagement.adminListTitle', { ns: 'common' })}</div>
            {adminTenantsQuery.isPending && (
              <div className="system-sm-regular text-text-tertiary">{t('loading', { ns: 'common' })}</div>
            )}
            {!adminTenantsQuery.isPending && adminTenants.length === 0 && (
              <div className="system-sm-regular text-text-tertiary">{t('noData', { ns: 'common' })}</div>
            )}
            {!adminTenantsQuery.isPending && adminTenants.length > 0 && (
              <div className="overflow-x-auto">
                <table className="min-w-full text-left">
                  <thead>
                    <tr className="border-b border-divider-subtle">
                      <th className="px-2 py-2 system-xs-medium-uppercase text-text-tertiary">{t('tenantManagement.adminTableName', { ns: 'common' })}</th>
                      <th className="px-2 py-2 system-xs-medium-uppercase text-text-tertiary">{t('tenantManagement.adminTableMode', { ns: 'common' })}</th>
                      <th className="px-2 py-2 system-xs-medium-uppercase text-text-tertiary">{t('tenantManagement.adminTableExternalTenantId', { ns: 'common' })}</th>
                      <th className="px-2 py-2 system-xs-medium-uppercase text-text-tertiary">{t('tenantManagement.adminTableMembers', { ns: 'common' })}</th>
                      <th className="px-2 py-2 system-xs-medium-uppercase text-text-tertiary">{t('tenantManagement.adminTableCreatedAt', { ns: 'common' })}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {adminTenants.map(tenant => (
                      <tr key={tenant.id} className="border-b border-divider-subtle/60">
                        <td className="px-2 py-2 system-sm-regular text-text-secondary">
                          <div className="flex items-center gap-2">
                            <span>{tenant.name}</span>
                            {tenant.is_default_tenant && (
                              <span className="rounded-md bg-state-accent-hover px-1.5 py-0.5 system-2xs-medium-uppercase text-text-accent">
                                {t('tenantManagement.adminDefaultBadge', { ns: 'common' })}
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-2 py-2 system-sm-regular text-text-secondary">
                          {tenant.management_mode === 'external_managed'
                            ? t('tenantManagement.modeExternal', { ns: 'common' })
                            : t('tenantManagement.modeLocal', { ns: 'common' })}
                        </td>
                        <td className="px-2 py-2 system-sm-regular text-text-secondary">{tenant.external_tenant_id || '-'}</td>
                        <td className="px-2 py-2 system-sm-regular text-text-secondary">{tenant.member_count}</td>
                        <td className="px-2 py-2 system-sm-regular text-text-secondary">{formatUnixTimestamp(tenant.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="rounded-xl border border-divider-subtle bg-components-panel-bg p-4">
        <div className="system-md-semibold text-text-primary">{t('tenantManagement.title', { ns: 'common' })}</div>
        <div className="mt-1 system-sm-regular text-text-tertiary">{t('tenantManagement.description', { ns: 'common' })}</div>

        <div className="mt-4">
          <div className="mb-1 system-xs-medium-uppercase text-text-tertiary">{t('tenantManagement.modeLabel', { ns: 'common' })}</div>
          <div className="inline-flex rounded-lg border border-divider-subtle p-1">
            {(['local_managed', 'external_managed'] as TenantManagementMode[]).map(mode => (
              <button
                key={mode}
                type="button"
                className={cn(
                  'rounded-md px-3 py-1.5 system-sm-medium text-text-secondary',
                  managementMode === mode && 'bg-state-base-active text-components-menu-item-text-active',
                )}
                disabled={!canManage}
                onClick={() => setManagementMode(mode)}
              >
                {mode === 'local_managed'
                  ? t('tenantManagement.modeLocal', { ns: 'common' })
                  : t('tenantManagement.modeExternal', { ns: 'common' })}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-4">
          <div className="mb-1 system-xs-medium-uppercase text-text-tertiary">{t('tenantManagement.externalTenantIdLabel', { ns: 'common' })}</div>
          <Input
            value={externalTenantId}
            onChange={e => setExternalTenantId(e.target.value)}
            placeholder={t('tenantManagement.externalTenantIdPlaceholder', { ns: 'common' })}
            disabled={!canManage}
          />
        </div>

        <div className="mt-4 flex items-center justify-between rounded-lg border border-divider-subtle p-3">
          <div>
            <div className="system-sm-medium text-text-primary">{t('tenantManagement.allowOverrideLabel', { ns: 'common' })}</div>
            <div className="mt-0.5 system-xs-regular text-text-tertiary">{t('tenantManagement.allowOverrideDesc', { ns: 'common' })}</div>
          </div>
          <Switch
            checked={allowLocalMemberOverride}
            onCheckedChange={setAllowLocalMemberOverride}
            disabled={!canManage || managementMode !== 'external_managed'}
            aria-label={t('tenantManagement.allowOverrideLabel', { ns: 'common' })}
          />
        </div>

        <div className="mt-4 flex gap-2">
          <Button
            variant="primary"
            loading={updateMutation.isPending}
            disabled={!canManage}
            onClick={handleSave}
          >
            {t('operation.save', { ns: 'common' })}
          </Button>
          <Button
            variant="secondary"
            loading={syncMutation.isPending}
            disabled={!canSync}
            onClick={handleSync}
          >
            {t('tenantManagement.syncNow', { ns: 'common' })}
          </Button>
        </div>
      </div>

      <div className="rounded-xl border border-divider-subtle bg-components-panel-bg p-4">
        <div className="system-md-semibold text-text-primary">{t('tenantManagement.bindingTitle', { ns: 'common' })}</div>
        <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
          <div>
            <div className="system-xs-medium-uppercase text-text-tertiary">{t('tenantManagement.bindingStatus', { ns: 'common' })}</div>
            <div className="mt-1 system-sm-regular text-text-secondary">
              {data?.has_external_binding
                ? t('tenantManagement.bindingEnabled', { ns: 'common' })
                : t('tenantManagement.bindingDisabled', { ns: 'common' })}
            </div>
          </div>
          <div>
            <div className="system-xs-medium-uppercase text-text-tertiary">{t('tenantManagement.sourceVersion', { ns: 'common' })}</div>
            <div className="mt-1 system-sm-regular text-text-secondary">
              {data?.external_tenant_binding?.source_version ?? '-'}
            </div>
          </div>
          <div>
            <div className="system-xs-medium-uppercase text-text-tertiary">{t('tenantManagement.lastSyncedAt', { ns: 'common' })}</div>
            <div className="mt-1 system-sm-regular text-text-secondary">
              {formatUnixTimestamp(data?.external_tenant_binding?.last_synced_at)}
            </div>
          </div>
          <div>
            <div className="system-xs-medium-uppercase text-text-tertiary">{t('tenantManagement.currentMode', { ns: 'common' })}</div>
            <div className="mt-1 system-sm-regular text-text-secondary">
              {data?.management_mode === 'external_managed'
                ? t('tenantManagement.modeExternal', { ns: 'common' })
                : t('tenantManagement.modeLocal', { ns: 'common' })}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default TenantManagementPage
