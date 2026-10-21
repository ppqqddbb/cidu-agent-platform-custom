#!/bin/bash
# Dify 服务器一键部署脚本
# 使用方法: ./deploy_to_server.sh

set -e

echo "🚀 开始部署 Dify 到服务器..."
echo "=========================================="

# 检查Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装，请先安装 Docker"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose 未安装，请先安装 Docker Compose"
    exit 1
fi

echo "✅ Docker 和 Docker Compose 已安装"

# 创建部署目录
DEPLOY_DIR="/opt/dify"
echo "📁 创建部署目录: $DEPLOY_DIR"
sudo mkdir -p $DEPLOY_DIR
cd $DEPLOY_DIR

# 克隆代码（如果尚未克隆）
if [ ! -d "$DEPLOY_DIR/docker" ]; then
    echo "📥 克隆代码仓库..."
    git clone http://192.168.3.201:8011/ProjectSplitting/cidu-dify-custom.git .
else
    echo "📥 更新代码仓库..."
    git pull origin custom/main
fi

# 进入docker目录
cd docker

# 创建配置文件
echo "⚙️  创建配置文件..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "✅ 已创建 .env 文件，请根据实际情况修改配置"
fi

if [ ! -f "middleware.env" ]; then
    cp middleware.env.example middleware.env
    echo "✅ 已创建 middleware.env 文件"
fi

# 显示关键配置提示
echo ""
echo "📋 请检查以下关键配置："
echo "=========================================="
echo "1. 数据库配置 (编辑 .env 文件):"
echo "   DB_HOST=db_postgres  # 使用Docker数据库"
echo "   DB_USERNAME=postgres"
echo "   DB_PASSWORD=your_secure_password"
echo ""
echo "2. 网络配置:"
echo "   DOMAIN=your-domain.com  # 你的域名"
echo "   ENABLE_SSL=true         # 是否启用SSL"
echo ""
echo "3. 插件配置 (已优化):"
echo "   PLUGIN_PYTHON_ENV_INIT_TIMEOUT=300"
echo "   PIP_MIRROR_URL=https://mirrors.aliyun.com/pypi/simple/"
echo "=========================================="

read -p "是否已检查配置？(y/n): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "请先修改配置文件，然后重新运行脚本"
    exit 1
fi

# 启动服务
echo "🚀 启动 Dify 服务..."
echo "=========================================="

# 启动中间件服务（数据库、Redis等）
echo "1. 启动中间件服务..."
docker-compose --env-file middleware.env -f docker-compose.middleware.yaml -p dify up -d

# 等待数据库就绪
echo "⏳ 等待数据库就绪..."
sleep 10

# 启动主服务
echo "2. 启动主服务..."
docker-compose up -d

# 检查服务状态
echo "3. 检查服务状态..."
docker-compose ps

echo ""
echo "=========================================="
echo "🎉 Dify 部署完成！"
echo ""
echo "📊 服务状态:"
echo "   API服务: http://localhost:5001"
echo "   Web界面: http://localhost:3000"
echo "   插件服务: http://localhost:5002-5003"
echo ""
echo "🔧 管理命令:"
echo "   查看日志: docker-compose logs -f"
echo "   重启服务: docker-compose restart"
echo "   停止服务: docker-compose down"
echo "   更新代码: git pull && docker-compose up -d --build"
echo ""
echo "⚠️  注意事项:"
echo "   1. 首次启动需要初始化数据库，请耐心等待"
echo "   2. 插件依赖安装可能需要几分钟时间"
echo "   3. 确保服务器防火墙开放相应端口"
echo "=========================================="

# 显示容器状态
echo ""
echo "📦 容器运行状态:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep dify