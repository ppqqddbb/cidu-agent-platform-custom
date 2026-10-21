import { render, screen, waitFor } from '@testing-library/react'
import Splash from '../splash'

const mocks = vi.hoisted(() => ({
  replace: vi.fn(),
  webAppLoginStatus: vi.fn(),
  fetchAccessToken: vi.fn(),
  setWebAppPassport: vi.fn(),
  setWebAppAccessToken: vi.fn(),
  webAppLogout: vi.fn(),
  webAppState: {
    shareCode: null as string | null,
    webAppAccessMode: 'public',
    embeddedUserId: null as string | null,
  },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock('@/context/web-app-context', () => ({
  useWebAppStore: (selector: (state: typeof mocks.webAppState) => unknown) => selector(mocks.webAppState),
}))

vi.mock('@/next/navigation', () => ({
  usePathname: () => '/chat/vJrfNlpLHvp183nF',
  useRouter: () => ({
    replace: mocks.replace,
  }),
  useSearchParams: () => new URLSearchParams(),
}))

vi.mock('@/service/share', () => ({
  fetchAccessToken: mocks.fetchAccessToken,
}))

vi.mock('@/service/webapp-auth', () => ({
  setWebAppAccessToken: mocks.setWebAppAccessToken,
  setWebAppPassport: mocks.setWebAppPassport,
  webAppLoginStatus: mocks.webAppLoginStatus,
  webAppLogout: mocks.webAppLogout,
}))

vi.mock('@/app/components/base/loading', () => ({
  default: () => <div>loading</div>,
}))

vi.mock('@/app/components/base/app-unavailable', () => ({
  default: ({ unknownReason }: { unknownReason?: string }) => <div>{unknownReason || 'unavailable'}</div>,
}))

describe('Splash', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.webAppState.shareCode = null
    mocks.webAppState.embeddedUserId = null
    mocks.webAppLoginStatus.mockResolvedValue({
      userLoggedIn: true,
      appLoggedIn: true,
    })
  })

  it('uses the share code from pathname before the store has been hydrated', async () => {
    render(
      <Splash>
        <div>share app</div>
      </Splash>,
    )

    await waitFor(() => {
      expect(mocks.webAppLoginStatus).toHaveBeenCalledWith('vJrfNlpLHvp183nF', undefined)
    })
    expect(await screen.findByText('share app')).toBeInTheDocument()
  })
})
