#!/bin/bash
# ciduai.daneng.cc 服务器一键部署脚本
# 适用于 /home/software/dify 路径

set -e

echo "🚀 开始部署 ciduai.daneng.cc 服务..."

# 检查是否在正确目录
if [ ! -d "/home/software/dify" ]; then
    echo "❌ 错误：请确保在 /home/software/dify 目录下执行"
    exit 1
fi

cd /home/software/dify

# 1. 更新代码到最新版本
echo "📥 更新代码到最新版本..."
git pull origin custom/main

# 2. 进入docker目录
cd docker

# 3. 检查并复制配置文件
if [ -f ".env.ciduai.daneng.cc" ] && [ -f "middleware.env.ciduai.daneng.cc" ]; then
    echo "✅ 找到生产环境配置文件"
    
    # 备份现有配置文件（如果存在）
    if [ -f ".env" ]; then
        cp .env ".env.backup.$(date +%Y%m%d_%H%M%S)"
    fi
    if [ -f "middleware.env" ]; then
        cp middleware.env "middleware.env.backup.$(date +%Y%m%d_%H%M%S)"
    fi
    
    # 使用生产环境配置
    cp .env.ciduai.daneng.cc .env
    cp middleware.env.ciduai.daneng.cc middleware.env
    echo "✅ 已应用生产环境配置 (ciduai.daneng.cc)"
else
    echo "⚠️  警告：未找到生产环境配置文件，使用默认配置"
    if [ ! -f ".env" ]; then
        cp .env.example .env
        echo "⚠️  请手动编辑 .env 文件："
        echo "    vi .env"
        echo "    主要修改："
        echo "    - DOMAIN=ciduai.daneng.cc"
        echo "    - DB_PASSWORD=your_secure_password"
        echo "    - REDIS_PASSWORD=your_redis_password"
        exit 1
    fi
fi

# 4. 停止现有服务（如果正在运行）
echo "🛑 停止现有服务..."
docker compose down 2>/dev/null || true

# 5. 启动中间件服务
echo "🔧 启动数据库和Redis服务..."
docker compose --env-file middleware.env -f docker-compose.middleware.yaml -p dify up -d

# 6. 等待数据库就绪
echo "⏳ 等待数据库服务就绪..."
sleep 15

# 7. 启动主服务
echo "🚀 启动主服务..."
docker compose up -d

# 8. 显示部署状态
echo "📊 部署状态："
docker compose ps

# 9. 显示访问信息
echo ""
echo "🎉 部署完成！"
echo "================================"
echo "🌐 访问地址："
echo "  Web界面: http://ciduai.daneng.cc"
echo "  API服务: https://ciduai.daneng.cc/api"
echo "  API文档: https://ciduai.daneng.cc/api/docs"
echo ""
echo "🔍 服务端口映射："
echo "  - Web: 3000 -> 80 (HTTP)"
echo "  - API: 5001 -> 443 (HTTPS)"
echo "  - 插件: 5002-5003 -> 5002-5003"
echo ""
echo "📝 重要配置："
echo "  - 域名: ciduai.daneng.cc"
echo "  - 数据库: PostgreSQL (容器内)"
echo "  - Redis: Redis (容器内)"
echo "  - 插件超时: 300秒"
echo "  - PyPI镜像: 阿里云镜像"
echo ""
echo "📋 检查服务状态："
echo "  cd /home/software/dify/docker"
echo "  docker compose ps"
echo "  docker compose logs -f"
echo ""
echo "🚨 请注意："
echo "  1. 确保域名 ciduai.daneng.cc 已解析到服务器IP"
echo "  2. 确保服务器防火墙开放相应端口 (80, 443, 5002-5003)"
echo "  3. 首次启动可能需要5-10分钟安装插件依赖"
echo "================================"

# 10. 显示最近日志
echo "📜 最近日志（最后10行）："
docker compose logs --tail=10