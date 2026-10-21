import type agentV2 from '../i18n/en-US/agent-v-2.json'
import type appAnnotation from '../i18n/en-US/app-annotation.json'
import type appApi from '../i18n/en-US/app-api.json'
import type appDebug from '../i18n/en-US/app-debug.json'
import type appLog from '../i18n/en-US/app-log.json'
import type appOverview from '../i18n/en-US/app-overview.json'
import type app from '../i18n/en-US/app.json'
import type billing from '../i18n/en-US/billing.json'
import type common from '../i18n/en-US/common.json'
import type custom from '../i18n/en-US/custom.json'
import type datasetCreation from '../i18n/en-US/dataset-creation.json'
import type datasetDocuments from '../i18n/en-US/dataset-documents.json'
import type datasetHitTesting from '../i18n/en-US/dataset-hit-testing.json'
import type datasetPipeline from '../i18n/en-US/dataset-pipeline.json'
import type datasetSettings from '../i18n/en-US/dataset-settings.json'
import type dataset from '../i18n/en-US/dataset.json'
import type deployments from '../i18n/en-US/deployments.json'
import type deviceFlow from '../i18n/en-US/device-flow.json'
import type education from '../i18n/en-US/education.json'
import type explore from '../i18n/en-US/explore.json'
import type layout from '../i18n/en-US/layout.json'
import type login from '../i18n/en-US/login.json'
import type oauth from '../i18n/en-US/oauth.json'
import type permissionKeys from '../i18n/en-US/permission-keys.json'
import type permission from '../i18n/en-US/permission.json'
import type pipeline from '../i18n/en-US/pipeline.json'
import type pluginTags from '../i18n/en-US/plugin-tags.json'
import type pluginTrigger from '../i18n/en-US/plugin-trigger.json'
import type plugin from '../i18n/en-US/plugin.json'
import type register from '../i18n/en-US/register.json'
import type runLog from '../i18n/en-US/run-log.json'
import type share from '../i18n/en-US/share.json'
import type snippet from '../i18n/en-US/snippet.json'
import type time from '../i18n/en-US/time.json'
import type tools from '../i18n/en-US/tools.json'
import type workflow from '../i18n/en-US/workflow.json'
import { kebabCase } from 'string-ts'

type RawResources = {
  app: typeof app
  appAnnotation: typeof appAnnotation
  appApi: typeof appApi
  appDebug: typeof appDebug
  appLog: typeof appLog
  appOverview: typeof appOverview
  agentV2: typeof agentV2
  billing: typeof billing
  common: typeof common
  custom: typeof custom
  dataset: typeof dataset
  datasetCreation: typeof datasetCreation
  datasetDocuments: typeof datasetDocuments
  datasetHitTesting: typeof datasetHitTesting
  datasetPipeline: typeof datasetPipeline
  datasetSettings: typeof datasetSettings
  deployments: typeof deployments
  deviceFlow: typeof deviceFlow
  education: typeof education
  explore: typeof explore
  layout: typeof layout
  login: typeof login
  oauth: typeof oauth
  permission: typeof permission
  permissionKeys: typeof permissionKeys
  pipeline: typeof pipeline
  plugin: typeof plugin
  pluginTags: typeof pluginTags
  pluginTrigger: typeof pluginTrigger
  register: typeof register
  runLog: typeof runLog
  share: typeof share
  snippet: typeof snippet
  time: typeof time
  tools: typeof tools
  workflow: typeof workflow
}

