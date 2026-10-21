'use client'

import type { ExternalApp, ExternalAppAuthMode, ExternalAppCallMode } from '@/models/common'
import { type ReactNode, useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAtomValue } from 'jotai'
import { Button } from '@langgenius/dify-ui/button'
import { cn } from '@langgenius/dify-ui/cn'
import {
  Dialog,
  DialogCloseButton,
  DialogContent,
  DialogTitle,
} from '@langgenius/dify-ui/dialog'
import { toast } from '@langgenius/dify-ui/toast'
import Input from '@/app/components/base/input'
import {
  currentWorkspaceAtom,
  isCurrentWorkspaceManagerAtom,
  isCurrentWorkspaceOwnerAtom,
} from '@/context/workspace-state'
import {
  useCreateExternalApp,
  useDeleteExternalApp,
  useExternalAppGovernanceCredentialAlerts,
  useExternalAppGovernanceRiskReport,
  useExternalApps,
  useUpdateExternalApp,
} from '@/service/use-external-app-management'

type AuthModeLabelKey =
  | 'externalApp.authModeNone'
  | 'externalApp.authModeStaticBearer'
  | 'externalApp.authModeOAuth2ClientCredentials'
  | 'externalApp.authModeOAuth2AuthorizationCode'
  | 'externalApp.authModeCustom'

type CallModeLabelKey =
  | 'externalApp.callModeGateway'
  | 'externalApp.callModeDirect'

type AppModalMode = 'create' | 'edit' | null

type AppFormState = {
  name: string
  description: string
  purpose: string
  callMode: ExternalAppCallMode
  authMode: ExternalAppAuthMode
  baseUrl: string
  bearerToken: string
  isEnabled: boolean
}

const AUTH_MODE_OPTIONS: Array<{ value: ExternalAppAuthMode, labelKey: AuthModeLabelKey }> = [
  { value: 'none', labelKey: 'externalApp.authModeNone' },
  { value: 'static_bearer', labelKey: 'externalApp.authModeStaticBearer' },
  { value: 'oauth2_client_credentials', labelKey: 'externalApp.authModeOAuth2ClientCredentials' },
  { value: 'oauth2_authorization_code', labelKey: 'externalApp.authModeOAuth2AuthorizationCode' },
  { value: 'custom', labelKey: 'externalApp.authModeCustom' },
]

const CALL_MODE_OPTIONS: Array<{ value: ExternalAppCallMode, labelKey: CallModeLabelKey }> = [
  { value: 'gateway', labelKey: 'externalApp.callModeGateway' },
  { value: 'direct', labelKey: 'externalApp.callModeDirect' },
]

const PAGE_SIZE_OPTIONS = [10, 20, 50]
const CREDENTIAL_ALERT_WITHIN_HOURS_OPTIONS = [24, 72, 168, 720]

const EMPTY_FORM: AppFormState = {
  name: '',
  description: '',
  purpose: '',
  callMode: 'gateway',
  authMode: 'none',
  baseUrl: '',
  bearerToken: '',
  isEnabled: true,
}

const buildAuthConfig = (
  baseUrl: string,
  bearerToken: string,
  mode: ExternalAppAuthMode,
  callMode: ExternalAppCallMode,
) => {
  const config: Record<string, string> = {}
  const normalizedBaseUrl = baseUrl.trim()
  if (normalizedBaseUrl)
    config.base_url = normalizedBaseUrl
  config.call_mode = callMode

  if (mode === 'static_bearer') {
    const normalizedToken = bearerToken.trim()
    if (normalizedToken)
      config.token = normalizedToken
  }

  return config
}

const formatUnixTimestamp = (timestamp: number | null | undefined): string => {
  if (!timestamp)
    return '-'

  return new Date(timestamp * 1000).toLocaleString()
}

const formatRemainingSeconds = (remainingSeconds: number): string => {
  if (remainingSeconds <= 0)
    return '0m'

  const totalMinutes = Math.ceil(remainingSeconds / 60)
  const days = Math.floor(totalMinutes / (24 * 60))
  const hours = Math.floor((totalMinutes % (24 * 60)) / 60)
  const minutes = totalMinutes % 60

  if (days > 0)
    return `${days}d ${hours}h`
  if (hours > 0)
    return `${hours}h ${minutes}m`
  return `${minutes}m`
}

