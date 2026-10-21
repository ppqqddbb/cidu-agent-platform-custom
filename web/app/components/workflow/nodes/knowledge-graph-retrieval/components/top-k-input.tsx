import type { FC } from 'react'
import Input from '@/app/components/base/input'

type Props = {
  value?: number
  onChange: (value: number) => void
  readonly?: boolean
}

const TopKInput: FC<Props> = ({
  value = 5,
  onChange,
  readonly,
}) => {
  return (
    <Input
      type="number"
      min={1}
      max={100}
      disabled={readonly}
      value={value}
      onChange={(event) => {
        const nextValue = Number(event.target.value)
        onChange(Number.isFinite(nextValue) && nextValue > 0 ? nextValue : 1)
      }}
    />
  )
}

export default TopKInput
