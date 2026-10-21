import { Button } from '@langgenius/dify-ui/button'
import { toast } from '@langgenius/dify-ui/toast'
import { noop } from 'es-toolkit/function'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { resolveWebAppLoginRedirect } from '@/app/(shareLayout)/webapp-signin/login-redirect'
import Input from '@/app/components/base/input'
import { COUNT_DOWN_TIME_MS, useSetCountdownLeftTime } from '@/app/components/signin/storage'
import { emailRegex } from '@/config'
import { useLocale } from '@/context/i18n'
import { useRouter, useSearchParams } from '@/next/navigation'
import { fetchLoginTenants, sendWebAppEMailLoginCode } from '@/service/common'
import { getClientLoginFallback } from '@/utils/login-redirect'
import { replaceLoginRedirect } from '@/utils/login-redirect.client'
import { basePath } from '@/utils/var'

type TenantOption = {
  id: string
  name: string
}

export default function MailAndCodeAuth() {
  const { t } = useTranslation()
  const router = useRouter()
  const searchParams = useSearchParams()
  const emailFromLink = decodeURIComponent(searchParams.get('email') || '')
  const [email, setEmail] = useState(emailFromLink)
  const [tenantQuery, setTenantQuery] = useState('')
  const [tenantOptions, setTenantOptions] = useState<TenantOption[]>([])
  const [selectedTenantId, setSelectedTenantId] = useState('')
  const [isLoadingTenants, setIsLoadingTenants] = useState(false)
  const [hasQueriedTenant, setHasQueriedTenant] = useState(false)
  const [showTenantDropdown, setShowTenantDropdown] = useState(false)
  const [loading, setLoading] = useState(false)
  const locale = useLocale()
  const setCountdownLeftTime = useSetCountdownLeftTime()
  const redirectUrl = searchParams.get('redirect_url')

  useEffect(() => {
    if (!resolveWebAppLoginRedirect(redirectUrl, window.location.origin))
      replaceLoginRedirect(getClientLoginFallback(), router.replace, basePath)
  }, [redirectUrl, router])

  const handleFetchTenants = async (targetQuery?: string) => {
    const candidateQuery = targetQuery ?? tenantQuery
    const normalizedQuery = candidateQuery.trim()
    if (!normalizedQuery) {
      setTenantOptions([])
      setSelectedTenantId('')
      setHasQueriedTenant(false)
      setShowTenantDropdown(false)
      return
    }
    try {
      setIsLoadingTenants(true)
      const ret = await fetchLoginTenants(normalizedQuery)
      if (ret.result !== 'success') {
        setTenantOptions([])
        setSelectedTenantId('')
        setHasQueriedTenant(true)
        setShowTenantDropdown(false)
        return
      }
      const tenants = ret.tenants || []
      setTenantOptions(tenants)
      if (tenants.length === 0) {
        setTenantOptions([])
        setSelectedTenantId('')
        setShowTenantDropdown(false)
      }
      else if (!tenants.some(tenant => tenant.id === selectedTenantId)) {
        const firstTenant = tenants[0]
        if (!firstTenant)
          return
        setSelectedTenantId(ret.selected_tenant_id || firstTenant.id)
        setShowTenantDropdown(true)
      }
      setHasQueriedTenant(true)
    }
    catch {
      setTenantOptions([])
      setSelectedTenantId('')
      setHasQueriedTenant(true)
      setShowTenantDropdown(false)
    }
    finally {
      setIsLoadingTenants(false)
    }
  }

  useEffect(() => {
    if (!tenantQuery.trim()) {
      setTenantOptions([])
      setSelectedTenantId('')
      setHasQueriedTenant(false)
      setShowTenantDropdown(false)
      return
    }

    const timer = setTimeout(() => {
      void handleFetchTenants(tenantQuery)
    }, 300)

    return () => clearTimeout(timer)
  }, [tenantQuery])

  const handleGetEMailVerificationCode = async () => {
    const loginRedirect = resolveWebAppLoginRedirect(redirectUrl, window.location.origin)
    if (!loginRedirect) {
      replaceLoginRedirect(getClientLoginFallback(), router.replace, basePath)
      return
    }
    try {
      if (!email) {
        toast.error(t(($) => $['error.emailEmpty'], { ns: 'login' }))
        return
      }

      if (!emailRegex.test(email)) {
        toast.error(t(($) => $['error.emailInValid'], { ns: 'login' }))
        return
      }
      if (!selectedTenantId) {
        toast.error(t(($) => $.tenantSelectionRequired, { ns: 'login' }))
        return
      }
      setLoading(true)
      const ret = await sendWebAppEMailLoginCode(email, locale)
      if (ret.result === 'success') {
        setCountdownLeftTime(`${COUNT_DOWN_TIME_MS}`)
        const params = new URLSearchParams(searchParams)
        params.set('email', encodeURIComponent(email))
        params.set('token', encodeURIComponent(ret.data))
        params.set('tenant_id', selectedTenantId)
        params.set('redirect_url', loginRedirect.target.href)
        router.push(`/webapp-signin/check-code?${params.toString()}`)
      }
    } catch (error) {
      console.error(error)
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={noop}>
      <input type="text" className="hidden" />
      <div className="mb-2">
        <label htmlFor="tenant-search" className="system-md-semibold my-2 text-text-secondary">{t(($) => $.tenantSearchLabel, { ns: 'login' })}</label>
        <div className="relative mt-1">
          <Input
            id="tenant-search"
            type="text"
            value={tenantQuery}
            placeholder={t(($) => $.tenantSearchPlaceholder, { ns: 'login' }) as string}
            onChange={(e) => {
              setTenantQuery(e.target.value)
              setSelectedTenantId('')
              setShowTenantDropdown(true)
            }}
            onFocus={() => {
              if (tenantOptions.length > 0)
                setShowTenantDropdown(true)
            }}
            onBlur={() => {
              setTimeout(() => setShowTenantDropdown(false), 120)
            }}
          />
          {showTenantDropdown && tenantOptions.length > 0 && (
            <div className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-xl border border-components-input-border bg-components-panel-bg shadow-lg">
              {tenantOptions.map(option => (
                <button
                  key={option.id}
                  type="button"
                  className="w-full px-3 py-2 text-left text-text-primary system-md-regular hover:bg-state-base-hover"
                  onMouseDown={() => {
                    setSelectedTenantId(option.id)
                    setTenantQuery(option.name)
                    setShowTenantDropdown(false)
                  }}
                >
                  {option.name}
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="mt-2 text-components-input-text-placeholder system-xs-regular">
          {!tenantQuery.trim()
            ? t(($) => $.tenantSelectHint, { ns: 'login' })
            : isLoadingTenants
              ? t(($) => $.loading, { ns: 'common' })
              : hasQueriedTenant
                ? tenantOptions.length === 0
                    ? t(($) => $.tenantSearchNoResult, { ns: 'login' })
                    : !selectedTenantId
                        ? t(($) => $.tenantSelectionRequired, { ns: 'login' })
                        : t(($) => $.tenantSelectHint, { ns: 'login' })
                : t(($) => $.tenantSelectHint, { ns: 'login' })}
        </div>
        <div className="mt-3">
          <label htmlFor="email" className="system-md-semibold my-2 text-text-secondary">{t(($) => $.email, { ns: 'login' })}</label>
          <div className="mt-1">
            <Input
              id="email"
              type="email"
              value={email}
              placeholder={t(($) => $.emailPlaceholder, { ns: 'login' }) as string}
              onChange={e => setEmail(e.target.value)}
            />
          </div>
        </div>
        <div className="mt-3">
          <Button
            loading={loading}
            disabled={loading || isLoadingTenants || !selectedTenantId || !email}
            variant="primary"
            className="w-full"
            onClick={handleGetEMailVerificationCode}
          >
            {t(($) => $['signup.verifyMail'], { ns: 'login' })}
          </Button>
        </div>
      </div>
    </form>
  )
}
