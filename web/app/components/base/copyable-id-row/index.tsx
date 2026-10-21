import type { MouseEvent } from 'react'
import { cn } from '@langgenius/dify-ui/cn'
import CopyIcon from '@/app/components/base/copy-icon'

type CopyableIdRowProps = {
  label: string
  id: string
  className?: string
}

const CopyableIdRow = ({
  label,
  id,
  className,
}: CopyableIdRowProps) => {
  const handleCopyClick = (event: MouseEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
  }

  return (
    <div
      className={cn('flex min-w-0 items-center gap-1 system-xs-regular text-text-tertiary', className)}
      title={`${label}: ${id}`}
    >
      <span className="shrink-0">
        {label}
        :
      </span>
      <span className="min-w-0 truncate">{id}</span>
      <div
        className="flex h-5 w-5 shrink-0 items-center justify-center opacity-70 transition-opacity hover:opacity-100"
        onClick={handleCopyClick}
        onMouseDown={handleCopyClick}
      >
        <CopyIcon content={id} />
      </div>
    </div>
  )
}

export default CopyableIdRow
