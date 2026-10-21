# 更新日志

## 2026-06-22 同步 upstream/main 到 custom/main

### 官方更新同步

- 同步官方 `upstream/main` 至 `3a3ad6ad7c`，包含官方 `1.14.2` 后续 main 分支更新。
- 引入官方 RBAC 权限体系、权限字典、权限配置接口和前端权限路由守卫调整。
- 引入 Agent v2 / Agent App 相关后端、前端页面、运行时、观测与 roster 能力。
- 同步官方 OpenAPI、Service API、Human Input 文件上传、Snippet 工作流、App Deploy、LLM polling 等能力。
- 同步 Docker SSRF proxy 加固、sandbox 版本更新、依赖与测试结构调整。
- 同步官方 i18n、前端服务层、合同路由、tag 管理、deployment 等模块重构。

### 本地定制保留

- 保留 Cidu 品牌 Logo、生产 `docker/prod` 部署目录、custom 镜像覆盖和 Neo4j/知识图谱配置。
- 保留知识图谱管理、知识图谱检索节点、工作区文件选择节点、外部应用运行时和租户管理入口。
- 保留公开聊天/嵌入式聊天文件下载链接刷新逻辑，避免二进制文件流链接过期后无法下载。
- 保留生产 Unstructured 配置示例，用于 DOC/DOCX 等文档解析。
- 保留默认租户、超级管理员跨租户查看/切换、外部托管租户成员只读等本地权限策略，并适配官方 RBAC 基线。

### 部署注意

- `docker/prod/docker-compose.yaml` 与模板中的官方基础镜像版本已从 `1.13.2` 更新为 `1.14.2`；本地生产覆盖仍使用 `cidu-dify-api:custom-main`、`cidu-dify-web:custom-main`。
- 官方 Docker 已新增 `docker/envs/` 分层 env 示例；当前生产目录仍保留本地 `docker/prod/.env` 与覆盖文件。
- 合并后建议在生产发布前执行 API 迁移、Web 构建、API 构建，并重点回归模型添加、LLM 节点、公开聊天下载、知识图谱和外部应用接口管理。
