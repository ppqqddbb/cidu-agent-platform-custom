# 开发服务器中间件

此目录只用于开发服务器，负责启动不需要改代码的依赖服务：

- Redis
- Weaviate
- Sandbox
- Plugin Daemon
- SSRF Proxy

此目录不用于启动：

- `api`
- `web`
- `worker`
- `nginx`
- PostgreSQL

启动命令：

```bash
docker compose --env-file middleware.env -f docker-compose.yaml -p dify up -d \
  redis sandbox plugin_daemon ssrf_proxy weaviate
```

PostgreSQL 安装在开发服务器宿主机上，不在 Docker 中。容器访问宿主机 PostgreSQL 时，`middleware.env` 中的 `DB_HOST` 应写：

```env
DB_HOST=host.docker.internal
DB_USERNAME=pgadmin
DB_PASSWORD=pgadmin4357
DB_PORT=5432
DB_DATABASE=dify
DB_PLUGIN_DATABASE=dify_plugin
```

不要写 `localhost`，因为容器里的 `localhost` 指向容器自身。PostgreSQL 中需要提前创建 `dify` 和 `dify_plugin` 两个库。
