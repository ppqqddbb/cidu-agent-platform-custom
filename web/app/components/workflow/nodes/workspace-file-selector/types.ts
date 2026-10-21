import type { CommonNodeType } from '@/app/components/workflow/types'

export type SelectedWorkspaceFile = {
  id: string
  name: string
  size: number
  mime_type?: string | null
  created_at?: number | null
}

export type WorkspaceFileSelectorNodeType = CommonNodeType & {
  file_id?: string
  selected_file?: SelectedWorkspaceFile
}
