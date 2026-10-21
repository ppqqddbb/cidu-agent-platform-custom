# Dify 服务器部署指南

针对 `/home/software/dify` 路径的服务器部署方案

## 📋 部署前提

### 服务器要求
- **操作系统**: Ubuntu 20.04+ / CentOS 8+ / Debian 11+
- **Docker**: 20.10+
- **Docker Compose**: 2.0+
- **内存**: 最低 4GB，推荐 8GB+
- **存储空间**: 至少 20GB

### 网络要求
需要开放的端口：
- **80/tcp** (HTTP)
- **443/tcp** (HTTPS)
- **5001/tcp** (API服务)
- **5002-5003/tcp** (插件服务)

## 🚀 一键部署脚本

### 方法1：使用提供的脚本
```bash
# 1. 将脚本复制到服务器
scp setup_server_deployment.sh user@your-server-ip:/tmp/

# 2. 在服务器上执行
ssh user@your-server-ip
chmod +x /tmp/setup_server_deployment.sh
sudo /tmp/setup_server_deployment.sh
```

### 方法2：手动执行
```bash
# 1. 登录服务器
ssh user@your-server-ip

# 2. 创建目录并拉取代码
sudo mkdir -p /home/software/dify
cd /home/software/dify
git clone http://192.168.3.201:8011/ProjectSplitting/cidu-dify-custom.git .
git checkout custom/main

# 3. 进入docker目录
cd docker

# 4. 创建配置文件
cp .env.example .env
cp middleware.env.example middleware.env

# 5. 修改配置文件
vi .env
# 关键配置：
# - DB_PASSWORD=your_secure_password
# - DOMAIN=your-domain.com
# - REDIS_PASSWORD=your_redis_password

# 6. 启动服务
docker-compose up -d
```

## ⚙️ 配置文件说明

### 核心配置文件
1. **`.env`** - 主配置文件
2. **`middleware.env`** - 中间件服务配置

### 必须修改的配置项

#### `.env` 文件
```bash
# 🔥 必须修改
DB_PASSWORD=your_secure_password_here    # 数据库密码
DOMAIN=your-domain.com                   # 你的域名
REDIS_PASSWORD=your_redis_password       # Redis密码

# 🔧 建议配置
VECTOR_STORE=weaviate                    # 向量数据库类型
ENABLE_SSL=true                         # 启用SSL
```

#### `middleware.env` 文件
```bash
# 🔥 必须修改
POSTGRES_PASSWORD=your_secure_password_here  # 与 .env 一致
REDIS_PASSWORD=your_redis_password           # 与 .env 一致
```

## 🔧 服务启动步骤

### 1. 启动中间件服务
```bash
cd /home/software/dify/docker
docker-compose --env-file middleware.env -f docker-compose.middleware.yaml -p dify up -d
```

### 2. 启动主服务
```bash
docker-compose up -d
```

### 3. 验证服务状态
```bash
docker-compose ps

# 预期输出：
# NAME                STATUS              PORTS
# dify-api-1          Up X minutes        0.0.0.0:5001->5001/tcp
# dify-web-1          Up X minutes        0.0.0.0:3000->3000/tcp
# dify-redis-1        Up X minutes        0.0.0.0:6379->6379/tcp
# dify-db_postgres-1  Up X minutes        0.0.0.0:5432->5432/tcp
```

## 📊 服务访问地址

### 本地访问
- **Web界面**: http://localhost:3000
- **API服务**: http://localhost:5001
- **插件服务**: http://localhost:5002-5003

### 外部访问
- **Web界面**: http://your-server-ip:3000
- **API服务**: http://your-server-ip:5001

## 🔒 安全配置

### 1. 修改默认密码
```bash
# 生成强密码
openssl rand -base64 32

# 更新配置文件
vi /home/software/dify/docker/.env
vi /home/software/dify/docker/middleware.env
```

### 2. 防火墙配置
```bash
# Ubuntu/Debian
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 5001/tcp
sudo ufw allow 3000/tcp
sudo ufw enable

# CentOS/RHEL
sudo firewall-cmd --permanent --add-port=80/tcp
sudo firewall-cmd --permanent --add-port=443/tcp
sudo firewall-cmd --permanent --add-port=5001/tcp
sudo firewall-cmd --permanent --add-port=3000/tcp
sudo firewall-cmd --reload
```

### 3. SSL证书配置
```bash
# 使用Certbot自动获取证书
cd /home/software/dify/docker
docker-compose -f docker-compose.yaml up -d certbot
```

## 🛠️ 管理命令

### 查看日志
```bash
# 查看所有服务日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f api
docker-compose logs -f web
docker-compose logs -f plugin_daemon
```

### 重启服务
```bash
# 重启所有服务
docker-compose restart

# 重启特定服务
docker-compose restart api
docker-compose restart web
```

### 停止服务
```bash
# 停止所有服务
docker-compose down

# 停止并删除数据（谨慎操作）
docker-compose down -v
```

## 🔄 更新代码

```bash
cd /home/software/dify
git pull origin custom/main
cd docker
docker-compose down
docker-compose pull
docker-compose up -d --build
```

## 🚨 故障排除

### 常见问题

#### 1. 端口冲突
```bash
# 检查端口占用
netstat -tulpn | grep :5001

# 修改docker-compose.yaml中的端口映射
vi /home/software/dify/docker/docker-compose.yaml
```

#### 2. 数据库连接失败
```bash
# 检查数据库容器状态
docker-compose logs db_postgres

# 检查网络连接
docker network ls
docker network inspect dify_default
```

#### 3. 插件初始化慢或失败
```bash
# 查看插件日志
docker-compose logs -f plugin_daemon

# 检查网络连接
docker exec dify-plugin_daemon-1 ping -c 3 mirrors.aliyun.com
```

### 日志位置
```bash
# Docker容器日志
docker-compose logs

# 应用日志（容器内）
/var/log/dify/
```

## 📞 技术支持

如遇问题，请提供：
1. 错误日志输出
2. 服务器环境信息
3. 配置文件（已脱敏）
4. 复现步骤

---

## 🎯 总结

### 部署路径
**代码位置**: `/home/software/dify`

### 关键命令
```bash
# 进入部署目录
cd /home/software/dify/docker

# 启动服务
docker-compose up -d

# 查看状态
docker-compose ps
```

### 验证部署成功
1. 访问 http://your-server-ip:3000
2. 查看容器状态 `docker-compose ps`
3. 检查日志 `docker-compose logs --tail=20`

已优化的配置：
- ✅ 插件初始化超时增加到300秒
- ✅ 配置国内PyPI镜像加速
- ✅ 完整的生产环境配置