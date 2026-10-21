'use client'

import type { ChangeEvent } from 'react'
import type { KnowledgeGraphImportTemplate } from '@/models/knowledge-graph'
import { Button } from '@langgenius/dify-ui/button'
import {
  Dialog,
  DialogCloseButton,
  DialogContent,
  DialogTitle,
} from '@langgenius/dify-ui/dialog'
import { toast } from '@langgenius/dify-ui/toast'
import { useCallback, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useImportKnowledgeGraphTemplate } from '@/service/use-knowledge-graph'
import { Textarea } from '@langgenius/dify-ui/textarea'

type ImportTemplateModalProps = {
  graphId: string
  show: boolean
  onClose: () => void
}

const exampleTemplate: KnowledgeGraphImportTemplate = {
  nodes: [
    {
      id: 'customer',
      name: 'Customer',
      type: 'Entity',
      description: 'A customer account',
      labels: ['Entity'],
      properties: {
        source: 'template',
      },
    },
    {
      id: 'product',
      name: 'Product',
      type: 'Entity',
      description: 'A product purchased by customers',
      labels: ['Entity'],
    },
  ],
  relationships: [
    {
      source_id: 'customer',
      target_id: 'product',
      relation_type: 'PURCHASES',
      confidence: 0.95,
      properties: {
        source: 'template',
      },
    },
  ],
}

const formatTemplate = (template: KnowledgeGraphImportTemplate) => JSON.stringify(template, null, 2)

const isRecord = (value: unknown): value is Record<string, unknown> => {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

const parseTemplate = (value: string): KnowledgeGraphImportTemplate => {
  const parsed: unknown = JSON.parse(value)
  if (!isRecord(parsed) || !Array.isArray(parsed.nodes))
    throw new Error('invalid_template')

  return parsed as KnowledgeGraphImportTemplate
}

const ImportTemplateModal = ({
  graphId,
  show,
  onClose,
}: ImportTemplateModalProps) => {
  const { t: rawT } = useTranslation()
  const t = useCallback(
    (key: string, options?: Record<string, unknown>) =>
      (rawT as unknown as (key: string, options?: Record<string, unknown>) => string)(key, options),
    [rawT],
  )
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [templateText, setTemplateText] = useState(() => formatTemplate(exampleTemplate))
  const [error, setError] = useState('')
  const importTemplate = useImportKnowledgeGraphTemplate()

  const handleClose = () => {
    setError('')
    onClose()
  }

  const handleImport = () => {
    let template: KnowledgeGraphImportTemplate
    try {
      template = parseTemplate(templateText)
    }
    catch {
      setError(t('knowledgeGraphImportInvalidJson', { ns: 'dataset' }))
      return
    }

    importTemplate.mutate({
      params: {
        graphId,
      },
      body: template,
    }, {
      onSuccess: (result) => {
        toast.success(t('knowledgeGraphImportSuccess', {
          ns: 'dataset',
          nodes: result.node_count,
          relationships: result.relationship_count,
        }))
        handleClose()
      },
      onError: (error) => {
        const message = error instanceof Error ? error.message : t('knowledgeGraphImportFailed', { ns: 'dataset' })
        toast.error(message)
      },
    })
  }

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file)
      return

    if (!file.name.toLowerCase().endsWith('.json')) {
      toast.error(t('knowledgeGraphImportFileTypeError', { ns: 'dataset' }))
      return
    }

    file.text()
      .then((text) => {
        setTemplateText(text)
        setError('')
      })
      .catch(() => toast.error(t('knowledgeGraphImportFileReadError', { ns: 'dataset' })))
  }

  return (
    <Dialog open={show} onOpenChange={open => !open && handleClose()}>
      <DialogContent className="max-w-[720px]">
        <DialogCloseButton />
        <DialogTitle className="title-2xl-semi-bold text-text-primary">
          {t('knowledgeGraphImportTitle', { ns: 'dataset' })}
        </DialogTitle>
        <div className="mt-4 body-sm-regular text-text-secondary">
          {t('knowledgeGraphImportDescription', { ns: 'dataset' })}
        </div>
        <div className="mt-4 flex items-center gap-2">
          <input
            ref={fileInputRef}
            className="hidden"
            type="file"
            accept=".json,application/json"
            onChange={handleFileChange}
          />
          <Button variant="secondary" onClick={() => fileInputRef.current?.click()}>
            <span className="mr-1 i-ri-file-upload-line h-4 w-4" />
            {t('knowledgeGraphImportSelectFile', { ns: 'dataset' })}
          </Button>
          <Button variant="secondary" onClick={() => setTemplateText(formatTemplate(exampleTemplate))}>
            <span className="mr-1 i-ri-file-list-3-line h-4 w-4" />
            {t('knowledgeGraphImportUseExample', { ns: 'dataset' })}
          </Button>
        </div>
        <Textarea
          className="mt-4 min-h-[360px] font-mono text-[13px] leading-5"
          value={templateText}
          spellCheck={false}
          onValueChange={(value) => {
            setTemplateText(value)
            setError('')
          }}
        />
        {!!error && (
          <div className="mt-2 system-xs-regular text-text-destructive">
            {error}
          </div>
        )}
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="secondary" onClick={handleClose}>
            {t('operation.cancel', { ns: 'common' })}
          </Button>
          <Button
            variant="primary"
            disabled={importTemplate.isPending}
            onClick={handleImport}
          >
            <span className="mr-1 i-ri-upload-cloud-2-line h-4 w-4" />
            {t('knowledgeGraphImportSubmit', { ns: 'dataset' })}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default ImportTemplateModal
