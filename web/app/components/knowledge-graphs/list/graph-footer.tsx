'use client'

import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'

const GraphFooter = () => {
  const { t: rawT } = useTranslation()
  const t = useCallback(
    (key: string, options?: Record<string, unknown>) =>
      (rawT as unknown as (key: string, options?: Record<string, unknown>) => string)(key, options),
    [rawT],
  )

  return (
    <footer className="shrink-0 px-12 py-6">
      <h3 className="text-xl leading-tight font-semibold text-text-accent">{t('knowledgeGraphDidYouKnow', { ns: 'dataset' })}</h3>
      <p className="mt-1 text-sm leading-tight font-normal text-text-secondary">
        {t('knowledgeGraphIntro1', { ns: 'dataset' })}
        <span className="inline-flex items-center gap-1 text-text-accent">{t('knowledgeGraphIntro2', { ns: 'dataset' })}</span>
        {t('knowledgeGraphIntro3', { ns: 'dataset' })}
      </p>
    </footer>
  )
}

export default GraphFooter
