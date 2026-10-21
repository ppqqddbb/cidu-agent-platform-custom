'use client'

import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'

type NewGraphCardProps = {
  onCreate: () => void
}

const NewGraphCard = ({ onCreate }: NewGraphCardProps) => {
  const { t: rawT } = useTranslation()
  const t = useCallback(
    (key: string, options?: Record<string, unknown>) =>
      (rawT as unknown as (key: string, options?: Record<string, unknown>) => string)(key, options),
    [rawT],
  )

  return (
    <div className="flex h-[190px] flex-col gap-y-0.5 rounded-xl bg-background-default-dimmed">
      <div className="flex grow flex-col items-center justify-center p-2">
        <button
          type="button"
          className="flex w-full items-center gap-x-2 rounded-lg bg-transparent px-4 py-2 text-text-tertiary shadow-shadow-shadow-3 hover:bg-background-default-dodge hover:text-text-secondary hover:shadow-xs"
          onClick={onCreate}
        >
          <span className="i-ri-add-line h-4 w-4 shrink-0" />
          <span className="grow text-left system-sm-medium">{t('knowledgeGraphCreateLibrary', { ns: 'dataset' })}</span>
        </button>
        <button
          type="button"
          className="flex w-full items-center gap-x-2 rounded-lg bg-transparent px-4 py-2 text-text-tertiary shadow-shadow-shadow-3 hover:bg-background-default-dodge hover:text-text-secondary hover:shadow-xs"
          onClick={onCreate}
        >
          <span className="i-ri-git-branch-line h-4 w-4 shrink-0" />
          <span className="grow text-left system-sm-medium">{t('knowledgeGraphCreateFromText', { ns: 'dataset' })}</span>
        </button>
      </div>
      <div className="border-t-[0.5px] border-divider-subtle p-2">
        <button
          type="button"
          className="flex w-full items-center gap-x-2 rounded-lg bg-transparent px-4 py-2 text-text-tertiary shadow-shadow-shadow-3 hover:bg-background-default-dodge hover:text-text-secondary hover:shadow-xs"
          onClick={onCreate}
        >
          <span className="i-ri-database-2-line h-4 w-4 shrink-0" />
          <span className="grow text-left system-sm-medium">{t('knowledgeGraphConnectExternal', { ns: 'dataset' })}</span>
        </button>
      </div>
    </div>
  )
}

export default NewGraphCard
