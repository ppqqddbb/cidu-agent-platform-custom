'use client'
import type {
  AppData,
  ConversationItem,
} from '@/models/share'
import ActionButton from '@/app/components/base/action-button'
import AppIcon from '@/app/components/base/app-icon'
import { cn } from '@langgenius/dify-ui/cn'
import { Button } from '@langgenius/dify-ui/button'
import {
  RiCloseLine,
  RiEditBoxLine,
  RiExpandRightLine,
  RiLayoutLeft2Line,
  RiMenuLine,
} from '@remixicon/react'
import { useSuspenseQuery } from '@tanstack/react-query'
import {
  useEffect,
  useMemo,
  useState,
} from 'react'
import { useTranslation } from 'react-i18next'
import ChatWrapper from '@/app/components/base/chat/embedded-chatbot/chat-wrapper'
import Header from '@/app/components/base/chat/embedded-chatbot/header'
import Loading from '@/app/components/base/loading'
import DifyLogo from '@/app/components/base/logo/dify-logo'
import LogoHeader from '@/app/components/base/logo/logo-embedded-chat-header'
import { systemFeaturesQueryOptions } from '@/features/system-features/client'
import useBreakpoints, { MediaType } from '@/hooks/use-breakpoints'
import useDocumentTitle from '@/hooks/use-document-title'
import { AppSourceType } from '@/service/share'
import {
  EmbeddedChatbotContext,
  useEmbeddedChatbotContext,
} from './context'
import { useEmbeddedChatbot } from './hooks'
import { useThemeContext } from './theme/theme-context'
import { CssTransform } from './theme/utils'
import { isDify } from './utils'

type ConversationListSectionProps = {
  title?: string
  list: ConversationItem[]
  currentConversationId: string
  onChangeConversation: (conversationId: string) => void
}

const ConversationListSection = ({
  title,
  list,
  currentConversationId,
  onChangeConversation,
}: ConversationListSectionProps) => {
  const { t } = useTranslation()

  return (
    <div className="space-y-0.5" data-testid="embedded-conversation-list">
      {title && (
        <div className="px-3 pt-2 pb-1 system-xs-medium-uppercase text-text-tertiary">{title}</div>
      )}
      {list.map(item => (
        <button
          key={item.id}
          type="button"
          className={cn(
            'group flex w-full cursor-pointer rounded-lg p-1 pl-3 system-sm-medium text-components-menu-item-text hover:bg-state-base-hover',
            currentConversationId === item.id && 'bg-state-accent-active text-text-accent hover:bg-state-accent-active',
          )}
          onClick={() => onChangeConversation(item.id)}
        >
          <div className="grow truncate p-1 pl-0 text-left" title={item.name || ''}>
            {item.name || t($ => $['chat.newChatDefaultName'], { ns: 'share' })}
          </div>
        </button>
      ))}
    </div>
  )
}

type ConversationSidebarProps = {
  onItemClick?: () => void
}

const ConversationSidebar = ({
  onItemClick,
}: ConversationSidebarProps) => {
  const { t } = useTranslation()
  const {
    appData,
    handleNewConversation,
    pinnedConversationList,
    conversationList,
    currentConversationId,
    handleChangeConversation,
    isResponding,
  } = useEmbeddedChatbotContext()

  const handleSelectConversation = (conversationId: string) => {
    handleChangeConversation(conversationId)
    onItemClick?.()
  }

  const handleCreateConversation = () => {
    handleNewConversation()
    onItemClick?.()
  }

  return (
    <div className="flex h-full w-full flex-col">
      <div className="flex shrink-0 items-center gap-3 p-3 pr-2">
        <div className="shrink-0">
          <AppIcon
            size="tiny"
            iconType={appData?.site.icon_type}
            icon={appData?.site.icon}
            background={appData?.site.icon_background}
            imageUrl={appData?.site.icon_url}
          />
        </div>
        <div className="grow truncate system-md-semibold text-text-secondary">{appData?.site.title}</div>
      </div>
      <div className="shrink-0 px-3 py-3">
        <Button
          variant="secondary-accent"
          disabled={isResponding}
          className="w-full justify-center"
          onClick={handleCreateConversation}
          data-testid="embedded-new-chat-button"
        >
          <RiEditBoxLine className="mr-1 h-4 w-4" />
          {t($ => $['chat.newChat'], { ns: 'share' })}
        </Button>
      </div>
      <div className="h-0 grow space-y-3 overflow-y-auto px-3 pb-3">
        {!!pinnedConversationList.length && (
          <ConversationListSection
            title={t($ => $['chat.pinnedTitle'], { ns: 'share' }) || ''}
            list={pinnedConversationList}
            currentConversationId={currentConversationId}
            onChangeConversation={handleSelectConversation}
          />
        )}
        {!!conversationList.length && (
          <ConversationListSection
            title={(pinnedConversationList.length && t($ => $['chat.unpinnedTitle'], { ns: 'share' })) || ''}
            list={conversationList}
            currentConversationId={currentConversationId}
            onChangeConversation={handleSelectConversation}
          />
        )}
      </div>
    </div>
  )
}

