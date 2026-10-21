# Dify 定制开发仓库

这是基于 Dify 的定制开发仓库。当前仓库不再使用官方 Dify README 的说明方式，重点记录本项目自己的开发环境、开发服务器中间件和生产部署方式。

## 环境拆分

当前约定如下：

- 开发机：源码启动 `api` 和 `web`，用于日常改代码和调试。
- 开发服务器：只运行不需要改代码的中间件服务。
- PostgreSQL：使用已经存在的外部数据库，不使用 Docker Compose 里的 PostgreSQL。
- 生产环境：仍使用完整 Docker 部署，配置文件放在 `docker/prod`。

开发服务器运行的服务包括：

```text
redis
weaviate
sandbox
plugin_daemon
ssrf_proxy
```

开发服务器不运行：

```text
api
web
worker
nginx
db_postgres
```

## 目录结构

```text
api/              后端 Flask API 源码
web/              前端 Next.js 源码
docker/
  dev/            开发服务器中间件 Compose 配置
  prod/           生产环境完整 Docker Compose 配置
  volumes/        共享运行时数据目录
  ssrf_proxy/     SSRF Proxy 配置
  nginx/          生产环境 Nginx 配置
dev/              本地开发辅助脚本
```

## 开发服务器部署

开发服务器只需要放这些目录：

```text
docker/dev/
docker/ssrf_proxy/
docker/volumes/
```

进入开发服务器后，先确认配置文件：

```text
docker/dev/middleware.env
```

数据库是开发服务器宿主机上的本地 PostgreSQL，不是 Docker 容器。开发服务器上的容器访问宿主机数据库时，`docker/dev/middleware.env` 里不要写 `localhost`，应使用 `host.docker.internal`。

PostgreSQL 需要提前准备两个库：`dify` 和 `dify_plugin`。例如：

```env
DB_HOST=host.docker.internal
DB_USERNAME=pgadmin
DB_PASSWORD=pgadmin4357
DB_DATABASE=dify
DB_PLUGIN_DATABASE=dify_plugin
```

启动开发服务器中间件：

```bash
cd docker/dev
docker compose --env-file middleware.env -f docker-compose.yaml -p dify up -d \
  redis sandbox plugin_daemon ssrf_proxy weaviate
```

这条命令只启动开发依赖服务，不会启动 Docker PostgreSQL。

查看状态：

```bash
docker compose --env-file middleware.env -f docker-compose.yaml -p dify ps
```

## 恢复本地数据库到开发服务器

如果本地 PostgreSQL 已经有开发数据，需要恢复到开发服务器上的 PostgreSQL，分别导出并恢复两个库：

```text
dify
dify_plugin
```

下面命令假设：

- 本地 PostgreSQL 地址：`localhost:5432`
- 开发服务器 PostgreSQL 地址：`192.168.3.201:5432`
- 用户名：`pgadmin`
- 密码：`pgadmin4357`

先在本地导出：

```bash
PGPASSWORD=pgadmin4357 pg_dump -h localhost -p 5432 -U pgadmin -d dify -Fc -f dify.dump
PGPASSWORD=pgadmin4357 pg_dump -h localhost -p 5432 -U pgadmin -d dify_plugin -Fc -f dify_plugin.dump
```

再恢复到开发服务器：

```bash
PGPASSWORD=pgadmin4357 pg_restore -h 192.168.3.201 -p 5432 -U pgadmin -d dify --clean --if-exists --no-owner dify.dump
PGPASSWORD=pgadmin4357 pg_restore -h 192.168.3.201 -p 5432 -U pgadmin -d dify_plugin --clean --if-exists --no-owner dify_plugin.dump
```

Windows PowerShell 可以这样执行：

```powershell
$env:PGPASSWORD = "pgadmin4357"
pg_dump -h localhost -p 5432 -U pgadmin -d dify -Fc -f dify.dump
pg_dump -h localhost -p 5432 -U pgadmin -d dify_plugin -Fc -f dify_plugin.dump
pg_restore -h 192.168.3.201 -p 5432 -U pgadmin -d dify --clean --if-exists --no-owner dify.dump
pg_restore -h 192.168.3.201 -p 5432 -U pgadmin -d dify_plugin --clean --if-exists --no-owner dify_plugin.dump
Remove-Item Env:PGPASSWORD
```

恢复前建议先备份开发服务器当前数据：

```bash
PGPASSWORD=pgadmin4357 pg_dump -h 192.168.3.201 -p 5432 -U pgadmin -d dify -Fc -f dify.server.backup.dump
PGPASSWORD=pgadmin4357 pg_dump -h 192.168.3.201 -p 5432 -U pgadmin -d dify_plugin -Fc -f dify_plugin.server.backup.dump
```

