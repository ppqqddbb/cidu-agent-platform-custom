'use client'

import { cn } from '@langgenius/dify-ui/cn'
import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import Link from '@/next/link'
import { useSelectedLayoutSegment } from '@/next/navigation'

type KnowledgeGraphNavProps = {
  className?: string
}

const KnowledgeGraphNav = ({
  className,
}: KnowledgeGraphNavProps) => {
  const { t: rawT } = useTranslation()
  const t = useCallback(
    (key: string, options?: Record<string, unknown>) =>
      (rawT as unknown as (key: string, options?: Record<string, unknown>) => string)(key, options),
    [rawT],
  )
  const selectedSegment = useSelectedLayoutSegment()
  const activated = selectedSegment === 'knowledge-graphs'

  return (
    <Link
      href="/knowledge-graphs"
      className={cn(
        'group text-sm font-medium',
        activated && 'bg-components-main-nav-nav-button-bg-active font-semibold shadow-md',
        activated ? 'text-components-main-nav-nav-button-text-active' : 'text-components-main-nav-nav-button-text hover:bg-components-main-nav-nav-button-bg-hover',
        className,
      )}
    >
      {
        activated
          ? <span className="i-ri-git-branch-fill h-4 w-4" />
          : <span className="i-ri-git-branch-line h-4 w-4" />
      }
      <div className="ml-2 max-[1024px]:hidden">
        {t('menus.knowledgeGraphs', { ns: 'common' })}
      </div>
    </Link>
  )
}

export default KnowledgeGraphNav
