'use client'

import { useTranslation } from 'react-i18next'
import { buildIntegrationPath } from '@/app/components/integrations/routes'
import { HeaderNavLink } from './nav-link'

export const ToolsNav = ({ className }: { className?: string }) => {
  const { t } = useTranslation()

  return (
    <HeaderNavLink
      href={buildIntegrationPath('provider')}
      active={(pathname) => pathname.startsWith('/integrations') || pathname.startsWith('/tools')}
      className={className}
      icon={<span aria-hidden className="i-custom-vender-main-nav-integrations h-4 w-4" />}
      activeIcon={<span aria-hidden className="i-custom-vender-main-nav-integrations-active h-4 w-4" />}
    >
      {t(($) => $['mainNav.integrations'], { ns: 'common' })}
    </HeaderNavLink>
  )
}