// This type-only bridge exposes runtime plural base keys; selector types cannot require callers to pass count.
type PluralBaseResources = {
  agentV2: {
    'agentDetail.access.workflow.nodeCount': string
    'agentDetail.configure.buildDraft.changesToApply': string
    'agentDetail.configure.publishImpact.workflowCount': string
  }
  app: {
    'accessControlDialog.groups': string
    'accessControlDialog.members': string
  }
  billing: {
    'plansCommon.teamMember': string
  }
  common: {
    [key: `mainNav.${string}`]: string
    [key: `navigation.${string}`]: string
    [key: `stepByStepTour.${string}`]: string
    'mainNav.help.docs': string
    'mainNav.help.learnDify': string
    'mainNav.help.openMenu': string
    'mainNav.help.stepByStepTour': string
    'mainNav.webApps.noResults': string
    'mainNav.webApps.openApp': string
    'mainNav.webApps.searchPlaceholder': string
    'navigation.skipToMain': string
    'stepByStepTour.completion.description': string
    'stepByStepTour.completion.dismiss': string
    'stepByStepTour.completion.label': string
    'stepByStepTour.completion.title': string
    'stepByStepTour.duration': string
    'stepByStepTour.markTaskComplete': string
    'stepByStepTour.markTaskIncomplete': string
    'stepByStepTour.minimize': string
    'stepByStepTour.progressAriaValueText': string
    'stepByStepTour.restore': string
    'stepByStepTour.skip': string
    'stepByStepTour.skipRecovery.dismiss': string
    'stepByStepTour.skipRecovery.label': string
    'stepByStepTour.skipRecovery.message': string
    'stepByStepTour.stepLabel': string
    'stepByStepTour.tasks.home.description': string
    'stepByStepTour.tasks.home.noCreate.description': string
    'stepByStepTour.tasks.home.noCreate.title': string
    'stepByStepTour.tasks.home.primaryActionLabel': string
    'stepByStepTour.tasks.home.title': string
    'stepByStepTour.tasks.integration.description': string
    'stepByStepTour.tasks.integration.noPermission.description': string
    'stepByStepTour.tasks.integration.noPermission.title': string
    'stepByStepTour.tasks.integration.primaryActionLabel': string
    'stepByStepTour.tasks.integration.title': string
    'stepByStepTour.tasks.knowledge.description': string
    'stepByStepTour.tasks.knowledge.noPermission.description': string
    'stepByStepTour.tasks.knowledge.noPermission.primaryActionLabel': string
    'stepByStepTour.tasks.knowledge.noPermission.title': string
    'stepByStepTour.tasks.knowledge.primaryActionLabel': string
    'stepByStepTour.tasks.knowledge.title': string
    'stepByStepTour.tasks.studio.description': string
    'stepByStepTour.tasks.studio.noCreate.description': string
    'stepByStepTour.tasks.studio.noCreate.title': string
    'stepByStepTour.tasks.studio.primaryActionLabel': string
    'stepByStepTour.tasks.studio.title': string
    'stepByStepTour.title': string
    'markdown.codeBlock.chart.loading': string
    'markdown.codeBlock.chart.switch': string
    'markdown.codeBlock.chartType.bar': string
    'markdown.codeBlock.chartType.line': string
    'markdown.codeBlock.chartType.pie': string
    'members.assignRolesModal.singleDescription': string
    'members.editRole': string
    'members.emailRecipients': string
    'members.emailRecipientsTip': string
    'members.emailRequired': string
    'members.invalidRole': string
    'members.inviteFailed': string
    'members.inviteLimitExceeded': string
    'members.memberDetails.assignedRole': string
    'members.recipientCountExceedsSeats': string
    'members.recipientCount': string
    'members.removeFromTeamConfirmDescription': string
    'members.removeFromTeamConfirmTitle': string
    'members.roles': string
    'members.seatsRemaining': string
    'members.sendInviteCount': string
    'modelProvider.auth.openAIResponsesAPITip': string
    'modelProvider.ranOutDate': string
    'modelProvider.selector.hideIncompatibleModels': string
    'modelProvider.selector.showIncompatibleModels': string
    'modelProvider.selector.suggestionTip': string
    'modelProvider.used': string
    'operation.downloading': string
    'voiceInput.starting': string
    'voiceInput.stop': string
  }
  dataset: {
    [key: `newKnowledge.${string}`]: string
    docAllEnabled: string
    'firstEmpty.noCreatePermission': string
    partialEnabled: string
  }
  datasetDocuments: {
    'segment.characters': string
    'segment.childChunks': string
    'segment.chunks': string
    'segment.parentChunks': string
    'segment.searchResults': string
  }
  deployments: {
    'access.members.groupCount': string
    'access.members.memberCount': string
    'createGuide.target.bindingCount': string
    'createGuide.target.envVarCount': string
    'deployDrawer.bindingCount': string
    'deployDrawer.envVarCount': string
    'overview.apiKeysCount': string
    'overview.apiTokenSummary.environments': string
    'overview.chip.behind': string
    'overview.chip.behindTooltip': string
    'overview.latestRelease.releaseCount': string
    'versions.disabledReason.releaseInUse': string
  }
  permission: {
    'accessRule.summary': string
    'role.copyMembersDescription': string
  }
  workflow: {
    'changeHistory.stepBackward': string
    'changeHistory.stepForward': string
    'nodes.iteration.error': string
    'nodes.iteration.iteration': string
    'nodes.loop.error': string
    'nodes.loop.loop': string
  }
}

export type Resources = Omit<RawResources, keyof PluralBaseResources> & {
  [Ns in keyof PluralBaseResources]: Ns extends keyof RawResources
    ? RawResources[Ns] & PluralBaseResources[Ns]
    : PluralBaseResources[Ns]
}

export const defaultNS = 'app' as const

export const namespaces = [
  'app',
  'appAnnotation',
  'appApi',
  'appDebug',
  'appLog',
  'appOverview',
  'agentV2',
  'billing',
  'common',
  'custom',
  'dataset',
  'datasetCreation',
  'datasetDocuments',
  'datasetHitTesting',
  'datasetPipeline',
  'datasetSettings',
  'deployments',
  'deviceFlow',
  'education',
  'explore',
  'layout',
  'login',
  'oauth',
  'permission',
  'permissionKeys',
  'pipeline',
  'plugin',
  'pluginTags',
  'pluginTrigger',
  'register',
  'runLog',
  'share',
  'snippet',
  'time',
  'tools',
  'workflow',
] as const satisfies ReadonlyArray<keyof Resources>
export type Namespace = (typeof namespaces)[number]

export const namespacesInFileName = namespaces.map((ns) => kebabCase(ns))
export type NamespaceInFileName = (typeof namespacesInFileName)[number]
