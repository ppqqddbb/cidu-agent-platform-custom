import { render, screen } from '@testing-library/react'
import useTheme from '@/hooks/use-theme'
import { Theme } from '@/types/app'
import DifyLogo from '../dify-logo'

vi.mock('@/hooks/use-theme', () => ({
  default: vi.fn(),
}))

describe('DifyLogo', () => {
  const mockUseTheme = {
    theme: Theme.light,
    themes: ['light', 'dark'],
    setTheme: vi.fn(),
    resolvedTheme: Theme.light,
    systemTheme: Theme.light,
    forcedTheme: undefined,
  }

  beforeEach(() => {
    vi.mocked(useTheme).mockReturnValue(mockUseTheme as ReturnType<typeof useTheme>)
  })

  describe('Render', () => {
    it('renders correctly with default props', () => {
      render(<DifyLogo />)
      const logo = screen.getByLabelText('Cidu')
      expect(logo).toBeInTheDocument()
      expect(logo).toHaveTextContent('Cidu')
    })
  })

  describe('Props', () => {
    it('applies custom size correctly', () => {
      const { rerender } = render(<DifyLogo size="large" />)
      let logo = screen.getByLabelText('Cidu')
      expect(logo).toHaveClass('text-[32px]')
      expect(logo).toHaveClass('leading-7')

      rerender(<DifyLogo size="small" />)
      logo = screen.getByLabelText('Cidu')
      expect(logo).toHaveClass('text-lg')
      expect(logo).toHaveClass('leading-4')
    })

    it('applies custom style correctly', () => {
      render(<DifyLogo style="monochromeWhite" />)
      const logo = screen.getByLabelText('Cidu')
      expect(logo).toHaveClass('text-white')
    })

    it('applies custom className', () => {
      render(<DifyLogo className="custom-test-class" />)
      const logo = screen.getByLabelText('Cidu')
      expect(logo).toHaveClass('custom-test-class')
    })

    it('applies custom alt text', () => {
      const { container } = render(<DifyLogo alt="" />)
      const logo = container.querySelector('[aria-label=""]')
      expect(logo).toBeInTheDocument()
    })
  })

  describe('Theme behavior', () => {
    it('uses monochromeWhite logo in dark theme when style is default', () => {
      vi.mocked(useTheme).mockReturnValue({
        ...mockUseTheme,
        theme: Theme.dark,
      } as ReturnType<typeof useTheme>)
      render(<DifyLogo style="default" />)
      const logo = screen.getByLabelText('Cidu')
      expect(logo).toHaveClass('text-white')
    })

    it('uses monochromeWhite logo in dark theme when style is monochromeWhite', () => {
      vi.mocked(useTheme).mockReturnValue({
        ...mockUseTheme,
        theme: Theme.dark,
      } as ReturnType<typeof useTheme>)
      render(<DifyLogo style="monochromeWhite" />)
      const logo = screen.getByLabelText('Cidu')
      expect(logo).toHaveClass('text-white')
    })

    it('uses default logo in light theme when style is default', () => {
      vi.mocked(useTheme).mockReturnValue({
        ...mockUseTheme,
        theme: Theme.light,
      } as ReturnType<typeof useTheme>)
      render(<DifyLogo style="default" />)
      const logo = screen.getByLabelText('Cidu')
      expect(logo).toHaveClass('text-text-primary')
    })
  })
})
