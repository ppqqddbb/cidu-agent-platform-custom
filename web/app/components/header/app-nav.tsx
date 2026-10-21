'use client'

import { useTranslation } from 'react-i18next'
import { HeaderNavLink } from './nav-link'

const AppNav = () => {
  const { t } = useTranslation()

  return (
    <HeaderNavLink
      href="/apps"
      active={(pathname) => pathname.startsWith('/apps') || pathname.startsWith('/app') || pathname.startsWith('/snippets')}
      className="flex h-8 items-center rounded-xl px-3"
      icon={<span aria-hidden className="i-custom-vender-main-nav-studio h-4 w-4" />}
      activeIcon={<span aria-hidden className="i-custom-vender-main-nav-studio-active h-4 w-4" />}
    >
      {t(($) => $['menus.apps'], { ns: 'common' })}
    </HeaderNavLink>
  )
}

export default AppNav
