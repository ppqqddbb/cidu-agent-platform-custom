'use client'

import type { ExternalAppApi } from '@/models/common'
import { type ReactNode, useCallback, useEffect, useState } from 'react'
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
import { Switch } from '@langgenius/dify-ui/switch'
import { toast } from '@langgenius/dify-ui/toast'
import Input from '@/app/components/base/input'
import {
  currentWorkspaceAtom,
  isCurrentWorkspaceManagerAtom,
  isCurrentWorkspaceOwnerAtom,
} from '@/context/workspace-state'
import {
  useCreateExternalAppApi,
  useDeleteExternalAppApi,
  useExternalAppApis,
  useExternalApps,
  useImportExternalAppOpenAPI,
  useUpdateExternalAppApi,
} from '@/service/use-external-app-management'

type ApiModalMode = 'create' | 'edit' | null

type ApiFormState = {
  name: string
  httpMethod: string
  path: string
  baseUrlOverride: string
  purpose: string
  summary: string
  description: string
  isConfirmed: boolean
  isEnabled: boolean
  paramConfig: ApiParamConfig
}

type ApiParamLocation = 'path' | 'query' | 'body' | 'headers'

type ApiParamDefinition = {
  id: string
  enabled: boolean
  name: string
  type: string
  required: boolean
  example: string
  description: string
}

type ApiParamConfig = Record<ApiParamLocation, ApiParamDefinition[]>

const PAGE_SIZE_OPTIONS = [10, 20, 50]
const HTTP_METHOD_OPTIONS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']

const PARAM_SECTION_KEYS: ApiParamLocation[] = ['path', 'query', 'body', 'headers']
const PARAM_TYPE_OPTIONS = ['string', 'number', 'integer', 'boolean', 'array', 'object']

type ApiParamSectionLabelKey =
  | 'externalApi.paramSectionPath'
  | 'externalApi.paramSectionQuery'
  | 'externalApi.paramSectionBody'
  | 'externalApi.paramSectionHeaders'

const PARAM_SECTION_LABEL_KEYS: Record<ApiParamLocation, ApiParamSectionLabelKey> = {
  path: 'externalApi.paramSectionPath',
  query: 'externalApi.paramSectionQuery',
  body: 'externalApi.paramSectionBody',
  headers: 'externalApi.paramSectionHeaders',
}

const createParamId = () => `${Date.now()}-${Math.random().toString(16).slice(2)}`

const createEmptyParamDefinition = (): ApiParamDefinition => ({
  id: createParamId(),
  enabled: true,
  name: '',
  type: 'string',
  required: false,
  example: '',
  description: '',
})

const createEmptyParamConfig = (): ApiParamConfig => ({
  path: [],
  query: [],
  body: [],
  headers: [],
})

const normalizeSchemaValueToInputString = (value: unknown): string => {
  if (value === null || value === undefined)
    return ''
  if (typeof value === 'string')
    return value
  try {
    return JSON.stringify(value)
  }
  catch {
    return String(value)
  }
}

const normalizeParamConfigFromRequestSchema = (requestSchema: Record<string, unknown> | null | undefined): ApiParamConfig => {
  const normalized = createEmptyParamConfig()
  if (!requestSchema || typeof requestSchema !== 'object')
    return normalized

  for (const section of PARAM_SECTION_KEYS) {
    const sectionItems = requestSchema[section]
    if (!Array.isArray(sectionItems))
      continue
    normalized[section] = sectionItems
      .filter(item => item && typeof item === 'object')
      .map((item) => {
        const param = item as Record<string, unknown>
        return {
          id: createParamId(),
          enabled: param.enabled !== false,
          name: typeof param.name === 'string' ? param.name : '',
          type: typeof param.type === 'string' && param.type.trim() ? param.type : 'string',
          required: Boolean(param.required),
          example: normalizeSchemaValueToInputString(param.example),
          description: typeof param.description === 'string' ? param.description : '',
        }
      })
      .filter(item => item.name.trim())
  }

  return normalized
}

const extractBaseUrlOverrideFromRequestSchema = (requestSchema: Record<string, unknown> | null | undefined): string => {
  if (!requestSchema || typeof requestSchema !== 'object')
    return ''

  const rawValue = requestSchema.base_url_override
  if (typeof rawValue !== 'string')
    return ''

  return rawValue.trim()
}