const mapAppToForm = (app: ExternalApp): AppFormState => ({
  name: app.name,
  description: app.description ?? '',
  purpose: app.app_purpose ?? '',
  callMode: app.call_mode,
  authMode: app.auth_mode,
  baseUrl: typeof app.auth_config?.base_url === 'string' ? app.auth_config.base_url : '',
  bearerToken: typeof app.auth_config?.token === 'string' ? app.auth_config.token : '',
  isEnabled: app.is_enabled,
})

const ModalFieldLabel = ({ children, required = false }: { children: ReactNode, required?: boolean }) => (
  <div className="mb-1 system-xs-medium-uppercase text-text-tertiary">
    {children}
    {required && <span className="ml-1 text-red-500">*</span>}
  </div>
)

const ExternalAppManagementPage = () => {
  const { t: rawT } = useTranslation()
  const t = useCallback(
    (key: string, options?: Record<string, unknown>) =>
      (rawT as unknown as (key: string, options?: Record<string, unknown>) => string)(key, options),
    [rawT],
  )
  const currentWorkspace = useAtomValue(currentWorkspaceAtom)
  const isCurrentWorkspaceManager = useAtomValue(isCurrentWorkspaceManagerAtom)
  const isCurrentWorkspaceOwner = useAtomValue(isCurrentWorkspaceOwnerAtom)
  const workspaceCapabilities = currentWorkspace.capabilities ?? []
  const isCurrentWorkspaceSuperAdmin = currentWorkspace.is_super_admin === true

  const canManageByRole = isCurrentWorkspaceSuperAdmin === true || isCurrentWorkspaceOwner || isCurrentWorkspaceManager
  const canView = workspaceCapabilities.includes('workspace.view') || canManageByRole
  const canManage = workspaceCapabilities.includes('workspace.settings.update') || canManageByRole

  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [searchInput, setSearchInput] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [credentialAlertWithinHours, setCredentialAlertWithinHours] = useState(72)

  const appsQuery = useExternalApps({
    page,
    page_size: pageSize,
    query: searchQuery.trim() || undefined,
  }, canView)
  const governanceRiskReportQuery = useExternalAppGovernanceRiskReport(canView)
  const governanceCredentialAlertsQuery = useExternalAppGovernanceCredentialAlerts(credentialAlertWithinHours, canView)

  const createMutation = useCreateExternalApp()
  const updateMutation = useUpdateExternalApp()
  const deleteMutation = useDeleteExternalApp()

  const apps = appsQuery.data?.apps ?? []
  const pagination = appsQuery.data?.pagination
  const totalPages = Math.max(1, Math.ceil((pagination?.total ?? 0) / (pagination?.page_size || pageSize)))
  const governanceRiskSummary = governanceRiskReportQuery.data?.summary
  const governanceRecommendations = governanceRiskReportQuery.data?.gateway_only_recommendations ?? []
  const credentialAlerts = governanceCredentialAlertsQuery.data?.alerts ?? []

  const [modalMode, setModalMode] = useState<AppModalMode>(null)
  const [editingApp, setEditingApp] = useState<ExternalApp | null>(null)
  const [form, setForm] = useState<AppFormState>(EMPTY_FORM)

  const isModalOpen = modalMode !== null
  const modalTitle = modalMode === 'create'
    ? t('externalApp.createModalTitle', { ns: 'common' })
    : t('externalApp.editModalTitle', { ns: 'common' })

  const modalConfirmText = modalMode === 'create'
    ? t('externalApp.createAppAction', { ns: 'common' })
    : t('externalApp.saveAppAction', { ns: 'common' })

  const modalSubmitting = createMutation.isPending || updateMutation.isPending

  useEffect(() => {
    if ((pagination?.total ?? 0) > 0 && apps.length === 0 && page > 1)
      setPage(prev => Math.max(1, prev - 1))
  }, [apps.length, page, pagination?.total])

  const authModeMap = useMemo(() => {
    return AUTH_MODE_OPTIONS.reduce<Record<ExternalAppAuthMode, string>>((acc, option) => {
      acc[option.value] = t(option.labelKey, { ns: 'common' })
      return acc
    }, {
      none: '',
      static_bearer: '',
      oauth2_client_credentials: '',
      oauth2_authorization_code: '',
      custom: '',
    })
  }, [t])

  const callModeMap = useMemo(() => {
    return CALL_MODE_OPTIONS.reduce<Record<ExternalAppCallMode, string>>((acc, option) => {
      acc[option.value] = t(option.labelKey, { ns: 'common' })
      return acc
    }, {
      gateway: '',
      direct: '',
    })
  }, [t])

  const riskReasonMap = useMemo(() => {
    return {
      direct_call_mode: t('externalApp.governanceRiskReasonDirectCallMode', { ns: 'common' }),
      required_permissions_present: t('externalApp.governanceRiskReasonPermissionsPresent', { ns: 'common' }),
      write_operation: t('externalApp.governanceRiskReasonWriteOperation', { ns: 'common' }),
      api_not_confirmed: t('externalApp.governanceRiskReasonApiNotConfirmed', { ns: 'common' }),
    }
  }, [t])

  const alertLevelMeta = useMemo(() => {
    return {
      expired: {
        label: t('externalApp.governanceAlertLevelExpired', { ns: 'common' }),
        className: 'bg-red-100 text-red-700',
      },
      critical: {
        label: t('externalApp.governanceAlertLevelCritical', { ns: 'common' }),
        className: 'bg-orange-100 text-orange-700',
      },
      warning: {
        label: t('externalApp.governanceAlertLevelWarning', { ns: 'common' }),
        className: 'bg-yellow-100 text-yellow-700',
      },
      info: {
        label: t('externalApp.governanceAlertLevelInfo', { ns: 'common' }),
        className: 'bg-blue-100 text-blue-700',
      },
    }
  }, [t])

  const closeModal = () => {
    setModalMode(null)
    setEditingApp(null)
    setForm(EMPTY_FORM)
  }

  const openCreateModal = () => {
    setModalMode('create')
    setEditingApp(null)
    setForm(EMPTY_FORM)
  }

  const openEditModal = (app: ExternalApp) => {
    setModalMode('edit')
    setEditingApp(app)
    setForm(mapAppToForm(app))
  }

  const setFormField = <K extends keyof AppFormState>(key: K, value: AppFormState[K]) => {
    setForm(prev => ({
      ...prev,
      [key]: value,
    }))
  }

  const handleApplySearch = () => {
    setPage(1)
    setSearchQuery(searchInput)
  }

  const handleResetSearch = () => {
    setSearchInput('')
    setSearchQuery('')
    setPage(1)
  }

  const handleSubmit = () => {
    const name = form.name.trim()
    if (!name) {
      toast.error(t('externalApp.nameRequired', { ns: 'common' }))
      return
    }

    if (modalMode === 'create') {
      createMutation.mutate({
        name,
        description: form.description.trim() || undefined,
        app_purpose: form.purpose.trim() || undefined,
        call_mode: form.callMode,
        auth_mode: form.authMode,
        auth_config: buildAuthConfig(form.baseUrl, form.bearerToken, form.authMode, form.callMode),
        is_enabled: form.isEnabled,
      }, {
        onSuccess: () => {
          toast.success(t('actionMsg.modifiedSuccessfully', { ns: 'common' }))
          setPage(1)
          closeModal()
        },
        onError: (error) => {
          toast.error(error.message || t('actionMsg.modifiedUnsuccessfully', { ns: 'common' }))
        },
      })
      return
    }

    if (!editingApp)
      return

    updateMutation.mutate({
      appId: editingApp.id,
      body: {
        name,
        description: form.description.trim() || undefined,
        app_purpose: form.purpose.trim() || undefined,
        call_mode: form.callMode,
        auth_mode: form.authMode,
        auth_config: buildAuthConfig(form.baseUrl, form.bearerToken, form.authMode, form.callMode),
        is_enabled: form.isEnabled,
      },
    }, {
      onSuccess: () => {
        toast.success(t('actionMsg.modifiedSuccessfully', { ns: 'common' }))
        closeModal()
      },
      onError: (error) => {
        toast.error(error.message || t('actionMsg.modifiedUnsuccessfully', { ns: 'common' }))
      },
    })
  }

  const handleToggleAppEnabled = (item: ExternalApp) => {
    updateMutation.mutate({
      appId: item.id,
      body: {
        is_enabled: !item.is_enabled,
      },
    }, {
      onError: (error) => {
        toast.error(error.message || t('actionMsg.modifiedUnsuccessfully', { ns: 'common' }))
      },
    })
  }

  const handleDeleteApp = (item: ExternalApp) => {
    if (!window.confirm(t('externalApp.deleteConfirm', { ns: 'common', name: item.name })))
      return

    deleteMutation.mutate({
      appId: item.id,
    }, {
      onSuccess: () => {
        toast.success(t('actionMsg.modifiedSuccessfully', { ns: 'common' }))
      },
      onError: (error) => {
        toast.error(error.message || t('actionMsg.modifiedUnsuccessfully', { ns: 'common' }))
      },
    })
  }

  if (!canView) {
    return (
      <div className="rounded-xl border border-divider-subtle bg-components-panel-bg p-4 system-sm-regular text-text-tertiary">
        {t('externalApp.permissionDenied', { ns: 'common' })}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-divider-subtle bg-components-panel-bg p-4">
        <div className="system-md-semibold text-text-primary">{t('externalApp.title', { ns: 'common' })}</div>
        <div className="mt-1 system-sm-regular text-text-tertiary">{t('externalApp.description', { ns: 'common' })}</div>
      </div>

      <div className="rounded-xl border border-divider-subtle bg-components-panel-bg p-4">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-[240px] grow items-center gap-2">
            <Input
              value={searchInput}
              onChange={e => setSearchInput(e.target.value)}
              placeholder={t('externalApp.searchPlaceholder', { ns: 'common' })}
              onKeyDown={(e) => {
                if (e.key === 'Enter')
                  handleApplySearch()
              }}
            />
            <Button variant="secondary" onClick={handleApplySearch}>{t('operation.search', { ns: 'common' })}</Button>
            <Button variant="ghost" onClick={handleResetSearch}>{t('operation.reset', { ns: 'common' })}</Button>
          </div>
          {canManage && (
            <Button variant="primary" onClick={openCreateModal}>
              {t('externalApp.createAppAction', { ns: 'common' })}
            </Button>
          )}
        </div>

        <div className="overflow-x-auto rounded-lg border border-divider-subtle">
          <table className="min-w-full text-left">
            <thead className="bg-components-panel-on-panel-item-bg-hover">
              <tr>
                <th className="px-3 py-2 system-xs-medium-uppercase text-text-tertiary">{t('externalApp.tableName', { ns: 'common' })}</th>
                <th className="px-3 py-2 system-xs-medium-uppercase text-text-tertiary">{t('externalApp.tablePurpose', { ns: 'common' })}</th>
                <th className="px-3 py-2 system-xs-medium-uppercase text-text-tertiary">{t('externalApp.tableCallMode', { ns: 'common' })}</th>
                <th className="px-3 py-2 system-xs-medium-uppercase text-text-tertiary">{t('externalApp.tableAuthMode', { ns: 'common' })}</th>
                <th className="px-3 py-2 system-xs-medium-uppercase text-text-tertiary">{t('externalApp.tableStatus', { ns: 'common' })}</th>
                <th className="px-3 py-2 system-xs-medium-uppercase text-text-tertiary">{t('externalApp.tableApiCount', { ns: 'common' })}</th>
                <th className="px-3 py-2 system-xs-medium-uppercase text-text-tertiary">{t('externalApp.tableUpdatedAt', { ns: 'common' })}</th>
                <th className="w-[220px] px-3 py-2 text-right system-xs-medium-uppercase text-text-tertiary">{t('externalApp.tableActions', { ns: 'common' })}</th>
              </tr>
            </thead>
            <tbody>
              {!appsQuery.isPending && apps.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-3 py-8 text-center system-sm-regular text-text-tertiary">
                    {t('externalApp.emptyApps', { ns: 'common' })}
                  </td>
                </tr>
              )}
              {apps.map(item => (
                <tr key={item.id} className="border-t border-divider-subtle/60">
                  <td className="px-3 py-3 system-sm-medium text-text-primary">{item.name}</td>
                  <td className="px-3 py-3 system-sm-regular text-text-secondary">{item.app_purpose || '-'}</td>
                  <td className="px-3 py-3 system-sm-regular text-text-secondary">{callModeMap[item.call_mode] || item.call_mode}</td>
                  <td className="px-3 py-3 system-sm-regular text-text-secondary">{authModeMap[item.auth_mode] || item.auth_mode}</td>
                  <td className="px-3 py-3">
                    <span
                      className={cn(
                        'inline-flex rounded-md px-2 py-0.5 system-xs-medium',
                        item.is_enabled
                          ? 'bg-green-100 text-green-700'
                          : 'bg-gray-100 text-gray-600',
                      )}
                    >
                      {item.is_enabled
                        ? t('externalApp.statusEnabled', { ns: 'common' })
                        : t('externalApp.statusDisabled', { ns: 'common' })}
                    </span>
                  </td>
                  <td className="px-3 py-3 system-sm-regular text-text-secondary">{item.api_count ?? 0}</td>
                  <td className="px-3 py-3 system-sm-regular text-text-secondary">{formatUnixTimestamp(item.updated_at ?? item.created_at)}</td>
                  <td className="px-3 py-3">
                    {canManage && (
                      <div className="flex items-center justify-end gap-2">
                        <Button
                          size="small"
                          variant="ghost"
                          onClick={() => openEditModal(item)}
                        >
                          {t('operation.edit', { ns: 'common' })}
                        </Button>
                        <Button
                          size="small"
                          variant="ghost"
                          loading={updateMutation.isPending}
                          onClick={() => handleToggleAppEnabled(item)}
                        >
                          {item.is_enabled
                            ? t('externalApp.disableApi', { ns: 'common' })
                            : t('externalApp.enableApi', { ns: 'common' })}
                        </Button>
                        <Button
                          size="small"
                          variant="ghost"
                          tone="destructive"
                          loading={deleteMutation.isPending}
                          onClick={() => handleDeleteApp(item)}
                        >
                          {t('operation.delete', { ns: 'common' })}
                        </Button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {!appsQuery.isPending && (pagination?.total ?? 0) > 0 && (
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <div className="system-xs-regular text-text-tertiary">
              {t('externalApp.paginationSummary', {
                ns: 'common',
                current: page,
                totalPages,
                total: pagination?.total ?? 0,
              })}
            </div>
            <div className="flex items-center gap-2">
              <div className="system-xs-regular text-text-tertiary">{t('externalApp.paginationPageSize', { ns: 'common' })}</div>
              <select
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value))
                  setPage(1)
                }}
                className="rounded-lg border border-divider-subtle bg-components-panel-bg px-2 py-1 system-xs-regular text-text-primary"
              >
                {PAGE_SIZE_OPTIONS.map(size => (
                  <option key={size} value={size}>{size}</option>
                ))}
              </select>
              <Button
                size="small"
                variant="ghost"
                disabled={page <= 1}
                onClick={() => setPage(prev => Math.max(1, prev - 1))}
              >
                {t('externalApp.paginationPrev', { ns: 'common' })}
              </Button>
              <Button
                size="small"
                variant="ghost"
                disabled={!pagination?.has_more}
                onClick={() => setPage(prev => prev + 1)}
              >
                {t('externalApp.paginationNext', { ns: 'common' })}
              </Button>
            </div>
          </div>
        )}
      </div>

      <div className="rounded-xl border border-divider-subtle bg-components-panel-bg p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="system-md-semibold text-text-primary">{t('externalApp.governanceTitle', { ns: 'common' })}</div>
            <div className="mt-1 system-sm-regular text-text-tertiary">{t('externalApp.governanceDescription', { ns: 'common' })}</div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="small"
              variant="ghost"
              loading={governanceRiskReportQuery.isFetching}
              onClick={() => {
                void governanceRiskReportQuery.refetch()
              }}
            >
              {t('externalApp.governanceRefresh', { ns: 'common' })}
            </Button>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-5">
          <div className="rounded-lg border border-divider-subtle px-3 py-2">
            <div className="system-xs-regular text-text-tertiary">{t('externalApp.governanceMetricTotalApps', { ns: 'common' })}</div>
            <div className="mt-1 system-md-semibold text-text-primary">{governanceRiskSummary?.total_apps ?? 0}</div>
          </div>
          <div className="rounded-lg border border-divider-subtle px-3 py-2">
            <div className="system-xs-regular text-text-tertiary">{t('externalApp.governanceMetricTotalApis', { ns: 'common' })}</div>
            <div className="mt-1 system-md-semibold text-text-primary">{governanceRiskSummary?.total_apis ?? 0}</div>
          </div>
          <div className="rounded-lg border border-divider-subtle px-3 py-2">
            <div className="system-xs-regular text-text-tertiary">{t('externalApp.governanceMetricDirectModeApps', { ns: 'common' })}</div>
            <div className="mt-1 system-md-semibold text-orange-700">{governanceRiskSummary?.direct_mode_apps ?? 0}</div>
          </div>
          <div className="rounded-lg border border-divider-subtle px-3 py-2">
            <div className="system-xs-regular text-text-tertiary">{t('externalApp.governanceMetricHighRiskApis', { ns: 'common' })}</div>
            <div className="mt-1 system-md-semibold text-red-700">{governanceRiskSummary?.high_risk_api_candidates ?? 0}</div>
          </div>
          <div className="rounded-lg border border-divider-subtle px-3 py-2">
            <div className="system-xs-regular text-text-tertiary">{t('externalApp.governanceMetricGatewayRecommendations', { ns: 'common' })}</div>
            <div className="mt-1 system-md-semibold text-blue-700">{governanceRiskSummary?.gateway_only_recommendations ?? 0}</div>
          </div>
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-divider-subtle p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="system-sm-semibold text-text-primary">{t('externalApp.governanceRecommendationTitle', { ns: 'common' })}</div>
              <span className="system-xs-regular text-text-tertiary">{governanceRecommendations.length}</span>
            </div>
            <div className="overflow-x-auto rounded-lg border border-divider-subtle/70">
              <table className="min-w-full text-left">
                <thead className="bg-components-panel-on-panel-item-bg-hover">
                  <tr>
                    <th className="px-3 py-2 system-xs-medium-uppercase text-text-tertiary">{t('externalApp.governanceRecommendationApp', { ns: 'common' })}</th>
                    <th className="px-3 py-2 system-xs-medium-uppercase text-text-tertiary">{t('externalApp.governanceRecommendationApi', { ns: 'common' })}</th>
                    <th className="px-3 py-2 system-xs-medium-uppercase text-text-tertiary">{t('externalApp.governanceRecommendationReasons', { ns: 'common' })}</th>
                  </tr>
                </thead>
                <tbody>
                  {!governanceRiskReportQuery.isPending && governanceRecommendations.length === 0 && (
                    <tr>
                      <td colSpan={3} className="px-3 py-6 text-center system-sm-regular text-text-tertiary">
                        {t('externalApp.governanceRecommendationEmpty', { ns: 'common' })}
                      </td>
                    </tr>
                  )}
                  {governanceRecommendations.map(item => (
                    <tr key={item.api_id} className="border-t border-divider-subtle/60">
                      <td className="px-3 py-2 system-sm-regular text-text-secondary">{item.app_name}</td>
                      <td className="px-3 py-2 system-sm-regular text-text-secondary">{item.http_method} {item.path}</td>
                      <td className="px-3 py-2">
                        <div className="flex flex-wrap gap-1">
                          {item.risk_reasons.map(reason => (
                            <span key={reason} className="inline-flex rounded-md bg-yellow-100 px-2 py-0.5 system-xs-medium text-yellow-700">
                              {riskReasonMap[reason] || reason}
                            </span>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="rounded-lg border border-divider-subtle p-3">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <div className="system-sm-semibold text-text-primary">{t('externalApp.governanceCredentialAlertsTitle', { ns: 'common' })}</div>
              <div className="flex items-center gap-2">
                <div className="system-xs-regular text-text-tertiary">{t('externalApp.governanceCredentialAlertsWithin', { ns: 'common' })}</div>
                <select
                  value={credentialAlertWithinHours}
                  onChange={(e) => {
                    setCredentialAlertWithinHours(Number(e.target.value))
                  }}
                  className="rounded-lg border border-divider-subtle bg-components-panel-bg px-2 py-1 system-xs-regular text-text-primary"
                >
                  {CREDENTIAL_ALERT_WITHIN_HOURS_OPTIONS.map(hours => (
                    <option key={hours} value={hours}>
                      {t('externalApp.governanceCredentialAlertsWithinOption', { ns: 'common', hours })}
                    </option>
                  ))}
                </select>
                <Button
                  size="small"
                  variant="ghost"
                  loading={governanceCredentialAlertsQuery.isFetching}
                  onClick={() => {
                    void governanceCredentialAlertsQuery.refetch()
                  }}
                >
                  {t('externalApp.governanceRefresh', { ns: 'common' })}
                </Button>
              </div>
            </div>
            <div className="overflow-x-auto rounded-lg border border-divider-subtle/70">
              <table className="min-w-full text-left">
                <thead className="bg-components-panel-on-panel-item-bg-hover">
                  <tr>
                    <th className="px-3 py-2 system-xs-medium-uppercase text-text-tertiary">{t('externalApp.governanceCredentialApp', { ns: 'common' })}</th>
                    <th className="px-3 py-2 system-xs-medium-uppercase text-text-tertiary">{t('externalApp.governanceCredentialExpireAt', { ns: 'common' })}</th>
                    <th className="px-3 py-2 system-xs-medium-uppercase text-text-tertiary">{t('externalApp.governanceCredentialRemaining', { ns: 'common' })}</th>
                    <th className="px-3 py-2 system-xs-medium-uppercase text-text-tertiary">{t('externalApp.governanceCredentialLevel', { ns: 'common' })}</th>
                  </tr>
                </thead>
                <tbody>
                  {!governanceCredentialAlertsQuery.isPending && credentialAlerts.length === 0 && (
                    <tr>
                      <td colSpan={4} className="px-3 py-6 text-center system-sm-regular text-text-tertiary">
                        {t('externalApp.governanceCredentialAlertsEmpty', { ns: 'common' })}
                      </td>
                    </tr>
                  )}
                  {credentialAlerts.map(item => (
                    <tr key={`${item.app_id}-${item.credential_expires_at}`} className="border-t border-divider-subtle/60">
                      <td className="px-3 py-2 system-sm-regular text-text-secondary">{item.app_name}</td>
                      <td className="px-3 py-2 system-sm-regular text-text-secondary">{new Date(item.credential_expires_at * 1000).toLocaleString()}</td>
                      <td className="px-3 py-2 system-sm-regular text-text-secondary">
                        {item.remaining_seconds > 0
                          ? formatRemainingSeconds(item.remaining_seconds)
                          : t('externalApp.governanceCredentialExpired', { ns: 'common' })}
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className={cn(
                            'inline-flex rounded-md px-2 py-0.5 system-xs-medium',
                            alertLevelMeta[item.alert_level]?.className ?? 'bg-gray-100 text-gray-600',
                          )}
                        >
                          {alertLevelMeta[item.alert_level]?.label ?? item.alert_level}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      <Dialog
        open={isModalOpen}
        onOpenChange={(open) => {
          if (!open)
            closeModal()
        }}
      >
        <DialogContent className="w-[640px] max-w-[calc(100vw-2rem)] p-0">
          <DialogCloseButton className="right-5 top-5" />
          <div className="border-b border-divider-subtle px-5 py-4 pr-12">
            <DialogTitle className="text-text-primary title-lg-semi-bold">{modalTitle}</DialogTitle>
          </div>
          <div className="space-y-3 px-5 py-4">
            <div>
              <ModalFieldLabel required>{t('externalApp.nameLabel', { ns: 'common' })}</ModalFieldLabel>
              <Input value={form.name} onChange={e => setFormField('name', e.target.value)} />
            </div>
            <div>
              <ModalFieldLabel>{t('externalApp.baseUrlLabel', { ns: 'common' })}</ModalFieldLabel>
              <Input value={form.baseUrl} onChange={e => setFormField('baseUrl', e.target.value)} />
            </div>
            <div>
              <ModalFieldLabel>{t('externalApp.callModeLabel', { ns: 'common' })}</ModalFieldLabel>
              <select
                value={form.callMode}
                onChange={e => setFormField('callMode', e.target.value as ExternalAppCallMode)}
                className="w-full rounded-lg border border-divider-subtle bg-components-panel-bg px-3 py-2 system-sm-regular text-text-primary"
              >
                {CALL_MODE_OPTIONS.map(option => (
                  <option key={option.value} value={option.value}>{t(option.labelKey, { ns: 'common' })}</option>
                ))}
              </select>
              {form.callMode === 'direct' && (
                <div className="mt-1 system-xs-regular text-yellow-700">
                  {t('externalApp.callModeDirectRiskHint', { ns: 'common' })}
                </div>
              )}
            </div>
            <div>
              <ModalFieldLabel required>{t('externalApp.tableAuthMode', { ns: 'common' })}</ModalFieldLabel>
              <select
                value={form.authMode}
                onChange={e => setFormField('authMode', e.target.value as ExternalAppAuthMode)}
                className="w-full rounded-lg border border-divider-subtle bg-components-panel-bg px-3 py-2 system-sm-regular text-text-primary"
              >
                {AUTH_MODE_OPTIONS.map(option => (
                  <option key={option.value} value={option.value}>{t(option.labelKey, { ns: 'common' })}</option>
                ))}
              </select>
            </div>
            {form.authMode === 'static_bearer' && (
              <div>
                <ModalFieldLabel>{t('externalApp.bearerTokenLabel', { ns: 'common' })}</ModalFieldLabel>
                <Input type="password" value={form.bearerToken} onChange={e => setFormField('bearerToken', e.target.value)} />
              </div>
            )}
            <div className="flex items-center justify-between rounded-lg border border-divider-subtle px-3 py-2">
              <div className="system-sm-regular text-text-secondary">{t('externalApp.appEnabled', { ns: 'common' })}</div>
              <button
                type="button"
                className="flex items-center"
                onClick={() => setFormField('isEnabled', !form.isEnabled)}
              >
                <span
                  className={cn(
                    'inline-flex rounded-md px-2 py-0.5 system-xs-medium',
                    form.isEnabled
                      ? 'bg-green-100 text-green-700'
                      : 'bg-gray-100 text-gray-600',
                  )}
                >
                  {form.isEnabled
                    ? t('externalApp.statusEnabled', { ns: 'common' })
                    : t('externalApp.statusDisabled', { ns: 'common' })}
                </span>
              </button>
            </div>
            <div>
              <ModalFieldLabel>{t('externalApp.purposeLabel', { ns: 'common' })}</ModalFieldLabel>
              <textarea
                value={form.purpose}
                onChange={e => setFormField('purpose', e.target.value)}
                className="h-24 w-full rounded-lg border border-divider-subtle bg-components-panel-bg px-3 py-2 system-sm-regular text-text-primary"
              />
            </div>
            <div>
              <ModalFieldLabel>{t('externalApp.descriptionLabel', { ns: 'common' })}</ModalFieldLabel>
              <textarea
                value={form.description}
                onChange={e => setFormField('description', e.target.value)}
                className="h-24 w-full rounded-lg border border-divider-subtle bg-components-panel-bg px-3 py-2 system-sm-regular text-text-primary"
              />
            </div>
          </div>
          <div className="flex justify-end gap-2 border-t border-divider-subtle px-5 py-4">
            <Button variant="secondary" onClick={closeModal}>
              {t('operation.cancel', { ns: 'common' })}
            </Button>
            <Button variant="primary" loading={modalSubmitting} onClick={handleSubmit}>
              {modalConfirmText}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export default ExternalAppManagementPage
