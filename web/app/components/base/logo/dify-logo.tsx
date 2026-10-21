'use client'
import type { FC } from 'react'
import { cn } from '@langgenius/dify-ui/cn'
import useTheme from '@/hooks/use-theme'

export type LogoStyle = 'default' | 'monochromeWhite'

export type LogoSize = 'large' | 'medium' | 'small'

export const logoSizeMap: Record<LogoSize, string> = {
  large: 'text-[32px] leading-7 min-w-[80px]',
  medium: 'text-2xl leading-[22px] min-w-[64px]',
  small: 'text-lg leading-4 min-w-[48px]',
}

type DifyLogoProps = {
  style?: LogoStyle
  size?: LogoSize
  className?: string
  alt?: string
}

const DifyLogo: FC<DifyLogoProps> = ({
  style = 'default',
  size = 'medium',
  className,
  alt = 'Cidu',
}) => {
  const { theme } = useTheme()
  const themedStyle = (theme === 'dark' && style === 'default') ? 'monochromeWhite' : style
  const isMonochrome = themedStyle === 'monochromeWhite'

  return (
    <div
      className={cn(
        'inline-flex items-center justify-start whitespace-nowrap font-semibold tracking-tight',
        logoSizeMap[size],
        isMonochrome ? 'text-white' : 'text-text-primary',
        className,
      )}
      aria-label={alt}
    >
      <span className={cn(
        'font-bold leading-none',
        isMonochrome ? 'text-white' : 'text-[#0033FF]',
      )}
      >
        C
      </span>
      <span className="leading-none">idu</span>
    </div>
  )
}

export default DifyLogo
