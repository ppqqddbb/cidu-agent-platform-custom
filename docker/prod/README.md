# 生产环境 Docker 配置

此目录只保留生产环境的主入口配置，开发环境中间件配置在 `docker/dev`。

## 目录结构

- `.env`：当前生产环境使用的环境变量。
- `.env.example`：完整环境变量参考模板。
- `docker-compose.yaml`：生产环境主 Compose 文件。
- `overrides/`：可选覆盖配置，例如使用本地定制镜像。
- `profiles/`：按域名或场景保存的环境配置档案。
- `tools/`：Compose 生成、环境变量同步等辅助脚本。
- `docs/`：部署说明图片等文档素材。

## 启动生产环境

```bash
cd docker/prod
docker compose --env-file .env -f docker-compose.yaml up -d
```

## 使用定制镜像覆盖

生产环境发布本地定制代码时，需要先在本机重新构建定制镜像：

```bash
docker build -t cidu-dify-api:custom-main -f api/Dockerfile .
docker build -t cidu-dify-web:custom-main -f web/Dockerfile .
```

`api`、`worker`、`worker_beat` 共用 `cidu-dify-api:custom-main`，`web` 使用 `cidu-dify-web:custom-main`。构建完成后通过定制覆盖文件启动：

```bash
cd docker/prod
docker compose --env-file .env \
  -f docker-compose.yaml \
  -f overrides/docker-compose.local-custom.yaml \
  up -d
```

也可以只覆盖 API 或 Web：

```bash
docker compose --env-file .env -f docker-compose.yaml -f overrides/docker-compose.local-api.yaml up -d
docker compose --env-file .env -f docker-compose.yaml -f overrides/docker-compose.local-web.yaml up -d
```

## 辅助脚本

重新生成主 Compose 文件：

```bash
cd docker/prod
python tools/generate_docker_compose
```

同步 `.env.example` 中新增的变量到 `.env`：

```bash
cd docker/prod
python tools/dify-env-sync.py --dir .
```
