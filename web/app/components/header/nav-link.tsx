'use client'

import type { ReactNode } from 'react'
import { cn } from '@langgenius/dify-ui/cn'
import Link from '@/next/link'
import { usePathname } from '@/next/navigation'

type HeaderNavLinkProps = {
  href: string
  active?: (pathname: string) => boolean
  className?: string
  icon: ReactNode
  activeIcon?: ReactNode
  children: ReactNode
}

export function HeaderNavLink({
  href,
  active,
  className,
  icon,
  activeIcon,
  children,
}: HeaderNavLinkProps) {
  const pathname = usePathname()
  const activated = active ? active(pathname) : pathname === href || pathname.startsWith(`${href}/`)

  return (
    <Link
      href={href}
      className={cn(
        'group text-sm font-medium',
        activated && 'bg-components-main-nav-nav-button-bg-active font-semibold shadow-md',
        activated
          ? 'text-components-main-nav-nav-button-text-active'
          : 'text-components-main-nav-nav-button-text hover:bg-components-main-nav-nav-button-bg-hover',
        className,
      )}
    >
      {activated && activeIcon ? activeIcon : icon}
      <div className="ml-2 max-[1024px]:hidden">
        {children}
      </div>
    </Link>
  )
}
