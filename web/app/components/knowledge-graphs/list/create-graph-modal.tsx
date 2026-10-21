'use client'

import { Button } from '@langgenius/dify-ui/button'
import {
  Dialog,
  DialogCloseButton,
  DialogContent,
  DialogTitle,
} from '@langgenius/dify-ui/dialog'
import { toast } from '@langgenius/dify-ui/toast'
import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import Input from '@/app/components/base/input'
import { useCreateKnowledgeGraph } from '@/service/use-knowledge-graph'
import { Textarea } from '@langgenius/dify-ui/textarea'

type CreateGraphModalProps = {
  show: boolean
  onClose: () => void
}

const CreateGraphModal = ({ show, onClose }: CreateGraphModalProps) => {
  const { t: rawT } = useTranslation()
  const t = useCallback(
    (key: string, options?: Record<string, unknown>) =>
      (rawT as unknown as (key: string, options?: Record<string, unknown>) => string)(key, options),
    [rawT],
  )
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const createGraph = useCreateKnowledgeGraph()

  const handleCreate = () => {
    const graphName = name.trim()
    if (!graphName) {
      toast(t('knowledgeGraphNameRequired', { ns: 'dataset' }), { type: 'error' })
      return
    }

    createGraph.mutate({
      body: {
        name: graphName,
        description: description.trim(),
      },
    }, {
      onSuccess: () => {
        toast(t('knowledgeGraphCreated', { ns: 'dataset' }), { type: 'success' })
        setName('')
        setDescription('')
        onClose()
      },
    })
  }

  return (
    <Dialog open={show} onOpenChange={open => !open && onClose()}>
      <DialogContent className="max-w-[480px]">
        <DialogCloseButton />
        <DialogTitle className="title-2xl-semi-bold text-text-primary">
          {t('knowledgeGraphCreateTitle', { ns: 'dataset' })}
        </DialogTitle>
        <div className="mt-6 space-y-4">
          <label className="block">
            <div className="mb-1 system-sm-medium text-text-secondary">{t('knowledgeGraphName', { ns: 'dataset' })}</div>
            <Input
              value={name}
              maxLength={80}
              onChange={e => setName(e.target.value)}
              placeholder={t('knowledgeGraphNamePlaceholder', { ns: 'dataset' })}
            />
          </label>
          <label className="block">
            <div className="mb-1 system-sm-medium text-text-secondary">{t('knowledgeGraphDescription', { ns: 'dataset' })}</div>
            <Textarea
              value={description}
              maxLength={400}
              onValueChange={setDescription}
              placeholder={t('knowledgeGraphDescriptionPlaceholder', { ns: 'dataset' })}
            />
          </label>
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            {t('operation.cancel', { ns: 'common' })}
          </Button>
          <Button
            variant="primary"
            disabled={createGraph.isPending}
            onClick={handleCreate}
          >
            {t('operation.create', { ns: 'common' })}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default CreateGraphModal
