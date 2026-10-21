# 开发服务器镜像离线包

此目录用于存放开发服务器中间件所需的 Docker 镜像离线包。

当前离线包：

```text
dify-dev-middleware-images.tar
```

包含镜像：

```text
redis:6-alpine
langgenius/dify-sandbox:0.2.15
langgenius/dify-plugin-daemon:0.6.1-local
ubuntu/squid:latest
semitechnologies/weaviate:1.27.0
```

在开发服务器导入：

```bash
cd docker/dev/images
docker load -i dify-dev-middleware-images.tar
```

导入后回到 `docker/dev` 启动中间件：

```bash
cd ..
docker compose --env-file middleware.env -f docker-compose.yaml -p dify up -d \
  redis sandbox plugin_daemon ssrf_proxy weaviate
```
