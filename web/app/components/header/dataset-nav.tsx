'use client'

import { useTranslation } from 'react-i18next'
import { HeaderNavLink } from './nav-link'

export const DatasetNav = () => {
  const { t } = useTranslation()

  return (
    <HeaderNavLink
      href="/datasets"
      className="flex h-8 items-center rounded-xl px-3"
      icon={<span aria-hidden className="i-custom-vender-main-nav-knowledge h-4 w-4" />}
      activeIcon={<span aria-hidden className="i-custom-vender-main-nav-knowledge-active h-4 w-4" />}
    >
      {t(($) => $['menus.datasets'], { ns: 'common' })}
    </HeaderNavLink>
  )
}
