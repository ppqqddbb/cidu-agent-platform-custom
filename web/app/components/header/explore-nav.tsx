'use client'

import { useTranslation } from 'react-i18next'
import { HeaderNavLink } from './nav-link'

export const ExploreNav = ({ className }: { className?: string }) => {
  const { t } = useTranslation()

  return (
    <HeaderNavLink
      href="/"
      active={(pathname) => pathname === '/' || pathname.startsWith('/explore')}
      className={className}
      icon={<span aria-hidden className="i-custom-vender-main-nav-home h-4 w-4" />}
      activeIcon={<span aria-hidden className="i-custom-vender-main-nav-home-active h-4 w-4" />}
    >
      {t(($) => $['mainNav.home'], { ns: 'common' })}
    </HeaderNavLink>
  )
}
