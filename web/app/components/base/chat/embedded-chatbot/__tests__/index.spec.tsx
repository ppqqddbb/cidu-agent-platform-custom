import type { ReactElement, RefObject } from 'react'
import type { ChatConfig } from '../../types'
import type { AppData, AppMeta, ConversationItem } from '@/models/share'
import { fireEvent, screen } from '@testing-library/react'
import { vi } from 'vitest'
import { renderWithSystemFeatures } from '@/__tests__/mock-system-features'
import useBreakpoints, { MediaType } from '@/hooks/use-breakpoints'
import { useEmbeddedChatbot } from '../hooks'
import EmbeddedChatbot from '../index'

let mockBrandingWorkspaceLogo = ''
let chatWrapperMountCounter = 0
const render = (ui: ReactElement) => renderWithSystemFeatures(ui, {
  systemFeatures: {
    branding: { enabled: true, workspace_logo: mockBrandingWorkspaceLogo },
  },
})

vi.mock('../hooks', () => ({
  useEmbeddedChatbot: vi.fn(),
}))

vi.mock('@/hooks/use-breakpoints', () => ({
  default: vi.fn(),
  MediaType: {
    mobile: 'mobile',
    tablet: 'tablet',
    pc: 'pc',
  },
}))

vi.mock('@/hooks/use-document-title', () => ({
  default: vi.fn(),
}))

vi.mock('../chat-wrapper', () => ({
  __esModule: true,
  default: () => {
    const React = require('react') as typeof import('react')
    const [mountId] = React.useState(() => ++chatWrapperMountCounter)
    return <div data-testid="chat-area">{`chat area ${mountId}`}</div>
  },
}))

vi.mock('../header', () => ({
  __esModule: true,
  default: () => <div>chat header</div>,
}))

vi.mock('../theme/theme-context', () => ({
  useThemeContext: vi.fn(() => ({
    buildTheme: vi.fn(),
    theme: {
      backgroundHeaderColorStyle: '',
    },
  })),
}))

const mockIsDify = vi.fn(() => false)
vi.mock('../utils', () => ({
  isDify: () => mockIsDify(),
}))

type EmbeddedChatbotHookReturn = ReturnType<typeof useEmbeddedChatbot>

const createHookReturn = (overrides: Partial<EmbeddedChatbotHookReturn> = {}): EmbeddedChatbotHookReturn => {
  const appData: AppData = {
    app_id: 'app-1',
    can_replace_logo: true,
    custom_config: {
      remove_webapp_brand: false,
      replace_webapp_logo: '',
    },
    enable_site: true,
    end_user_id: 'user-1',
    site: {
      title: 'Embedded App',
      chat_color_theme: 'blue',
      chat_color_theme_inverted: false,
    },
  }

  const base: EmbeddedChatbotHookReturn = {
    appSourceType: 'webApp' as EmbeddedChatbotHookReturn['appSourceType'],
    isInstalledApp: false,
    appId: 'app-1',
    currentConversationId: '',
    currentConversationItem: undefined,
    removeConversationIdInfo: vi.fn(),
    handleConversationIdInfoChange: vi.fn(),
    appData,
    appParams: {} as ChatConfig,
    appMeta: { tool_icons: {} } as AppMeta,
    appPinnedConversationData: { data: [], has_more: false, limit: 20 },
    appConversationData: { data: [], has_more: false, limit: 20 },
    appConversationDataLoading: false,
    appChatListData: { data: [], has_more: false, limit: 20 },
    appChatListDataLoading: false,
    appPrevChatList: [],
    pinnedConversationList: [] as ConversationItem[],
    conversationList: [] as ConversationItem[],
    setShowNewConversationItemInList: vi.fn(),
    newConversationInputs: {},
    newConversationInputsRef: { current: {} } as unknown as RefObject<Record<string, unknown>>,
    handleNewConversationInputsChange: vi.fn(),
    inputsForms: [],
    handleNewConversation: vi.fn(),
    handleStartChat: vi.fn(),
    handleChangeConversation: vi.fn(),
    handleNewConversationCompleted: vi.fn(),
    handleConversationCompleted: vi.fn(),
    newConversationId: '',
    chatShouldReloadKey: 'reload-key',
    allowResetChat: true,
    handleFeedback: vi.fn(),
    currentChatInstanceRef: { current: { handleStop: vi.fn() } },
    clearChatList: false,
    setClearChatList: vi.fn(),
    isResponding: false,
    setIsResponding: vi.fn(),
    currentConversationInputs: {},
    setCurrentConversationInputs: vi.fn(),
    allInputsHidden: false,
    initUserVariables: {},
  }

  return {
    ...base,
    ...overrides,
  }
}

