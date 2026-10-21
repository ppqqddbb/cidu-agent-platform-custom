# Dify 服务器部署配置清单

## 📋 部署前检查清单

### 1. 服务器要求
- [ ] **操作系统**: Ubuntu 20.04+ / CentOS 8+ / Debian 11+
- [ ] **Docker**: 20.10+
- [ ] **Docker Compose**: 2.0+
- [ ] **内存**: 最低 4GB，推荐 8GB+
- [ ] **存储**: 至少 20GB 可用空间
- [ ] **CPU**: 2核+

### 2. 网络要求
- [ ] **端口开放**:
  - 80/tcp (HTTP)
  - 443/tcp (HTTPS)
  - 5001/tcp (API)
  - 5002-5003/tcp (插件服务)
  - 5432/tcp (PostgreSQL，可选)
  - 6379/tcp (Redis，可选)

### 3. 配置文件调整

#### `.env` 文件关键配置
```bash
# 数据库配置
DB_TYPE=postgresql
DB_HOST=db_postgres          # 使用Docker容器数据库
DB_PORT=5432
DB_USERNAME=postgres
DB_PASSWORD=your_secure_password_here  # 🔥 修改为强密码
DB_DATABASE=dify

# 向量数据库（可选）
VECTOR_STORE=weaviate        # 或 milvus, opensearch
WEAVIATE_ENDPOINT=http://weaviate:8080

# 域名和SSL
DOMAIN=your-domain.com       # 🔥 修改为你的域名
ENABLE_SSL=true

# 插件配置（已优化）
PLUGIN_PYTHON_ENV_INIT_TIMEOUT=300
PIP_MIRROR_URL=https://mirrors.aliyun.com/pypi/simple/

# Redis配置
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=              # 建议设置密码

# 邮件配置（可选）
MAIL_USERNAME=
MAIL_PASSWORD=
MAIL_FROM=
MAIL_PORT=587
MAIL_SERVER=smtp.gmail.com
```

#### `middleware.env` 文件配置
```bash
# 数据库类型
DB_TYPE=postgresql

# PostgreSQL配置
POSTGRES_PASSWORD=your_secure_password_here  # 🔥 与 .env 一致
POSTGRES_USER=postgres
POSTGRES_DB=dify

# Redis配置
REDIS_PASSWORD=your_redis_password           # 🔥 建议设置
```

### 4. 安全配置建议

#### A. 数据库安全
1. **修改默认密码**: 确保 PostgreSQL 和 Redis 使用强密码
2. **限制访问**: 配置防火墙只允许必要端口
3. **定期备份**: 设置数据库自动备份

#### B. SSL证书
1. **使用 Certbot**（自动证书）:
   ```bash
   # 在 docker 目录中
   docker-compose -f docker-compose.yaml up -d certbot
   ```

2. **或使用已有证书**:
   ```bash
   # 将证书文件放入 volumes/nginx/cert/
   # 修改 nginx 配置
   ```

#### C. 环境变量保护
1. **敏感信息**:
   - 数据库密码
   - API密钥
   - 邮件密码
   - Redis密码

2. **建议存储方式**:
   - 使用 Docker Secrets（生产环境）
   - 使用环境变量文件（.env）
   - 避免硬编码

### 5. 性能优化配置

#### 内存限制
```yaml
# 在 docker-compose.yaml 中为服务添加资源限制
services:
  api:
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 1G
```

#### 数据库优化
```bash
# PostgreSQL 配置优化
POSTGRES_SHARED_BUFFERS=256MB
POSTGRES_EFFECTIVE_CACHE_SIZE=1GB
POSTGRES_WORK_MEM=16MB
```

### 6. 监控和日志

#### 日志配置
```bash
# 启用日志轮转
LOG_FILE_MAX_SIZE=50
LOG_FILE_BACKUP_COUNT=10

# 日志级别
LOG_LEVEL=INFO
```

#### 健康检查
- API健康检查: `http://localhost:5001/health`
- Web健康检查: `http://localhost:3000`
- 数据库连接: 使用 `pg_isready`

### 7. 备份策略

#### 数据库备份脚本
```bash
#!/bin/bash
# 备份 PostgreSQL
docker exec $(docker ps -qf "name=dify-db_postgres") pg_dump -U postgres dify > backup_$(date +%Y%m%d_%H%M%S).sql

# 备份 Redis
docker exec $(docker ps -qf "name=dify-redis") redis-cli SAVE
docker cp $(docker ps -qf "name=dify-redis"):/data/dump.rdb redis_backup_$(date +%Y%m%d).rdb
```

### 8. 故障排除

#### 常见问题
1. **端口冲突**:
   ```bash
   # 检查端口占用
   netstat -tulpn | grep :5001
   # 修改 docker-compose.yaml 中的端口映射
   ```

2. **数据库连接失败**:
   ```bash
   # 检查数据库容器状态
   docker-compose logs db_postgres
   # 检查网络连接
   docker network ls
   ```

3. **插件初始化失败**:
   ```bash
   # 查看插件日志
   docker-compose logs plugin_daemon
   # 检查网络连接
   docker exec dify-plugin_daemon-1 curl -s https://mirrors.aliyun.com/pypi/simple/
   ```

### 9. 升级指南

#### 平滑升级步骤
1. **备份数据库和配置**
2. **拉取最新代码**
3. **更新环境变量**
4. **重新构建镜像**
5. **重启服务**

```bash
# 升级命令
cd /opt/dify
git pull origin custom/main
cd docker
docker-compose down
docker-compose pull
docker-compose up -d --build
```

### 10. 联系支持

如遇问题，请提供:
1. 错误日志
2. 环境信息
3. 复现步骤
4. 相关配置文件（已脱敏）