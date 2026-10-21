'use client'

import { useTranslation } from 'react-i18next'
import { HeaderNavLink } from '../nav-link'

const PluginsNav = () => {
  const { t } = useTranslation()

  return (
    <HeaderNavLink
      href="/marketplace"
      active={(pathname) => pathname.startsWith('/marketplace') || pathname.startsWith('/plugins')}
      className="flex h-8 items-center rounded-xl px-3"
      icon={<span aria-hidden className="i-custom-vender-main-nav-marketplace h-4 w-4" />}
      activeIcon={<span aria-hidden className="i-custom-vender-main-nav-marketplace-active h-4 w-4" />}
    >
      {t(($) => $['mainNav.marketplace'], { ns: 'common' })}
    </HeaderNavLink>
  )
}

export default PluginsNav