const Chatbot = () => {
  const {
    isMobile,
    allowResetChat,
    appData,
    appChatListDataLoading,
    appPrevChatList,
    chatShouldReloadKey,
    handleNewConversation,
    themeBuilder,
  } = useEmbeddedChatbotContext()
  const media = useBreakpoints()
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
  const { t } = useTranslation()
  const { data: systemFeatures } = useSuspenseQuery(systemFeaturesQueryOptions())

  const customConfig = appData?.custom_config
  const site = appData?.site
  const isCleanLayout = useMemo(() => {
    if (typeof window === 'undefined')
      return false
    const urlParams = new URLSearchParams(window.location.search)
    return urlParams.get('embed_layout') === 'clean'
  }, [])
  const isCompactMode = media === MediaType.mobile && !isCleanLayout

  const difyIcon = <LogoHeader />

  useEffect(() => {
    setSidebarCollapsed(isCompactMode)
    if (!isCompactMode)
      setMobileSidebarOpen(false)
  }, [isCompactMode])

  useEffect(() => {
    themeBuilder?.buildTheme(site?.chat_color_theme, site?.chat_color_theme_inverted)
  }, [site, customConfig, themeBuilder])

  const chatWrapperRenderKey = useMemo(() => {
    const tailId = appPrevChatList.at(-1)?.id || 'empty'
    return `${chatShouldReloadKey || 'new'}:${appPrevChatList.length}:${tailId}`
  }, [appPrevChatList, chatShouldReloadKey])

  useDocumentTitle(site?.title || 'Chat')

  return (
    <div className="relative">
      <div
        className={cn(
          'flex rounded-2xl',
          isCleanLayout && 'px-2 pb-2 pt-5',
          isMobile
            ? isCleanLayout
              ? 'h-screen shadow-xs'
              : 'h-[calc(100vh-60px)] shadow-xs'
            : 'h-screen overflow-hidden bg-chatbot-bg',
        )}
        style={isMobile ? Object.assign({}, CssTransform(themeBuilder?.theme?.backgroundHeaderColorStyle ?? '')) : {}}
      >
        {!isCompactMode && (
          <div
            className={cn(
              'relative h-full shrink-0 border-r border-divider-subtle bg-chatbot-bg transition-all duration-200 ease-in-out',
              sidebarCollapsed ? 'w-0 overflow-hidden opacity-0' : 'w-[248px]',
            )}
          >
            {!sidebarCollapsed && (
              <>
                <div className="absolute right-2 top-2 z-10">
                  <ActionButton size="l" onClick={() => setSidebarCollapsed(true)}>
                    <RiLayoutLeft2Line className="h-[18px] w-[18px]" />
                  </ActionButton>
                </div>
                <ConversationSidebar />
              </>
            )}
          </div>
        )}
        <div className="relative flex grow flex-col">
          {!isCompactMode && sidebarCollapsed && (
            <div className="absolute left-2 top-2 z-20">
              <ActionButton size="l" onClick={() => setSidebarCollapsed(false)} data-testid="embedded-sidebar-trigger">
                <RiExpandRightLine className="h-[18px] w-[18px]" />
              </ActionButton>
            </div>
          )}
          {isCompactMode && (
            <div className="absolute left-2 top-2 z-20">
              <ActionButton size="l" onClick={() => setMobileSidebarOpen(true)} data-testid="embedded-sidebar-trigger">
                <RiMenuLine className="h-[18px] w-[18px]" />
              </ActionButton>
            </div>
          )}
          {!isCleanLayout && (
            <Header
              isMobile={isMobile}
              allowResetChat={allowResetChat}
              title={site?.title || ''}
              customerIcon={isDify() ? difyIcon : ''}
              theme={themeBuilder?.theme}
              onCreateNewChat={handleNewConversation}
            />
          )}
          <div className={cn(
            'flex grow flex-col overflow-y-auto',
            isCleanLayout && !isMobile && 'm-1 rounded-2xl border border-divider-subtle bg-chatbot-bg shadow-sm',
            isMobile && (isCleanLayout ? 'm-1 h-full rounded-2xl border border-divider-subtle bg-chatbot-bg shadow-sm' : 'm-[0.5px] h-[calc(100vh-3rem)]! rounded-2xl bg-chatbot-bg'),
          )}
          >
            {appChatListDataLoading && (
              <Loading type="app" />
            )}
            {!appChatListDataLoading && (
              <ChatWrapper key={chatWrapperRenderKey} />
            )}
          </div>
        </div>
      </div>
      {isCompactMode && mobileSidebarOpen && (
        <div
          className="fixed inset-0 z-50 flex bg-background-overlay p-1"
          onClick={() => setMobileSidebarOpen(false)}
          data-testid="embedded-sidebar-overlay"
        >
          <div
            className="flex h-full w-[calc(100vw-40px)] flex-col rounded-xl bg-components-panel-bg shadow-lg backdrop-blur-xs"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex justify-end px-2 pt-2">
              <ActionButton size="l" onClick={() => setMobileSidebarOpen(false)}>
                <RiCloseLine className="h-[18px] w-[18px]" />
              </ActionButton>
            </div>
            <ConversationSidebar onItemClick={() => setMobileSidebarOpen(false)} />
          </div>
        </div>
      )}
      {/* powered by */}
      {isMobile && !isCleanLayout && (
        <div className="flex h-[60px] shrink-0 items-center pl-2">
          {!appData?.custom_config?.remove_webapp_brand && (
            <div className={cn(
              'flex shrink-0 items-center gap-1.5 px-2',
            )}
            >
              <div className="system-2xs-medium-uppercase text-text-tertiary">{t($ => $['chat.poweredBy'], { ns: 'share' })}</div>
              {
                systemFeatures.branding.enabled && systemFeatures.branding.workspace_logo
                  ? <img src={systemFeatures.branding.workspace_logo} alt="logo" className="block h-5 w-auto" />
                  : appData?.custom_config?.replace_webapp_logo
                    ? <img src={`${appData?.custom_config?.replace_webapp_logo}`} alt="logo" className="block h-5 w-auto" />
                    : <DifyLogo size="small" />
              }
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const EmbeddedChatbotWrapper = () => {
  const media = useBreakpoints()
  const isMobile = media === MediaType.mobile
  const themeBuilder = useThemeContext()

  const {
    appData,
    appParams,
    appMeta,
    appChatListDataLoading,
    currentConversationId,
    currentConversationItem,
    appPrevChatList,
    pinnedConversationList,
    conversationList,
    newConversationInputs,
    newConversationInputsRef,
    handleNewConversationInputsChange,
    inputsForms,
    handleNewConversation,
    handleStartChat,
    handleChangeConversation,
    handleNewConversationCompleted,
    handleConversationCompleted,
    chatShouldReloadKey,
    isInstalledApp,
    allowResetChat,
    appId,
    handleFeedback,
    currentChatInstanceRef,
    clearChatList,
    setClearChatList,
    isResponding,
    setIsResponding,
    currentConversationInputs,
    setCurrentConversationInputs,
    allInputsHidden,
    initUserVariables,
  } = useEmbeddedChatbot(AppSourceType.webApp)

  return (
    <EmbeddedChatbotContext.Provider value={{
      appSourceType: AppSourceType.webApp,
      appData: (appData as AppData) || null,
      appParams,
      appMeta,
      appChatListDataLoading,
      currentConversationId,
      currentConversationItem,
      appPrevChatList,
      pinnedConversationList,
      conversationList,
      newConversationInputs,
      newConversationInputsRef,
      handleNewConversationInputsChange,
      inputsForms,
      handleNewConversation,
      handleStartChat,
      handleChangeConversation,
      handleNewConversationCompleted,
      handleConversationCompleted,
      chatShouldReloadKey,
      isMobile,
      isInstalledApp,
      allowResetChat,
      appId,
      handleFeedback,
      currentChatInstanceRef,
      themeBuilder,
      clearChatList,
      setClearChatList,
      isResponding,
      setIsResponding,
      currentConversationInputs,
      setCurrentConversationInputs,
      allInputsHidden,
      initUserVariables,
    }}
    >
      <Chatbot />
    </EmbeddedChatbotContext.Provider>
  )
}

const EmbeddedChatbot = () => {
  return <EmbeddedChatbotWrapper />
}

export default EmbeddedChatbot