## 开发机源码启动

开发机用于运行源码版 `api` 和 `web`。

首次准备环境：

```bash
./dev/setup
```

然后检查并调整：

```text
api/.env
web/.env.local
```

`api/.env` 应该连接开发服务器上的中间件：

```env
DB_HOST=192.168.3.201
DB_USERNAME=pgadmin
DB_PASSWORD=pgadmin4357
DB_PORT=5432
DB_DATABASE=dify
REDIS_HOST=192.168.3.201
REDIS_PORT=16379
WEAVIATE_ENDPOINT=http://192.168.3.201:18080
CODE_EXECUTION_ENDPOINT=http://192.168.3.201:8194
PLUGIN_DAEMON_URL=http://192.168.3.201:5002
SSRF_PROXY_HTTP_URL=http://192.168.3.201:3128
```

`web/.env.local` 应该访问开发机本地源码 API：

```env
NEXT_PUBLIC_API_PREFIX=http://localhost:5001/console/api
NEXT_PUBLIC_PUBLIC_API_PREFIX=http://localhost:5001/api
NEXT_PUBLIC_SOCKET_URL=ws://localhost:5001
```

### Windows PowerShell 启动方式

当前 Windows 环境不要使用 `bash ./dev/start-api` 这类脚本；如果 `bash` 走到 WSL 且 WSL 没有 `/bin/bash`，脚本会启动失败。直接使用 PowerShell 原生命令启动。

终端 1，启动 API：

```powershell
cd D:\File\VSCodeFile\QDHB\cidu-dify-custom\api
uv run flask db upgrade
uv run flask run --host 0.0.0.0 --port 5001 --debug
```

终端 2，启动 Worker：

```powershell
cd D:\File\VSCodeFile\QDHB\cidu-dify-custom\api
uv run celery -A app.celery worker -P gevent -c 1 --loglevel INFO -Q dataset,dataset_summary,priority_dataset,priority_pipeline,pipeline,mail,ops_trace,app_deletion,plugin,workflow_storage,conversation,workflow,schedule_poller,schedule_executor,triggered_workflow_dispatcher,trigger_refresh_executor,retention,workflow_based_app_execution
```

终端 3，启动 Web：

```powershell
cd D:\File\VSCodeFile\QDHB\cidu-dify-custom
pnpm --dir D:\File\VSCodeFile\QDHB\cidu-dify-custom install
pnpm --dir D:\File\VSCodeFile\QDHB\cidu-dify-custom\web dev:inspect
```

可选终端 4，启动 Beat：

```powershell
cd D:\workspace\code\dify
uv --directory api run celery -A app.celery beat --loglevel INFO --scheduler celery.beat:PersistentScheduler
```

访问地址：

```text
http://localhost:3000
```

### 脚本启动方式

如果当前环境可以正常执行 Bash 脚本，也可以使用下面的脚本。

启动后端 API：

```bash
./dev/start-api
```

启动 Worker：

```bash
./dev/start-worker
```

启动前端 Web：

```bash
./dev/start-web
```

如需定时任务，再启动：

```bash
./dev/start-beat
```

访问地址：

```text
http://localhost:3000
```

## 生产环境部署

生产环境配置文件已和开发环境分开，放在：

```text
docker/prod/
```

启动生产环境：

```bash
cd docker/prod
docker compose --env-file .env -f docker-compose.yaml up -d
```

如果需要叠加定制镜像配置：

```bash
docker compose --env-file .env \
  -f docker-compose.yaml \
  -f overrides/docker-compose.local-custom.yaml \
  up -d
```

查看生产环境状态：

```bash
docker compose --env-file .env -f docker-compose.yaml ps
```

## 常用检查

检查开发服务器中间件：

```bash
cd docker/dev
docker compose --env-file middleware.env -f docker-compose.yaml -p dify ps
```

检查生产环境：

```bash
cd docker/prod
docker compose --env-file .env -f docker-compose.yaml ps
```

## 注意事项

- 开发服务器不要启动 `api` 和 `web`，它们在开发机源码启动。
- 开发服务器不要启动 Docker PostgreSQL，数据库使用现有 PostgreSQL。
- `api/.env`、`web/.env`、`docker/dev/middleware.env`、`docker/prod/.env` 都属于本项目内网开发/部署配置，已经纳入版本库。
- 后端开发规范见 `api/AGENTS.md`。
- 前端开发规范见 `web/AGENTS.md`。