describe('EmbeddedChatbot index', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockBrandingWorkspaceLogo = ''
    chatWrapperMountCounter = 0
    vi.mocked(useBreakpoints).mockReturnValue(MediaType.mobile)
    vi.mocked(useEmbeddedChatbot).mockReturnValue(createHookReturn())
    window.history.replaceState({}, '', '/')
  })

  afterEach(() => {
    window.history.replaceState({}, '', '/')
  })

  describe('Loading and chat content', () => {
    it('should show loading state before chat content', () => {
      vi.mocked(useEmbeddedChatbot).mockReturnValue(createHookReturn({ appChatListDataLoading: true }))

      render(<EmbeddedChatbot />)

      expect(screen.getByRole('status')).toBeInTheDocument()
      expect(screen.queryByTestId('chat-area')).not.toBeInTheDocument()
    })

    it('should render chat content when loading finishes', () => {
      render(<EmbeddedChatbot />)

      expect(screen.getByTestId('chat-area')).toBeInTheDocument()
    })

    it('should remount chat content when history snapshot changes for the same conversation', () => {
      const hookState = createHookReturn({
        currentConversationId: 'conversation-1',
        chatShouldReloadKey: 'conversation-1',
        appPrevChatList: [],
      })
      vi.mocked(useBreakpoints).mockReturnValue(MediaType.pc)
      vi.mocked(useEmbeddedChatbot).mockImplementation(() => hookState)

      const { rerender } = render(<EmbeddedChatbot />)

      expect(screen.getByTestId('chat-area')).toHaveTextContent('chat area 1')

      hookState.appPrevChatList = [{
        id: 'question-msg-1',
        content: 'hello',
        isAnswer: false,
      }] as typeof hookState.appPrevChatList

      rerender(<EmbeddedChatbot />)

      expect(screen.getByTestId('chat-area')).toHaveTextContent('chat area 2')
    })
  })

  describe('Sidebar behavior', () => {
    it('should render new chat button and conversation list on desktop', () => {
      vi.mocked(useBreakpoints).mockReturnValue(MediaType.pc)
      vi.mocked(useEmbeddedChatbot).mockReturnValue(createHookReturn({
        pinnedConversationList: [{ id: 'pinned-1', name: 'Pinned 1', inputs: {}, introduction: '' }],
        conversationList: [{ id: 'conversation-1', name: 'Conversation 1', inputs: {}, introduction: '' }],
      }))

      render(<EmbeddedChatbot />)

      expect(screen.getByTestId('embedded-new-chat-button')).toBeInTheDocument()
      expect(screen.getByText('Pinned 1')).toBeInTheDocument()
      expect(screen.getByText('Conversation 1')).toBeInTheDocument()
    })

    it('should call handleChangeConversation when selecting a conversation', () => {
      vi.mocked(useBreakpoints).mockReturnValue(MediaType.pc)
      const handleChangeConversation = vi.fn()
      vi.mocked(useEmbeddedChatbot).mockReturnValue(createHookReturn({
        conversationList: [{ id: 'conversation-1', name: 'Conversation 1', inputs: {}, introduction: '' }],
        handleChangeConversation,
      }))

      render(<EmbeddedChatbot />)
      fireEvent.click(screen.getByRole('button', { name: 'Conversation 1' }))

      expect(handleChangeConversation).toHaveBeenCalledWith('conversation-1')
    })

    it('should open compact sidebar overlay when clicking menu button', () => {
      vi.mocked(useBreakpoints).mockReturnValue(MediaType.mobile)

      render(<EmbeddedChatbot />)
      fireEvent.click(screen.getByTestId('embedded-sidebar-trigger'))

      expect(screen.getByTestId('embedded-sidebar-overlay')).toBeInTheDocument()
    })
  })

  describe('Powered by branding', () => {
    it('should show workspace logo on mobile when branding is enabled', () => {
      mockBrandingWorkspaceLogo = 'https://example.com/workspace-logo.png'

      render(<EmbeddedChatbot />)

      expect(screen.getByText('share.chat.poweredBy')).toBeInTheDocument()
      expect(screen.getByAltText('logo')).toHaveAttribute('src', 'https://example.com/workspace-logo.png')
    })

    it('should show custom logo when workspace branding logo is unavailable', () => {
      vi.mocked(useEmbeddedChatbot).mockReturnValue(createHookReturn({
        appData: {
          app_id: 'app-1',
          can_replace_logo: true,
          custom_config: {
            remove_webapp_brand: false,
            replace_webapp_logo: 'https://example.com/custom-logo.png',
          },
          enable_site: true,
          end_user_id: 'user-1',
          site: {
            title: 'Embedded App',
            chat_color_theme: 'blue',
            chat_color_theme_inverted: false,
          },
        },
      }))

      render(<EmbeddedChatbot />)

      expect(screen.getByText('share.chat.poweredBy')).toBeInTheDocument()
      expect(screen.getByAltText('logo')).toHaveAttribute('src', 'https://example.com/custom-logo.png')
    })

    it('should hide powered by section when branding is removed', () => {
      vi.mocked(useEmbeddedChatbot).mockReturnValue(createHookReturn({
        appData: {
          app_id: 'app-1',
          can_replace_logo: true,
          custom_config: {
            remove_webapp_brand: true,
            replace_webapp_logo: '',
          },
          enable_site: true,
          end_user_id: 'user-1',
          site: {
            title: 'Embedded App',
            chat_color_theme: 'blue',
            chat_color_theme_inverted: false,
          },
        },
      }))

      render(<EmbeddedChatbot />)

      expect(screen.queryByText('share.chat.poweredBy')).not.toBeInTheDocument()
    })

    it('should not show powered by section on desktop', () => {
      vi.mocked(useBreakpoints).mockReturnValue(MediaType.pc)
      vi.mocked(useEmbeddedChatbot).mockReturnValue(createHookReturn({ appData: null }))
      mockIsDify.mockReturnValue(true)

      render(<EmbeddedChatbot />)

      expect(screen.queryByText('share.chat.poweredBy')).not.toBeInTheDocument()
      expect(screen.getByText('chat header')).toBeInTheDocument()
    })
  })

  describe('Clean layout mode', () => {
    it('should hide header and powered-by section when embed_layout=clean', () => {
      window.history.replaceState({}, '', '/?embed_layout=clean')

      render(<EmbeddedChatbot />)

      expect(screen.queryByText('chat header')).not.toBeInTheDocument()
      expect(screen.queryByText('share.chat.poweredBy')).not.toBeInTheDocument()
      expect(screen.getByTestId('chat-area')).toBeInTheDocument()
    })
  })
})
