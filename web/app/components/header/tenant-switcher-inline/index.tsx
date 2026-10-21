'use client'

import type { TenantListItemResponse } from '@dify/contracts/api/console/workspaces/types.gen'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useCallback, useTransition } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from '@langgenius/dify-ui/toast'
import { useAppContext } from '@/context/app-context'
import { consoleQuery } from '@/service/client'
import { basePath } from '@/utils/var'

const TenantSwitcherInline = () => {
  const { t: rawT } = useTranslation()
  const t = useCallback(
    (key: string, options?: Record<string, unknown>) =>
      (rawT as unknown as (key: string, options?: Record<string, unknown>) => string)(key, options),
    [rawT],
  )
  const { data } = useQuery(consoleQuery.workspaces.get.queryOptions())
  const switchWorkspaceMutation = useMutation(consoleQuery.workspaces.switch.post.mutationOptions())
  const workspaces = data?.workspaces ?? []
  const { currentWorkspaceCapabilities = [], isCurrentWorkspaceManager } = useAppContext()
  const [isPending, startTransition] = useTransition()

  if (workspaces.length <= 1)
    return null

  const currentWorkspace = workspaces.find((v: TenantListItemResponse) => v.current)
  const canSwitchWorkspace = currentWorkspaceCapabilities.length
    ? currentWorkspaceCapabilities.includes('workspace.switch')
    : isCurrentWorkspaceManager

  const handleSwitchWorkspace = (tenantId: string) => {
    if (!currentWorkspace || currentWorkspace.id === tenantId || !canSwitchWorkspace)
      return

    startTransition(async () => {
      try {
        await switchWorkspaceMutation.mutateAsync({ body: { tenant_id: tenantId } })
        toast.success(t('actionMsg.modifiedSuccessfully', { ns: 'common' }))
        location.assign(`${location.origin}${basePath}`)
      }
      catch {
        toast.error(t('provider.saveFailed', { ns: 'common' }))
      }
    })
  }

  return (
    <div className="ml-2">
      <select
        aria-label={t('userProfile.workspace', { ns: 'common' })}
        value={currentWorkspace?.id || ''}
        disabled={!canSwitchWorkspace || isPending}
        onChange={e => handleSwitchWorkspace(e.target.value)}
        className="h-8 min-w-[180px] rounded-lg border border-divider-subtle bg-components-panel-bg px-2 text-text-secondary system-sm-regular outline-none focus:border-components-input-border-active disabled:cursor-not-allowed disabled:text-text-tertiary"
      >
        {workspaces.map((workspace: TenantListItemResponse) => (
          <option key={workspace.id} value={workspace.id}>
            {workspace.name}
          </option>
        ))}
      </select>
    </div>
  )
}

export default TenantSwitcherInline
