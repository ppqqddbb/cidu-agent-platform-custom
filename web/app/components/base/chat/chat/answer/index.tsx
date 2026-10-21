import type {
  FC,
  ReactNode,
} from 'react'
import type {
  ChatConfig,
  ChatItem,
} from '../../types'
import type { HumanInputFormSubmitData } from './human-input-content/type'
import type { FileEntity } from '@/app/components/base/file-uploader/types'
import type { AppData } from '@/models/share'
import type { AppSourceType } from '@/service/share'
import { cn } from '@langgenius/dify-ui/cn'
import { memo, useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { EditTitle } from '@/app/components/app/annotation/edit-annotation-modal/edit-item'
import AnswerIcon from '@/app/components/base/answer-icon'
import Citation from '@/app/components/base/chat/chat/citation'
import LoadingAnim from '@/app/components/base/chat/chat/loading-anim'
import { FileList } from '@/app/components/base/file-uploader'
import { fetchTextGenerationMessage } from '@/service/debug'
import { fetchChatMessage } from '@/service/share'
import ContentSwitch from '../content-switch'
import { useChatContext } from '../context'
import AgentContent from './agent-content'
import BasicContent from './basic-content'
import HumanInputFilledFormList from './human-input-filled-form-list'
import HumanInputFormList from './human-input-form-list'
import More from './more'
import Operation from './operation'
import SuggestedQuestions from './suggested-questions'
import WorkflowProcessItem from './workflow-process'

type MessageFileResponse = {
  id?: string
  related_id?: string
  upload_file_id?: string
  url?: string
}

type AnswerProps = {
  item: ChatItem
  question: string
  index: number
  config?: ChatConfig
  answerIcon?: ReactNode
  responding?: boolean
  showPromptLog?: boolean
  chatAnswerContainerInner?: string
  hideProcessDetail?: boolean
  appData?: AppData
  noChatInput?: boolean
  switchSibling?: (siblingMessageId: string) => void
  hideAvatar?: boolean
  onHumanInputFormSubmit?: (formToken: string, formData: HumanInputFormSubmitData) => Promise<void>
  appSourceType?: AppSourceType
  installedAppId?: string
  renderAgentContent?: (props: { item: ChatItem, responding?: boolean, content?: string }) => ReactNode
}
const Answer: FC<AnswerProps> = ({
  item,
  question,
  index,
  config,
  answerIcon,
  responding,
  showPromptLog,
  chatAnswerContainerInner,
  hideProcessDetail,
  appData,
  noChatInput,
  switchSibling,
  hideAvatar,
  onHumanInputFormSubmit,
  appSourceType,
  installedAppId,
  renderAgentContent,
}) => {
  const { t } = useTranslation()
  const {
    content,
    citation,
    agent_thoughts,
    more,
    annotation,
    workflowProcess,
    allFiles,
    message_files,
    humanInputFormDataList,
    humanInputFilledFormDataList,
  } = item
  const hasAgentThoughts = !!agent_thoughts?.length
  const hasHumanInputs = !!humanInputFormDataList?.length || !!humanInputFilledFormDataList?.length
  const findFreshFile = useCallback((freshFiles: MessageFileResponse[], file: FileEntity) => {
    return freshFiles.find((candidate) => {
      return candidate.id === file.id
        || candidate.related_id === file.id
        || candidate.upload_file_id === file.uploadedId
        || candidate.id === file.uploadedId
    })
  }, [])

  const resolveDownloadUrl = useCallback(async (file: FileEntity) => {
    if (!config?.appId && !appSourceType)
      return undefined

    try {
      let freshFiles: MessageFileResponse[] = []
      if (appSourceType) {
        const result = await fetchChatMessage(item.id, appSourceType, installedAppId)
        freshFiles = result?.message_files || []
      }
      else if (config?.appId) {
        const result = await fetchTextGenerationMessage({
          appId: config.appId,
          messageId: item.id,
        }) as { message_files?: MessageFileResponse[] }
        freshFiles = result?.message_files || []
      }
      const freshFile = findFreshFile(freshFiles, file)
      const freshUrl = freshFile?.url
      if (!freshUrl)
        return undefined

      const separator = freshUrl.includes('?') ? '&' : '?'
      return freshUrl.includes('as_attachment') ? freshUrl : `${freshUrl}${separator}as_attachment=true`
    }
    catch {
      return undefined
    }
  }, [appSourceType, config?.appId, findFreshFile, installedAppId, item.id])

  const [containerWidth, setContainerWidth] = useState(0)
  const [contentWidth, setContentWidth] = useState(0)
  const [humanInputFormContainerWidth, setHumanInputFormContainerWidth] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const humanInputFormContainerRef = useRef<HTMLDivElement>(null)

  const {
    getHumanInputNodeData,
  } = useChatContext()

  const getContainerWidth = () => {
    if (containerRef.current)
      setContainerWidth(containerRef.current?.clientWidth + 16)
  }
  useEffect(() => {
    getContainerWidth()
  }, [])

  const getContentWidth = () => {
    if (contentRef.current)
      setContentWidth(contentRef.current?.clientWidth)
  }

  useEffect(() => {
    if (!responding)
      getContentWidth()
  }, [responding])

  const getHumanInputFormContainerWidth = () => {
    if (humanInputFormContainerRef.current)
      setHumanInputFormContainerWidth(humanInputFormContainerRef.current?.clientWidth)
  }

  useEffect(() => {
    if (hasHumanInputs)
      getHumanInputFormContainerWidth()
  }, [hasHumanInputs])

  // Recalculate contentWidth when content changes (e.g., SVG preview/source toggle)
  useEffect(() => {
    if (!containerRef.current)
      return
    const resizeObserver = new ResizeObserver(() => {
      getContentWidth()
      getHumanInputFormContainerWidth()
    })
    resizeObserver.observe(containerRef.current)
    return () => {
      resizeObserver.disconnect()
    }
  }, [])

  const handleSwitchSibling = useCallback((direction: 'prev' | 'next') => {
    if (direction === 'prev') {
      if (item.prevSibling)
        switchSibling?.(item.prevSibling)
    }
    else {
      if (item.nextSibling)
        switchSibling?.(item.nextSibling)
    }
  }, [switchSibling, item.prevSibling, item.nextSibling])

  const contentIsEmpty = typeof content === 'string' && content.trim() === ''

  return (
    <div className="mb-2 flex last:mb-0">
      {!hideAvatar && (
        <div className="relative size-10 shrink-0">
          {answerIcon || <AnswerIcon />}
          {responding && (
            <div className="absolute top-[-3px] left-[-3px] flex h-4 w-4 items-center rounded-full border-[0.5px] border-divider-subtle bg-background-section-burn pl-[6px] shadow-xs">
              <LoadingAnim type="avatar" />
            </div>
          )}
        </div>
      )}
      <div className="chat-answer-container group ml-4 w-0 grow pb-4" ref={containerRef} data-testid="chat-answer-container">
        {/* Block 1: Workflow Process + Human Input Forms */}
        {hasHumanInputs && (
          <div className={cn('group relative pr-10', chatAnswerContainerInner)} data-testid="chat-answer-container-humaninput">
            <div
              ref={humanInputFormContainerRef}
              className={cn('relative inline-block w-full max-w-full rounded-2xl bg-chat-bubble-bg px-4 py-3 body-lg-regular text-text-primary')}
            >
              {
                !responding && contentIsEmpty && !hasAgentThoughts && (
                  <Operation
                    hasWorkflowProcess={!!workflowProcess}
                    maxSize={containerWidth - humanInputFormContainerWidth - 4}
                    contentWidth={humanInputFormContainerWidth}
                    item={item}
                    question={question}
                    index={index}
                    showPromptLog={showPromptLog}
                    noChatInput={noChatInput}
                  />
                )
              }
              {/** Render workflow process */}
              {
                workflowProcess && (
                  <WorkflowProcessItem
                    data={workflowProcess}
                    item={item}
                    hideProcessDetail={hideProcessDetail}
                    readonly={hideProcessDetail && appData ? !appData.site.show_workflow_steps : undefined}
                  />
                )
              }
              {
                humanInputFormDataList && humanInputFormDataList.length > 0 && (
                  <HumanInputFormList
                    humanInputFormDataList={humanInputFormDataList}
                    onHumanInputFormSubmit={onHumanInputFormSubmit}
                    getHumanInputNodeData={getHumanInputNodeData}
                  />
                )
              }
              {
                humanInputFilledFormDataList && humanInputFilledFormDataList.length > 0 && (
                  <HumanInputFilledFormList
                    humanInputFilledFormDataList={humanInputFilledFormDataList}
                  />
                )
              }
              {
                typeof item.siblingCount === 'number'
                && item.siblingCount > 1
                && !responding
                && contentIsEmpty
                && !hasAgentThoughts
                && (
                  <ContentSwitch
                    count={item.siblingCount}
                    currentIndex={item.siblingIndex}
                    prevDisabled={!item.prevSibling}
                    nextDisabled={!item.nextSibling}
                    switchSibling={handleSwitchSibling}
                  />
                )
              }
            </div>
          </div>
        )}

        {/* Block 2: Response Content (when human inputs exist) */}
        {hasHumanInputs && (responding || !contentIsEmpty || hasAgentThoughts) && (
          <div className={cn('group relative mt-2 pr-10', chatAnswerContainerInner)}>
            <div className="absolute -top-2 left-6 h-3 w-0.5 bg-chat-answer-human-input-form-divider-bg" />
            <div
              ref={contentRef}
              className="relative inline-block w-full max-w-full rounded-2xl bg-chat-bubble-bg px-4 py-3 body-lg-regular text-text-primary"
            >
              {
                !responding && (
                  <Operation
                    hasWorkflowProcess={!!workflowProcess}
                    maxSize={containerWidth - contentWidth - 4}
                    contentWidth={contentWidth}
                    item={item}
                    question={question}
                    index={index}
                    showPromptLog={showPromptLog}
                    noChatInput={noChatInput}
                  />
                )
              }
              {
                responding && contentIsEmpty && !hasAgentThoughts && (
                  <div className="flex h-5 w-6 items-center justify-center">
                    <LoadingAnim type="text" />
                  </div>
                )
              }
              {
                renderAgentContent && item.agent_response_parts?.length ? (
                  renderAgentContent({ item, responding, content })
                ) : !contentIsEmpty && !hasAgentThoughts && (
                  <BasicContent item={item} />
                )
              }
              {
                hasAgentThoughts && (
                  <AgentContent
                    item={item}
                    responding={responding}
                    content={content}
                    onResolveDownloadUrl={resolveDownloadUrl}
                  />
                )
              }
              {
                !!allFiles?.length && (
                  <FileList
                    className="my-1"
                    files={allFiles}
                    showDeleteAction={false}
                    showDownloadAction
                    canPreview
                    onResolveDownloadUrl={resolveDownloadUrl}
                  />
                )
              }
              {
                !!message_files?.length && (
                  <FileList
                    className="my-1"
                    files={message_files}
                    showDeleteAction={false}
                    showDownloadAction
                    canPreview
                    onResolveDownloadUrl={resolveDownloadUrl}
                  />
                )
              }
              {
                annotation?.id && annotation.authorName && (
                  <EditTitle
                    className="mt-1"
                    title={t(($) => $.editBy, { ns: 'appAnnotation', author: annotation.authorName })}
                  />
                )
              }
              <SuggestedQuestions item={item} />
              {
                !!citation?.length && !responding && (
                  <Citation data={citation} showHitInfo={config?.supportCitationHitInfo} />
                )
              }
              {
                typeof item.siblingCount === 'number'
                && item.siblingCount > 1
                && (
                  <ContentSwitch
                    count={item.siblingCount}
                    currentIndex={item.siblingIndex}
                    prevDisabled={!item.prevSibling}
                    nextDisabled={!item.nextSibling}
                    switchSibling={handleSwitchSibling}
                  />
                )
              }
            </div>
          </div>
        )}

        {/* Original single block layout (when no human inputs) */}
        {!hasHumanInputs && (
          <div className={cn('group relative pr-10', chatAnswerContainerInner)} data-testid="chat-answer-container-inner">
            <div
              ref={contentRef}
              className={cn('relative inline-block max-w-full rounded-2xl bg-chat-bubble-bg px-4 py-3 body-lg-regular text-text-primary', workflowProcess && 'w-full')}
            >
              {
                !responding && (
                  <Operation
                    hasWorkflowProcess={!!workflowProcess}
                    maxSize={containerWidth - contentWidth - 4}
                    contentWidth={contentWidth}
                    item={item}
                    question={question}
                    index={index}
                    showPromptLog={showPromptLog}
                    noChatInput={noChatInput}
                  />
                )
              }
              {/** Render workflow process */}
              {
                workflowProcess && (
                  <WorkflowProcessItem
                    data={workflowProcess}
                    item={item}
                    hideProcessDetail={hideProcessDetail}
                    readonly={hideProcessDetail && appData ? !appData.site?.show_workflow_steps : undefined}
                  />
                )
              }
              {
                responding && contentIsEmpty && !hasAgentThoughts && (
                  <div className="flex h-5 w-6 items-center justify-center">
                    <LoadingAnim type="text" />
                  </div>
                )
              }
              {
                renderAgentContent && item.agent_response_parts?.length ? (
                  renderAgentContent({ item, responding, content })
                ) : !contentIsEmpty && !hasAgentThoughts && (
                  <BasicContent item={item} />
                )
              }
              {
                hasAgentThoughts && (
                  <AgentContent
                    item={item}
                    responding={responding}
                    content={content}
                    onResolveDownloadUrl={resolveDownloadUrl}
                  />
                )
              }
              {
                !!allFiles?.length && (
                  <FileList
                    className="my-1"
                    files={allFiles}
                    showDeleteAction={false}
                    showDownloadAction
                    canPreview
                    onResolveDownloadUrl={resolveDownloadUrl}
                  />
                )
              }
              {
                !!message_files?.length && (
                  <FileList
                    className="my-1"
                    files={message_files}
                    showDeleteAction={false}
                    showDownloadAction
                    canPreview
                    onResolveDownloadUrl={resolveDownloadUrl}
                  />
                )
              }
              {
                annotation?.id && annotation.authorName && (
                  <EditTitle
                    className="mt-1"
                    title={t(($) => $.editBy, { ns: 'appAnnotation', author: annotation.authorName })}
                  />
                )
              }
              <SuggestedQuestions item={item} />
              {
                !!citation?.length && !responding && (
                  <Citation data={citation} showHitInfo={config?.supportCitationHitInfo} />
                )
              }
              {
                typeof item.siblingCount === 'number'
                && item.siblingCount > 1 && (
                  <ContentSwitch
                    count={item.siblingCount}
                    currentIndex={item.siblingIndex}
                    prevDisabled={!item.prevSibling}
                    nextDisabled={!item.nextSibling}
                    switchSibling={handleSwitchSibling}
                  />
                )
              }
            </div>
          </div>
        )}
        <More more={more} />
      </div>
    </div>
  )
}

export default memo(Answer)
