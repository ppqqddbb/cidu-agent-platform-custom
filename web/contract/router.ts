import type { InferContractRouterInputs } from '@orpc/contract'
import { consoleRouterContract as communityContract } from '@dify/contracts/api/console/router.gen'
import { contract as knowledgeFsContract } from '@dify/contracts/knowledge-fs/orpc.gen'
import {
  externalAppApiCreateContract,
  externalAppApiDeleteContract,
  externalAppApiListContract,
  externalAppApiUpdateContract,
  externalAppCreateContract,
  externalAppDeleteContract,
  externalAppGovernanceCredentialAlertsContract,
  externalAppGovernanceRiskReportContract,
  externalAppListContract,
  externalAppOpenAPIImportContract,
  externalAppRuntimeAvailableApisContract,
  externalAppRuntimeInvokeContract,
  externalAppUpdateContract,
} from './console/external-app-management'
import {
  knowledgeGraphCreateContract,
  knowledgeGraphDeleteContract,
  knowledgeGraphDetailContract,
  knowledgeGraphImportTemplateContract,
  knowledgeGraphOverviewContract,
  knowledgeGraphsContract,
  knowledgeGraphSearchContract,
} from './console/knowledge-graphs'
import {
  tenantAdminCreateTenantContract,
  tenantAdminTenantsContract,
  tenantManagementInfoContract,
  tenantManagementSyncContract,
  tenantManagementUpdateContract,
} from './console/tenant-management'
import { marketplaceRouterContract } from '@dify/contracts/marketplace'

export type MarketPlaceInputs = InferContractRouterInputs<typeof marketplaceRouterContract>

export const consoleRouterContract = {
  ...communityContract,
  knowledgeFs: knowledgeFsContract,
  knowledgeGraphs: {
    list: knowledgeGraphsContract,
    detail: knowledgeGraphDetailContract,
    create: knowledgeGraphCreateContract,
    delete: knowledgeGraphDeleteContract,
    search: knowledgeGraphSearchContract,
    overview: knowledgeGraphOverviewContract,
    importTemplate: knowledgeGraphImportTemplateContract,
  },
  tenantManagement: {
    info: tenantManagementInfoContract,
    update: tenantManagementUpdateContract,
    sync: tenantManagementSyncContract,
    tenants: tenantAdminTenantsContract,
    createTenant: tenantAdminCreateTenantContract,
  },
  externalAppManagement: {
    listApps: externalAppListContract,
    createApp: externalAppCreateContract,
    updateApp: externalAppUpdateContract,
    deleteApp: externalAppDeleteContract,
    listApis: externalAppApiListContract,
    createApi: externalAppApiCreateContract,
    updateApi: externalAppApiUpdateContract,
    deleteApi: externalAppApiDeleteContract,
    importOpenAPI: externalAppOpenAPIImportContract,
    listAvailableRuntimeApis: externalAppRuntimeAvailableApisContract,
    governanceRiskReport: externalAppGovernanceRiskReportContract,
    governanceCredentialAlerts: externalAppGovernanceCredentialAlertsContract,
    invokeRuntimeApi: externalAppRuntimeInvokeContract,
  },
}
