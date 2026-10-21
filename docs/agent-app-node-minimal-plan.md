# Agent App 作为 Workflow 节点的最小版实施方案

## 目标

新增一个 `agent-app` 工作流节点，用来在 workflow 里选择并执行一个已有的 `AGENT_CHAT` 应用。

首版目标不是做完整复用，而是先打通最短闭环：

- 画布中可添加 `Agent App` 节点
- 节点面板可选择一个已发布的 `AGENT_CHAT` 应用
- 节点支持配置 `query`
- `query` 可引用上游变量
- 整条 workflow 运行时，该节点能产出 `text`

## 首版范围

### 支持

- 只支持选择已发布的 `AGENT_CHAT` 应用
- 只支持一个输入字段 `query`
- 只输出 `text`
- 允许在 `query` 中引用变量

### 暂不支持

- 不支持 app 级额外 `inputs`
- 不支持 `files`
- 不支持会话延续
- 不支持 Human Input
- 不支持单节点调试
- 不支持删除依赖保护
- 不支持 `agent_log` 面板联动

## 实现原则

- 不复用现有 `Agent` 节点，新增独立的 `agent-app` 节点
- 不修改 `graphon` 依赖包
- 后端节点类型直接使用字符串 `agent-app`
- 首版优先保证整条 workflow 可运行，再补外围能力

## 节点 DSL

### 前端节点类型

```ts
type AgentAppNodeType = CommonNodeType & {
  app_id?: string
  app_name?: string
  query?: string
}
```

### 后端节点数据

建议定义：

- `type: "agent-app"`
- `app_id: str | None`
- `app_name: str | None`
- `query: str | None`

### 输出变量

首版只暴露：

- `text: string`

## 实施顺序

1. 后端先实现 `agent-app` 节点执行闭环
2. 前端把节点加到画布和配置面板
3. 补发布校验和变量输出
4. 补最小测试集

## 文件级 TODO

### 一、后端节点实现

新增文件：

- `api/core/workflow/nodes/agent_app/entities.py`
- `api/core/workflow/nodes/agent_app/agent_app_node.py`

任务：

- 定义 `AgentAppNodeData(BaseNodeData)`
- 在节点 `_run()` 中读取 `app_id` 和 `query`
- 从变量池渲染 `query`
- 校验 app 是否存在
- 校验 app 是否属于当前 tenant
- 校验 app 的 mode 是否为 `AGENT_CHAT`
- 调用 Agent App 运行逻辑
- 聚合最终文本并输出到 `text`

建议参考：

- `api/core/app/apps/agent_chat/app_generator.py`
- `api/core/app/apps/agent_chat/app_runner.py`
- `api/services/app_generate_service.py`

### 二、后端节点注册

修改文件：

- `api/core/workflow/node_factory.py`

任务：

- 在节点初始化分发逻辑里支持 `agent-app`
- 为新节点传入最小依赖
- 确保 `node_type` 使用字符串即可，不依赖 `BuiltinNodeTypes`

说明：

- `graphon.enums.NodeType` 本质是 `str`
- `BuiltinNodeTypes` 只是内置常量集合，不是必须扩展的枚举

### 三、前端枚举和节点注册

修改文件：

- `web/app/components/workflow/types.ts`
- `web/app/components/workflow/block-selector/constants.tsx`
- `web/app/components/workflow/block-icon.tsx`
- `web/app/components/workflow/nodes/components.ts`

任务：

- 新增 `BlockEnum.AgentApp = 'agent-app'`
- 在 block selector 中增加 `Agent App`
- 复用现有 Agent 图标和颜色
- 注册节点组件和面板组件

### 四、前端节点目录

新增文件：

- `web/app/components/workflow/nodes/agent-app/types.ts`
- `web/app/components/workflow/nodes/agent-app/default.ts`
- `web/app/components/workflow/nodes/agent-app/node.tsx`
- `web/app/components/workflow/nodes/agent-app/panel.tsx`
- `web/app/components/workflow/nodes/agent-app/use-config.ts`

任务：

- `types.ts` 定义节点数据结构
- `default.ts` 提供默认值和 `checkValid`
- `node.tsx` 展示 app 名称和 query 摘要
- `panel.tsx` 提供 app 选择和 query 编辑
- `use-config.ts` 负责节点 CRUD 和表单数据处理

### 五、前端 App 选择器

建议复用：

- `web/app/components/plugins/plugin-detail-panel/app-selector/app-picker.tsx`

任务：

- 仅显示 `AGENT_CHAT` 应用
- 选择后回填 `app_id` 和 `app_name`

如果没有合适的查询 hook，首版可以直接在节点面板层做过滤，不额外抽象公共逻辑。

### 六、发布校验

修改文件：

- `web/app/components/workflow/hooks/use-checklist.ts`

任务：

- 未选 app 时提示错误
- 未填 query 时提示错误

### 七、变量输出

修改文件：

- `web/app/components/workflow/nodes/_base/components/variable/utils.ts`

任务：

- 为 `agent-app` 增加输出变量定义
- 首版只暴露 `text`

## 后端执行建议

首版建议在 `agent_app_node.py` 中写一个轻量 adapter，而不是直接接控制器接口。

建议流程：

1. 根据 `app_id` 加载 `App`
2. 校验 `mode == AGENT_CHAT`
3. 解析并渲染 `query`
4. 构造最小调用参数
5. 走 Agent App 内核运行
6. 收集最终文本
7. 输出为节点结果

建议固定策略：

- `conversation_id = None`
- 不传额外 `inputs`
- 不传 `files`
- 不做会话复用

## 测试清单

### 后端

新增文件：

- `api/tests/unit_tests/core/workflow/nodes/agent_app/test_agent_app_node.py`

覆盖：

- `app_id` 不存在时报错
- 选择非 `AGENT_CHAT` app 时失败
- `query` 能从变量池解析
- 成功时节点输出包含 `text`

### 前端

新增文件：

- `web/app/components/workflow/nodes/agent-app/__tests__/default.spec.ts`
- `web/app/components/workflow/nodes/agent-app/__tests__/panel.spec.tsx`

覆盖：

- 能选择 agent app
- 空 app 或空 query 会触发校验
- 输出变量中可见 `text`

## 验收标准

- 画布里能添加 `Agent App` 节点
- 面板里能选择一个已发布的 Agent 应用
- `query` 支持引用上游变量
- workflow 发布后可正常运行该节点
- 节点执行成功后有 `text` 输出
- app 不存在或类型错误时，节点明确失败

## 延期项

以下能力不纳入最小版：

- 多轮会话复用
- 额外输入映射
- 文件输入输出
- `agent_log` 联动
- 单节点调试
- 依赖删除保护
- 与 workflow tool 的统一抽象

## 建议拆分为 3 个提交

### 提交 1

- 后端 `agent-app` 节点
- 节点注册
- 后端单测

### 提交 2

- 前端节点和面板
- block selector 注册
- checklist 校验

### 提交 3

- 输出变量
- 前端测试
- 文案和细节整理