const buildRequestSchemaFromParamConfig = (paramConfig: ApiParamConfig, baseUrlOverride: string): Record<string, unknown> => {
  const schema: Record<string, unknown> = {}

  for (const section of PARAM_SECTION_KEYS) {
    const normalizedItems = paramConfig[section]
      .map(item => ({
        enabled: Boolean(item.enabled),
        name: item.name.trim(),
        type: item.type.trim() || 'string',
        required: Boolean(item.required),
        example: item.example.trim() || undefined,
        description: item.description.trim() || undefined,
      }))
      .filter(item => item.enabled && item.name)
      .map(({ enabled, ...rest }) => rest)
    if (normalizedItems.length > 0)
      schema[section] = normalizedItems
  }

  const normalizedBaseUrlOverride = baseUrlOverride.trim()
  if (normalizedBaseUrlOverride)
    schema.base_url_override = normalizedBaseUrlOverride

  return schema
}

const createEmptyForm = (): ApiFormState => ({
  name: '',
  httpMethod: 'GET',
  path: '',
  baseUrlOverride: '',
  purpose: '',
  summary: '',
  description: '',
  isConfirmed: true,
  isEnabled: true,
  paramConfig: createEmptyParamConfig(),
})

const formatUnixTimestamp = (timestamp: number | null | undefined): string => {
  if (!timestamp)
    return '-'

  return new Date(timestamp * 1000).toLocaleString()
}

const mapApiToForm = (item: ExternalAppApi): ApiFormState => ({
  name: item.name,
  httpMethod: item.http_method,
  path: item.path,
  baseUrlOverride: extractBaseUrlOverrideFromRequestSchema(item.request_schema),
  purpose: item.api_purpose ?? '',
  summary: item.summary ?? '',
  description: item.description ?? '',
  isConfirmed: item.is_confirmed,
  isEnabled: item.is_enabled,
  paramConfig: normalizeParamConfigFromRequestSchema(item.request_schema),
})

const isValidHttpUrl = (value: string): boolean => {
  try {
    const parsed = new URL(value)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:'
  }
  catch {
    return false
  }
}

const ModalFieldLabel = ({ children, required = false }: { children: ReactNode, required?: boolean }) => (
  <div className="mb-1 system-xs-medium-uppercase text-text-tertiary">
    {children}
    {required && <span className="ml-1 text-red-500">*</span>}
  </div>
)

