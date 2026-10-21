import { Button } from '@langgenius/dify-ui/button'
import { Field, FieldControl, FieldLabel } from '@langgenius/dify-ui/field'
import { Form } from '@langgenius/dify-ui/form'
import { toast } from '@langgenius/dify-ui/toast'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { COUNT_DOWN_TIME_MS, useSetCountdownLeftTime } from '@/app/components/signin/storage'
import { emailRegex } from '@/config'
import { useLocale } from '@/context/i18n'
import { useRouter, useSearchParams } from '@/next/navigation'
import { fetchLoginTenants, sendEMailLoginCode } from '@/service/common'

type MailAndCodeAuthProps = {
  isInvite: boolean
}

type TenantOption = {
  id: string
  name: string
}

export default function MailAndCodeAuth({ isInvite }: MailAndCodeAuthProps) {
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
      const ret = await sendEMailLoginCode(email, locale)
      if (ret.result === 'success') {
        setCountdownLeftTime(`${COUNT_DOWN_TIME_MS}`)
        const params = new URLSearchParams(searchParams)
        params.set('email', encodeURIComponent(email))
        params.set('token', encodeURIComponent(ret.data))
        params.set('tenant_id', selectedTenantId)
        router.push(`/signin/check-code?${params.toString()}`)
      }
    } catch (error) {
      console.error(error)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Form
      onFormSubmit={() => {
        void handleGetEMailVerificationCode()
      }}
    >
      <Field name="tenant" className="mb-3">
        <FieldLabel className="my-2 py-0 system-md-semibold text-text-secondary">
          {t(($) => $.tenantSearchLabel, { ns: 'login' })}
        </FieldLabel>
        <div className="relative mt-1">
          <FieldControl
            value={tenantQuery}
            placeholder={t(($) => $.tenantSearchPlaceholder, { ns: 'login' }) as string}
            onValueChange={(value) => {
              setTenantQuery(value)
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
      </Field>

      <Field name="email" disabled={isInvite} className="mb-2">
        <FieldLabel className="my-2 py-0 system-md-semibold text-text-secondary">
          {t(($) => $.email, { ns: 'login' })}
        </FieldLabel>
        <FieldControl
          type="email"
          autoComplete="email"
          spellCheck={false}
          disabled={isInvite}
          value={email}
          placeholder={t(($) => $.emailPlaceholder, { ns: 'login' }) as string}
          onValueChange={setEmail}
        />
        <div className="mt-3">
          <Button
            type="submit"
            loading={loading}
            disabled={loading || isLoadingTenants || !selectedTenantId || !email}
            variant="primary"
            className="w-full"
          >
            {t(($) => $['signup.verifyMail'], { ns: 'login' })}
          </Button>
        </div>
      </Field>
    </Form>
  )
}
