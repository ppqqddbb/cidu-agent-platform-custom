import type { GetSystemFeaturesResponse } from '@dify/contracts/api/console/system-features/types.gen'
import type { QueryClient } from '@tanstack/react-query'
import type { ReactElement, ReactNode } from 'react'
import { render } from '@testing-library/react'
import { QueryClientProvider, QueryClient as TanstackQueryClient } from '@tanstack/react-query'
import { defaultSystemFeatures } from '@/features/system-features/config'
import { systemFeaturesQueryOptions } from '@/features/system-features/client'

type DeepPartial<T> = {
  [P in keyof T]?: T[P] extends object ? DeepPartial<T[P]> : T[P]
}

type RenderWithSystemFeaturesOptions = {
  systemFeatures?: DeepPartial<GetSystemFeaturesResponse>
  queryClient?: QueryClient
}

const mergeSystemFeatures = (
  overrides: DeepPartial<GetSystemFeaturesResponse> = {},
): GetSystemFeaturesResponse => ({
  ...defaultSystemFeatures,
  ...overrides,
  branding: {
    ...defaultSystemFeatures.branding,
    ...overrides.branding,
  },
  webapp_auth: {
    ...defaultSystemFeatures.webapp_auth,
    ...overrides.webapp_auth,
    sso_config: {
      ...defaultSystemFeatures.webapp_auth.sso_config,
      ...overrides.webapp_auth?.sso_config,
    },
  },
  license: {
    ...defaultSystemFeatures.license,
    ...overrides.license,
    workspaces: {
      ...defaultSystemFeatures.license.workspaces,
      ...overrides.license?.workspaces,
    },
    seats: {
      ...defaultSystemFeatures.license.seats,
      ...overrides.license?.seats,
    },
  },
  plugin_installation_permission: {
    ...defaultSystemFeatures.plugin_installation_permission,
    ...overrides.plugin_installation_permission,
  },
  plugin_manager: {
    ...defaultSystemFeatures.plugin_manager,
    ...overrides.plugin_manager,
  },
})

export const renderWithSystemFeatures = (
  ui: ReactElement,
  options: RenderWithSystemFeaturesOptions = {},
) => {
  const queryClient = options.queryClient ?? new TanstackQueryClient()
  queryClient.setQueryData(
    systemFeaturesQueryOptions().queryKey,
    mergeSystemFeatures(options.systemFeatures),
  )

  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  return render(ui, { wrapper: Wrapper })
}
