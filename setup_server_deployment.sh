#!/bin/bash
# Dify服务器部署设置脚本
# 适用于在/home/software/dify路径拉取代码的服务器

set -e

echo "🚀 开始配置Dify服务器部署..."
echo "=========================================="

# 创建目标目录
DEPLOY_DIR="/home/software/dify"
echo "📁 创建部署目录: $DEPLOY_DIR"
sudo mkdir -p "$DEPLOY_DIR"
cd "$DEPLOY_DIR"

# 检查是否已经有代码
if [ -d "$DEPLOY_DIR/docker" ]; then
    echo "📂 代码已存在，更新中..."
    git fetch origin
    git checkout custom/main
    git pull origin custom/main
else
    echo "📥 克隆代码仓库..."
    git clone http://192.168.3.201:8011/ProjectSplitting/cidu-dify-custom.git .
    git checkout custom/main
fi

echo ""
echo "✅ 代码拉取完成"

# 进入docker目录
cd docker

# 创建配置文件
echo "⚙️ 创建配置文件..."

# 创建主配置文件
if [ ! -f ".env" ]; then
    echo "创建 .env 配置文件..."
    cat > .env << 'EOF'
# ==========================================
# Dify 生产环境配置
# ==========================================

# 数据库配置
DB_TYPE=postgresql
DB_HOST=db_postgres
DB_PORT=5432
DB_USERNAME=postgres
DB_PASSWORD=your_secure_password_here  # 🔥 修改为强密码
DB_DATABASE=dify

# 向量数据库（默认weaviate，可选milvus、opensearch）
VECTOR_STORE=weaviate
WEAVIATE_ENDPOINT=http://weaviate:8080

# 域名和SSL配置
DOMAIN=your-domain.com  # 🔥 修改为你的域名
ENABLE_SSL=true

# 插件配置（已优化）
PLUGIN_PYTHON_ENV_INIT_TIMEOUT=300
PIP_MIRROR_URL=https://mirrors.aliyun.com/pypi/simple/  # 国内镜像加速

# Redis配置（使用Docker容器）
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=your_redis_password  # 🔥 建议设置

# 邮件配置（可选）
MAIL_USERNAME=
MAIL_PASSWORD=
MAIL_FROM=
MAIL_PORT=587
MAIL_SERVER=smtp.gmail.com

# 监控配置
ENABLE_OTEL=false
OTLP_BASE_ENDPOINT=

# 日志配置
LOG_LEVEL=INFO
LOG_FILE_MAX_SIZE=50
LOG_FILE_BACKUP_COUNT=10
EOF
    echo "✅ 已创建 .env 文件"
else
    echo "✅ .env 文件已存在"
fi

# 创建中间件配置文件
if [ ! -f "middleware.env" ]; then
    echo "创建 middleware.env 配置文件..."
    cat > middleware.env << 'EOF'
# 中间件服务配置

# 数据库类型
DB_TYPE=postgresql

# PostgreSQL 配置
POSTGRES_PASSWORD=your_secure_password_here  # 🔥 与 .env 一致
POSTGRES_USER=postgres
POSTGRES_DB=dify

# Redis配置
REDIS_PASSWORD=your_redis_password
EOF
    echo "✅ 已创建 middleware.env 文件"
else
    echo "✅ middleware.env 文件已存在"
fi

echo ""
echo "=========================================="
echo "📋 配置文件位置："
echo "   🔧 主配置: $DEPLOY_DIR/docker/.env"
echo "   🔧 中间件配置: $DEPLOY_DIR/docker/middleware.env"
echo ""
echo "⚡ 启动服务命令："
echo "   1. 启动中间件服务："
echo "      cd $DEPLOY_DIR/docker"
echo "      docker-compose --env-file middleware.env -f docker-compose.middleware.yaml -p dify up -d"
echo ""
echo "   2. 启动主服务："
echo "      docker-compose up -d"
echo ""
echo "🔧 管理命令："
echo "   查看日志: docker-compose logs -f"
echo "   重启服务: docker-compose restart"
echo "   停止服务: docker-compose down"
echo ""
echo "⚠️  重要提示："
echo "   1. 修改 .env 中的 DB_PASSWORD 为强密码"
echo "   2. 配置 DOMAIN 为你的域名"
echo "   3. 确保服务器防火墙开放端口"
echo "=========================================="

echo ""
echo "🎯 下一步操作："
echo "   1. 修改配置文件："
echo "      vi $DEPLOY_DIR/docker/.env"
echo "   2. 启动服务："
echo "      cd $DEPLOY_DIR/docker"
echo "      docker-compose up -d"
echo "   3. 验证服务："
echo "      docker-compose ps