const ExternalApiManagementPage = () => {
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

  const [selectedAppId, setSelectedAppId] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [searchInput, setSearchInput] = useState('')
  const [searchQuery, setSearchQuery] = useState('')

  const appsQuery = useExternalApps({
    page: 1,
    page_size: 200,
  }, canView)
  const apps = appsQuery.data?.apps ?? []
  const selectedApp = apps.find(item => item.id === selectedAppId)
  const selectedAppBaseUrl = typeof selectedApp?.auth_config?.base_url === 'string'
    ? selectedApp.auth_config.base_url
    : ''

  const apisQuery = useExternalAppApis(
    selectedAppId || undefined,
    {
      page,
      page_size: pageSize,
      query: searchQuery.trim() || undefined,
    },
    canView && !!selectedAppId,
  )
  const apis = apisQuery.data?.apis ?? []
  const pagination = apisQuery.data?.pagination
  const totalPages = Math.max(1, Math.ceil((pagination?.total ?? 0) / (pagination?.page_size || pageSize)))

  const createMutation = useCreateExternalAppApi()
  const updateMutation = useUpdateExternalAppApi()
  const deleteMutation = useDeleteExternalAppApi()
  const importOpenAPIMutation = useImportExternalAppOpenAPI()

  const [modalMode, setModalMode] = useState<ApiModalMode>(null)
  const [editingApi, setEditingApi] = useState<ExternalAppApi | null>(null)
  const [form, setForm] = useState<ApiFormState>(createEmptyForm())
  const [activeParamSection, setActiveParamSection] = useState<ApiParamLocation>('query')

  const [isImportDialogOpen, setIsImportDialogOpen] = useState(false)
  const [openAPIText, setOpenAPIText] = useState('')

  useEffect(() => {
    if (!apps.length) {
      setSelectedAppId('')
      return
    }
    if (!selectedAppId || !apps.some(item => item.id === selectedAppId))
      setSelectedAppId(apps[0]?.id ?? '')
  }, [apps, selectedAppId])

  useEffect(() => {
    setPage(1)
  }, [selectedAppId])

  useEffect(() => {
    if ((pagination?.total ?? 0) > 0 && apis.length === 0 && page > 1)
      setPage(prev => Math.max(1, prev - 1))
  }, [apis.length, page, pagination?.total])

  const setFormField = <K extends keyof ApiFormState>(key: K, value: ApiFormState[K]) => {
    setForm(prev => ({
      ...prev,
      [key]: value,
    }))
  }

  const addParamDefinition = (section: ApiParamLocation) => {
    setForm((prev) => {
      const nextParamConfig: ApiParamConfig = {
        ...prev.paramConfig,
        [section]: [...prev.paramConfig[section], createEmptyParamDefinition()],
      }
      return {
        ...prev,
        paramConfig: nextParamConfig,
      }
    })
  }

  const removeParamDefinition = (section: ApiParamLocation, definitionId: string) => {
    setForm((prev) => {
      const nextParamConfig: ApiParamConfig = {
        ...prev.paramConfig,
        [section]: prev.paramConfig[section].filter(item => item.id !== definitionId),
      }
      return {
        ...prev,
        paramConfig: nextParamConfig,
      }
    })
  }

  const updateParamDefinition = (
    section: ApiParamLocation,
    definitionId: string,
    key: keyof Omit<ApiParamDefinition, 'id'>,
    value: string | boolean,
  ) => {
    setForm((prev) => {
      const nextParamConfig: ApiParamConfig = {
        ...prev.paramConfig,
        [section]: prev.paramConfig[section].map((item) => {
          if (item.id !== definitionId)
            return item
          return {
            ...item,
            [key]: value,
          }
        }),
      }
      return {
        ...prev,
        paramConfig: nextParamConfig,
      }
    })
  }

  const closeApiModal = () => {
    setModalMode(null)
    setEditingApi(null)
    setActiveParamSection('query')
    setForm(createEmptyForm())
  }

  const openCreateModal = () => {
    setModalMode('create')
    setEditingApi(null)
    setActiveParamSection('query')
    setForm(createEmptyForm())
  }

  const openEditModal = (item: ExternalAppApi) => {
    setModalMode('edit')
    setEditingApi(item)
    setActiveParamSection('query')
    setForm(mapApiToForm(item))
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

  const handleSubmitApi = () => {
    if (!selectedAppId)
      return

    const name = form.name.trim()
    const path = form.path.trim()
    const normalizedBaseUrlOverride = form.baseUrlOverride.trim()
    if (normalizedBaseUrlOverride && !isValidHttpUrl(normalizedBaseUrlOverride)) {
      toast.error(t('externalApi.baseUrlInvalid', { ns: 'common' }))
      return
    }
    if (!normalizedBaseUrlOverride && !selectedAppBaseUrl) {
      toast.error(t('externalApi.baseUrlRequired', { ns: 'common' }))
      return
    }
    const requestSchema = buildRequestSchemaFromParamConfig(form.paramConfig, normalizedBaseUrlOverride)
    if (!name || !path) {
      toast.error(t('externalApp.apiRequiredFields', { ns: 'common' }))
      return
    }

    if (modalMode === 'create') {
      createMutation.mutate({
        appId: selectedAppId,
        body: {
          name,
          http_method: form.httpMethod,
          path,
          summary: form.summary.trim() || undefined,
          description: form.description.trim() || undefined,
          api_purpose: form.purpose.trim() || undefined,
          required_permissions: [],
          request_schema: requestSchema,
          response_schema: {},
          is_confirmed: form.isConfirmed,
          is_enabled: form.isEnabled,
        },
      }, {
        onSuccess: () => {
          toast.success(t('actionMsg.modifiedSuccessfully', { ns: 'common' }))
          setPage(1)
          closeApiModal()
        },
        onError: (error) => {
          toast.error(error.message || t('actionMsg.modifiedUnsuccessfully', { ns: 'common' }))
        },
      })
      return
    }

    if (!editingApi)
      return

    updateMutation.mutate({
      appId: selectedAppId,
      apiId: editingApi.id,
      body: {
        name,
        http_method: form.httpMethod,
        path,
        summary: form.summary.trim() || undefined,
        description: form.description.trim() || undefined,
        api_purpose: form.purpose.trim() || undefined,
        request_schema: requestSchema,
        is_confirmed: form.isConfirmed,
        is_enabled: form.isEnabled,
      },
    }, {
      onSuccess: () => {
        toast.success(t('actionMsg.modifiedSuccessfully', { ns: 'common' }))
        closeApiModal()
      },
      onError: (error) => {
        toast.error(error.message || t('actionMsg.modifiedUnsuccessfully', { ns: 'common' }))
      },
    })
  }

  const handleDeleteApi = (item: ExternalAppApi) => {
    if (!selectedAppId)
      return
    if (!window.confirm(t('externalApp.apiDeleteConfirm', { ns: 'common', name: item.name })))
      return

    deleteMutation.mutate({
      appId: selectedAppId,
      apiId: item.id,
    }, {
      onSuccess: () => {
        toast.success(t('actionMsg.modifiedSuccessfully', { ns: 'common' }))
      },
      onError: (error) => {
        toast.error(error.message || t('actionMsg.modifiedUnsuccessfully', { ns: 'common' }))
      },
    })
  }

  const handleToggleApiEnabled = (item: ExternalAppApi) => {
    if (!selectedAppId)
      return
    updateMutation.mutate({
      appId: selectedAppId,
      apiId: item.id,
      body: {
        is_enabled: !item.is_enabled,
      },
    }, {
      onError: (error) => {
        toast.error(error.message || t('actionMsg.modifiedUnsuccessfully', { ns: 'common' }))
      },
    })
  }

  const handleToggleApiConfirmed = (item: ExternalAppApi) => {
    if (!selectedAppId)
      return
    updateMutation.mutate({
      appId: selectedAppId,
      apiId: item.id,
      body: {
        is_confirmed: !item.is_confirmed,
      },
    }, {
      onError: (error) => {
        toast.error(error.message || t('actionMsg.modifiedUnsuccessfully', { ns: 'common' }))
      },
    })
  }

  const handleImportOpenAPI = () => {
    if (!selectedAppId)
      return
    const spec = openAPIText.trim()
    if (!spec) {
      toast.error(t('externalApp.openAPIRequired', { ns: 'common' }))
      return
    }

    importOpenAPIMutation.mutate({
      appId: selectedAppId,
      body: {
        spec,
        overwrite_existing: true,
        import_as_unconfirmed: true,
      },
    }, {
      onSuccess: (response) => {
        toast.success(t('externalApp.openAPIImportSuccess', {
          ns: 'common',
          created: response.summary.created,
          updated: response.summary.updated,
          skipped: response.summary.skipped,
        }))
        setIsImportDialogOpen(false)
        setOpenAPIText('')
      },
      onError: (error) => {
        toast.error(error.message || t('externalApp.openAPIImportFailed', { ns: 'common' }))
      },
    })
  }

  const apiModalTitle = modalMode === 'create'
    ? t('externalApi.createModalTitle', { ns: 'common' })
    : t('externalApi.editModalTitle', { ns: 'common' })

  const apiModalConfirmText = modalMode === 'create'
    ? t('externalApp.createApiAction', { ns: 'common' })
    : t('externalApi.saveApiAction', { ns: 'common' })

  if (!canView) {
    return (
      <div className="rounded-xl border border-divider-subtle bg-components-panel-bg p-4 system-sm-regular text-text-tertiary">
        {t('externalApp.permissionDenied', { ns: 'common' })}
      </div>
    )
  }

  return (
    <div className="w-full space-y-4">
      <div className="rounded-xl border border-divider-subtle bg-components-panel-bg p-4">
        <div className="system-md-semibold text-text-primary">{t('externalApi.title', { ns: 'common' })}</div>
        <div className="mt-1 system-sm-regular text-text-tertiary">{t('externalApi.description', { ns: 'common' })}</div>
      </div>

      <div className="rounded-xl border border-divider-subtle bg-components-panel-bg p-4">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-[280px] grow flex-wrap items-center gap-2">
            <select
              value={selectedAppId}
              onChange={(e) => setSelectedAppId(e.target.value)}
              className="min-w-[220px] rounded-lg border border-divider-subtle bg-components-panel-bg px-3 py-2 system-sm-regular text-text-primary"
            >
              {apps.length === 0 && (
                <option value="">{t('externalApi.emptyApps', { ns: 'common' })}</option>
              )}
              {apps.map(item => (
                <option key={item.id} value={item.id}>{item.name}</option>
              ))}
            </select>
            <Input
              value={searchInput}
              onChange={e => setSearchInput(e.target.value)}
              placeholder={t('externalApi.searchPlaceholder', { ns: 'common' })}
              onKeyDown={(e) => {
                if (e.key === 'Enter')
                  handleApplySearch()
              }}
            />
            <Button variant="secondary" onClick={handleApplySearch}>{t('operation.search', { ns: 'common' })}</Button>
            <Button variant="ghost" onClick={handleResetSearch}>{t('operation.reset', { ns: 'common' })}</Button>
          </div>
          {canManage && (
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                disabled={!selectedAppId}
                onClick={() => setIsImportDialogOpen(true)}
              >
                {t('externalApp.importOpenAPIAction', { ns: 'common' })}
              </Button>
              <Button
                variant="primary"
                disabled={!selectedAppId}
                onClick={openCreateModal}
              >
                {t('externalApp.createApiAction', { ns: 'common' })}
              </Button>
            </div>
          )}
        </div>

        {!selectedAppId && (
          <div className="rounded-lg border border-divider-subtle p-6 text-center system-sm-regular text-text-tertiary">
            {t('externalApi.selectAppHint', { ns: 'common' })}
          </div>
        )}

        {selectedAppId && (
          <>
            <div className="overflow-x-auto rounded-lg border border-divider-subtle">
              <table className="min-w-full text-left">
                <thead className="bg-components-panel-on-panel-item-bg-hover">
                  <tr>
                    <th className="px-3 py-2 system-xs-medium-uppercase text-text-tertiary">{t('externalApi.tableName', { ns: 'common' })}</th>
                    <th className="px-3 py-2 system-xs-medium-uppercase text-text-tertiary">{t('externalApi.tableMethodPath', { ns: 'common' })}</th>
                    <th className="px-3 py-2 system-xs-medium-uppercase text-text-tertiary">{t('externalApi.tableBaseUrl', { ns: 'common' })}</th>
                    <th className="px-3 py-2 system-xs-medium-uppercase text-text-tertiary">{t('externalApi.tablePurpose', { ns: 'common' })}</th>
                    <th className="px-3 py-2 system-xs-medium-uppercase text-text-tertiary">{t('externalApi.tableStatus', { ns: 'common' })}</th>
                    <th className="px-3 py-2 system-xs-medium-uppercase text-text-tertiary">{t('externalApi.tableUpdatedAt', { ns: 'common' })}</th>
                    <th className="w-[280px] px-3 py-2 text-right system-xs-medium-uppercase text-text-tertiary">{t('externalApi.tableActions', { ns: 'common' })}</th>
                  </tr>
                </thead>
                <tbody>
                  {!apisQuery.isPending && apis.length === 0 && (
                    <tr>
                      <td colSpan={7} className="px-3 py-8 text-center system-sm-regular text-text-tertiary">
                        {t('externalApp.emptyApis', { ns: 'common' })}
                      </td>
                    </tr>
                  )}
                  {apis.map(item => (
                    <tr key={item.id} className="border-t border-divider-subtle/60">
                      <td className="px-3 py-3 system-sm-medium text-text-primary">{item.name}</td>
                      <td className="px-3 py-3 system-sm-regular text-text-secondary">
                        <div>{item.http_method} {item.path}</div>
                      </td>
                      <td className="max-w-[260px] px-3 py-3 system-sm-regular text-text-secondary">
                        {extractBaseUrlOverrideFromRequestSchema(item.request_schema) || selectedAppBaseUrl || '-'}
                      </td>
                      <td className="px-3 py-3 system-sm-regular text-text-secondary">{item.api_purpose || '-'}</td>
                      <td className="px-3 py-3">
                        <div className="flex flex-wrap gap-1">
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
                          <span
                            className={cn(
                              'inline-flex rounded-md px-2 py-0.5 system-xs-medium',
                              item.is_confirmed
                                ? 'bg-blue-100 text-blue-700'
                                : 'bg-yellow-100 text-yellow-700',
                            )}
                          >
                            {item.is_confirmed
                              ? t('externalApi.statusConfirmed', { ns: 'common' })
                              : t('externalApi.statusUnconfirmed', { ns: 'common' })}
                          </span>
                        </div>
                      </td>
                      <td className="px-3 py-3 system-sm-regular text-text-secondary">{formatUnixTimestamp(item.updated_at ?? item.created_at)}</td>
                      <td className="px-3 py-3">
                        {canManage && (
                          <div className="flex flex-wrap items-center justify-end gap-2">
                            <Button size="small" variant="ghost" onClick={() => openEditModal(item)}>
                              {t('operation.edit', { ns: 'common' })}
                            </Button>
                            <Button size="small" variant="ghost" loading={updateMutation.isPending} onClick={() => handleToggleApiConfirmed(item)}>
                              {item.is_confirmed
                                ? t('externalApp.markUnconfirmed', { ns: 'common' })
                                : t('externalApp.markConfirmed', { ns: 'common' })}
                            </Button>
                            <Button size="small" variant="ghost" loading={updateMutation.isPending} onClick={() => handleToggleApiEnabled(item)}>
                              {item.is_enabled
                                ? t('externalApp.disableApi', { ns: 'common' })
                                : t('externalApp.enableApi', { ns: 'common' })}
                            </Button>
                            <Button size="small" variant="ghost" tone="destructive" loading={deleteMutation.isPending} onClick={() => handleDeleteApi(item)}>
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

            {!apisQuery.isPending && (pagination?.total ?? 0) > 0 && (
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
          </>
        )}
      </div>

      <Dialog
        open={modalMode !== null}
        onOpenChange={(open) => {
          if (!open)
            closeApiModal()
        }}
      >
        <DialogContent className="w-[1200px] max-w-[calc(100vw-1.5rem)] p-0">
          <DialogCloseButton className="right-5 top-5" />
          <div className="border-b border-divider-subtle px-5 py-4 pr-12">
            <DialogTitle className="text-text-primary title-lg-semi-bold">{apiModalTitle}</DialogTitle>
          </div>
          <div className="space-y-3 px-5 py-4">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div>
                <ModalFieldLabel required>{t('externalApp.apiNameLabel', { ns: 'common' })}</ModalFieldLabel>
                <Input value={form.name} onChange={e => setFormField('name', e.target.value)} />
              </div>
              <div>
                <ModalFieldLabel required>{t('externalApi.tableMethodPath', { ns: 'common' })}</ModalFieldLabel>
                <select
                  value={form.httpMethod}
                  onChange={e => setFormField('httpMethod', e.target.value)}
                  className="w-full rounded-lg border border-divider-subtle bg-components-panel-bg px-3 py-2 system-sm-regular text-text-primary"
                >
                  {HTTP_METHOD_OPTIONS.map(method => (
                    <option key={method} value={method}>{method}</option>
                  ))}
                </select>
              </div>
            </div>
            <div>
              <ModalFieldLabel required>{t('externalApp.apiPathLabel', { ns: 'common' })}</ModalFieldLabel>
              <Input value={form.path} onChange={e => setFormField('path', e.target.value)} />
            </div>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div>
                <ModalFieldLabel>{t('externalApp.baseUrlLabel', { ns: 'common' })}</ModalFieldLabel>
                <Input value={selectedAppBaseUrl} readOnly disabled />
              </div>
              <div>
                <ModalFieldLabel>{t('externalApi.baseUrlOverrideLabel', { ns: 'common' })}</ModalFieldLabel>
                <Input
                  value={form.baseUrlOverride}
                  placeholder={t('externalApi.baseUrlOverridePlaceholder', { ns: 'common' })}
                  onChange={e => setFormField('baseUrlOverride', e.target.value)}
                />
                <div className="mt-1 system-xs-regular text-text-tertiary">
                  {t('externalApi.baseUrlOverrideHint', {
                    ns: 'common',
                    baseUrl: selectedAppBaseUrl || '-',
                  })}
                </div>
              </div>
            </div>
            <div>
              <ModalFieldLabel>{t('externalApp.apiPurposeLabel', { ns: 'common' })}</ModalFieldLabel>
              <textarea
                value={form.purpose}
                onChange={e => setFormField('purpose', e.target.value)}
                className="h-24 w-full rounded-lg border border-divider-subtle bg-components-panel-bg px-3 py-2 system-sm-regular text-text-primary"
              />
            </div>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div>
                <ModalFieldLabel>{t('externalApi.summaryLabel', { ns: 'common' })}</ModalFieldLabel>
                <textarea
                  value={form.summary}
                  onChange={e => setFormField('summary', e.target.value)}
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
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div className="flex items-center justify-between rounded-lg border border-divider-subtle px-3 py-2">
                <div className="system-sm-regular text-text-secondary">{t('externalApi.confirmedLabel', { ns: 'common' })}</div>
                <Switch checked={form.isConfirmed} onCheckedChange={value => setFormField('isConfirmed', value)} />
              </div>
              <div className="flex items-center justify-between rounded-lg border border-divider-subtle px-3 py-2">
                <div className="system-sm-regular text-text-secondary">{t('externalApi.enabledLabel', { ns: 'common' })}</div>
                <Switch checked={form.isEnabled} onCheckedChange={value => setFormField('isEnabled', value)} />
              </div>
            </div>

            <div className="rounded-lg border border-divider-subtle p-3">
              <div className="mb-2 system-sm-medium text-text-primary">{t('externalApi.paramConfigTitle', { ns: 'common' })}</div>
              <div className="mb-3 flex flex-wrap gap-2">
                {PARAM_SECTION_KEYS.map(section => (
                  <button
                    key={section}
                    type="button"
                    onClick={() => setActiveParamSection(section)}
                    className={cn(
                      'rounded-lg border px-3 py-1.5 system-xs-medium-uppercase transition-colors',
                      activeParamSection === section
                        ? 'border-components-button-primary-bg bg-components-button-primary-bg text-text-primary-on-surface'
                        : 'border-divider-subtle bg-components-panel-bg text-text-tertiary hover:bg-components-panel-on-panel-item-bg-hover',
                    )}
                  >
                    {section.toUpperCase()} ({form.paramConfig[section].length})
                  </button>
                ))}
              </div>

              <div className="rounded-lg border border-divider-subtle/70 p-2">
                <div className="mb-2 flex items-center justify-between">
                  <div className="system-xs-medium-uppercase text-text-tertiary">{t(PARAM_SECTION_LABEL_KEYS[activeParamSection], { ns: 'common' })}</div>
                  <Button
                    size="small"
                    variant="ghost"
                    onClick={() => addParamDefinition(activeParamSection)}
                  >
                    {t('externalApi.paramAdd', { ns: 'common' })}
                  </Button>
                </div>

                {form.paramConfig[activeParamSection].length === 0 && (
                  <div className="px-1 py-2 system-xs-regular text-text-tertiary">
                    {t('externalApi.paramEmpty', { ns: 'common' })}
                  </div>
                )}

                {form.paramConfig[activeParamSection].length > 0 && (
                  <div className="mb-2 hidden rounded-md border border-divider-subtle/60 bg-components-panel-on-panel-item-bg-hover px-2 py-1 md:grid md:grid-cols-[40px_minmax(0,1.2fr)_120px_110px_minmax(0,1fr)_minmax(0,1fr)_64px] md:gap-2">
                    <div className="system-xs-medium-uppercase text-text-tertiary">{t('externalApi.paramEnabled', { ns: 'common' })}</div>
                    <div className="system-xs-medium-uppercase text-text-tertiary">{t('externalApi.paramName', { ns: 'common' })}</div>
                    <div className="system-xs-medium-uppercase text-text-tertiary">{t('externalApi.paramType', { ns: 'common' })}</div>
                    <div className="system-xs-medium-uppercase text-text-tertiary">{t('externalApi.paramRequired', { ns: 'common' })}</div>
                    <div className="system-xs-medium-uppercase text-text-tertiary">{t('externalApi.paramExample', { ns: 'common' })}</div>
                    <div className="system-xs-medium-uppercase text-text-tertiary">{t('externalApi.paramDescription', { ns: 'common' })}</div>
                    <div className="system-xs-medium-uppercase text-text-tertiary">{t('operation.delete', { ns: 'common' })}</div>
                  </div>
                )}

                <div className="space-y-2">
                  {form.paramConfig[activeParamSection].map((item) => {
                    return (
                      <div key={item.id} className="grid grid-cols-1 gap-2 rounded-md border border-divider-subtle p-2 md:grid-cols-[40px_minmax(0,1.2fr)_120px_110px_minmax(0,1fr)_minmax(0,1fr)_64px] md:items-center">
                        <div className="flex items-center justify-center rounded-md border border-divider-subtle px-2 py-2">
                          <input
                            type="checkbox"
                            checked={item.enabled}
                            onChange={e => updateParamDefinition(activeParamSection, item.id, 'enabled', e.target.checked)}
                            className="h-4 w-4 cursor-pointer accent-[var(--color-primary)]"
                          />
                        </div>
                        <Input
                          value={item.name}
                          onChange={e => updateParamDefinition(activeParamSection, item.id, 'name', e.target.value)}
                          placeholder={`${t('externalApi.paramName', { ns: 'common' })} *`}
                        />
                        <select
                          value={item.type}
                          onChange={e => updateParamDefinition(activeParamSection, item.id, 'type', e.target.value)}
                          className="w-full rounded-lg border border-divider-subtle bg-components-panel-bg px-2 py-2 system-sm-regular text-text-primary"
                        >
                          {PARAM_TYPE_OPTIONS.map(type => (
                            <option key={type} value={type}>{type}</option>
                          ))}
                        </select>
                        <div className="flex items-center justify-between rounded-lg border border-divider-subtle px-2 py-2">
                          <div className="system-xs-regular text-text-tertiary md:hidden">{t('externalApi.paramRequired', { ns: 'common' })}</div>
                          <Switch
                            checked={item.required}
                            onCheckedChange={value => updateParamDefinition(activeParamSection, item.id, 'required', value)}
                          />
                        </div>
                        <Input
                          value={item.example}
                          onChange={e => updateParamDefinition(activeParamSection, item.id, 'example', e.target.value)}
                          placeholder={t('externalApi.paramExample', { ns: 'common' })}
                        />
                        <Input
                          value={item.description}
                          onChange={e => updateParamDefinition(activeParamSection, item.id, 'description', e.target.value)}
                          placeholder={t('externalApi.paramDescription', { ns: 'common' })}
                        />
                        <Button
                          size="small"
                          variant="ghost"
                          tone="destructive"
                          onClick={() => removeParamDefinition(activeParamSection, item.id)}
                        >
                          {t('operation.delete', { ns: 'common' })}
                        </Button>
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          </div>
          <div className="flex justify-end gap-2 border-t border-divider-subtle px-5 py-4">
            <Button variant="secondary" onClick={closeApiModal}>
              {t('operation.cancel', { ns: 'common' })}
            </Button>
            <Button
              variant="primary"
              loading={createMutation.isPending || updateMutation.isPending}
              onClick={handleSubmitApi}
            >
              {apiModalConfirmText}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog
        open={isImportDialogOpen}
        onOpenChange={(open) => {
          setIsImportDialogOpen(open)
          if (!open)
            setOpenAPIText('')
        }}
      >
        <DialogContent className="w-[720px] max-w-[calc(100vw-2rem)] p-0">
          <DialogCloseButton className="right-5 top-5" />
          <div className="border-b border-divider-subtle px-5 py-4 pr-12">
            <DialogTitle className="text-text-primary title-lg-semi-bold">{t('externalApp.openAPITitle', { ns: 'common' })}</DialogTitle>
          </div>
          <div className="space-y-2 px-5 py-4">
            <div className="system-sm-regular text-text-tertiary">{t('externalApp.openAPIDesc', { ns: 'common' })}</div>
            <textarea
              value={openAPIText}
              onChange={e => setOpenAPIText(e.target.value)}
              placeholder={t('externalApp.openAPIPlaceholder', { ns: 'common' })}
              className="h-72 w-full rounded-lg border border-divider-subtle bg-components-panel-bg px-3 py-2 system-sm-regular text-text-primary"
            />
          </div>
          <div className="flex justify-end gap-2 border-t border-divider-subtle px-5 py-4">
            <Button
              variant="secondary"
              onClick={() => {
                setIsImportDialogOpen(false)
                setOpenAPIText('')
              }}
            >
              {t('operation.cancel', { ns: 'common' })}
            </Button>
            <Button
              variant="primary"
              loading={importOpenAPIMutation.isPending}
              onClick={handleImportOpenAPI}
            >
              {t('externalApp.importOpenAPIAction', { ns: 'common' })}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export default ExternalApiManagementPage
