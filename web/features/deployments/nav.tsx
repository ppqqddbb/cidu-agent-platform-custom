'use client'

import { useTranslation } from 'react-i18next'
import { HeaderNavLink } from '@/app/components/header/nav-link'

export const DeploymentsNav = () => {
  const { t } = useTranslation()

  return (
    <HeaderNavLink
      href="/deployments"
      className="flex h-8 items-center rounded-xl px-3"
      icon={<span aria-hidden className="i-ri-rocket-line h-4 w-4" />}
      activeIcon={<span aria-hidden className="i-ri-rocket-fill h-4 w-4" />}
    >
      {t(($) => $['menus.deployments'], { ns: 'common' })}
    </HeaderNavLink>
  )
}
