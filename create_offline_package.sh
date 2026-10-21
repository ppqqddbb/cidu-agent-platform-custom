#!/bin/bash
# Dify 离线部署包创建脚本
# 在可以访问GitLab的机器上运行

set -e

echo "📦 创建 Dify 离线部署包..."
echo "=========================================="

# 创建临时目录
TEMP_DIR=$(mktemp -d)
echo "临时目录: $TEMP_DIR"

# 检查是否在Dify目录中
if [ ! -f "docker/docker-compose.yaml" ]; then
    echo "❌ 请在Dify项目根目录运行此脚本"
    exit 1
fi

PACKAGE_NAME="dify-offline-$(date +%Y%m%d-%H%M%S)"
PACKAGE_DIR="$TEMP_DIR/$PACKAGE_NAME"

echo "📁 创建包目录: $PACKAGE_DIR"
mkdir -p "$PACKAGE_DIR"

# 1. 复制所有代码文件
echo "📋 复制代码文件..."
rsync -av --exclude='node_modules' --exclude='__pycache__' --exclude='.git' --exclude='*.pyc' . "$PACKAGE_DIR/"

# 2. 创建部署脚本
echo "⚙️  创建部署脚本..."
cat > "$PACKAGE_DIR/deploy.sh" << 'EOF'
#!/bin/bash
# Dify 离线部署脚本

set -e

echo "🚀 开始离线部署 Dify..."
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

# 进入docker目录
cd docker

# 创建配置文件
echo "⚙️  创建配置文件..."
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "✅ 已创建 .env 文件（请修改配置）"
    fi
fi

if [ ! -f "middleware.env" ]; then
    if [ -f "middleware.env.example" ]; then
        cp middleware.env.example middleware.env
        echo "✅ 已创建 middleware.env 文件"
    fi
fi

# 显示配置提示
echo ""
echo "📋 请修改以下配置文件："
echo "=========================================="
echo "1. 编辑 .env 文件："
echo "   nano docker/.env"
echo ""
echo "2. 关键配置项："
echo "   DB_PASSWORD=your_secure_password"
echo "   DOMAIN=your-domain.com"
echo "=========================================="

read -p "是否继续启动服务？(y/n): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "请先修改配置文件"
    exit 0
fi

# 启动中间件服务
echo "🚀 启动中间件服务..."
if [ -f "docker-compose.middleware.yaml" ]; then
    docker-compose --env-file middleware.env -f docker-compose.middleware.yaml -p dify up -d
    sleep 10
fi

# 启动主服务
echo "🚀 启动主服务..."
docker-compose up -d

echo ""
echo "=========================================="
echo "🎉 Dify 离线部署完成！"
echo ""
echo "📊 服务状态："
docker-compose ps
echo ""
echo "🔧 管理命令："
echo "   查看日志: docker-compose logs -f"
echo "   重启服务: docker-compose restart"
echo "   停止服务: docker-compose down"
echo "=========================================="
EOF

chmod +x "$PACKAGE_DIR/deploy.sh"

# 3. 创建配置指南
echo "📝 创建配置指南..."
cat > "$PACKAGE_DIR/CONFIGURATION.md" << 'EOF'
# Dify 离线部署配置指南

## 📋 快速开始

1. **上传包到服务器**：
   ```bash
   scp dify-offline-*.tar.gz user@your-server-ip:/tmp/
   ```

2. **在服务器上解压**：
   ```bash
   cd /opt
   tar -xzf /tmp/dify-offline-*.tar.gz
   cd dify-offline-*
   ```

3. **执行部署**：
   ```bash
   ./deploy.sh
   ```

## ⚙️ 配置文件说明

### 1. 数据库配置 (docker/.env)
```bash
# 数据库类型
DB_TYPE=postgresql

# 数据库连接
DB_HOST=db_postgres      # 使用Docker容器
DB_PORT=5432
DB_USERNAME=postgres
DB_PASSWORD=your_secure_password_here   # 🔥 修改这里
DB_DATABASE=dify

# 向量数据库（可选）
VECTOR_STORE=weaviate
```

### 2. 网络配置
```bash
# 域名
DOMAIN=your-domain.com   # 🔥 修改为你的域名

# SSL设置
ENABLE_SSL=true
```

### 3. 插件配置（已优化）
```bash
# 插件初始化超时（已优化为300秒）
PLUGIN_PYTHON_ENV_INIT_TIMEOUT=300

# PyPI镜像（已配置为阿里云镜像）
PIP_MIRROR_URL=https://mirrors.aliyun.com/pypi/simple/
```

## 🔒 安全建议

1. **修改所有默认密码**
2. **配置防火墙规则**
3. **启用SSL证书**
4. **定期备份数据库**

## 📞 故障排除

### 常见问题：
1. **端口冲突**：修改 docker-compose.yaml 中的端口映射
2. **数据库连接失败**：检查密码和网络配置
3. **插件初始化慢**：已优化配置，耐心等待

### 查看日志：
```bash
cd /opt/dify-offline-*/docker
docker-compose logs -f
```
EOF

# 4. 打包所有文件
echo "📦 打包文件..."
cd "$TEMP_DIR"
tar -czf "$PACKAGE_NAME.tar.gz" "$PACKAGE_NAME"

# 5. 输出结果
echo ""
echo "🎉 离线部署包创建完成！"
echo "=========================================="
echo "包文件: $TEMP_DIR/$PACKAGE_NAME.tar.gz"
echo ""
echo "📋 部署步骤："
echo "1. 将包文件传输到服务器："
echo "   scp \"$TEMP_DIR/$PACKAGE_NAME.tar.gz\" user@your-server-ip:/tmp/"
echo ""
echo "2. 在服务器上解压并部署："
echo "   cd /opt"
echo "   tar -xzf /tmp/$PACKAGE_NAME.tar.gz"
echo "   cd $PACKAGE_NAME"
echo "   ./deploy.sh"
echo ""
echo "3. 按照提示修改配置文件"
echo "=========================================="

# 清理临时文件（保留包文件）
echo "包文件已保留在: $TEMP_DIR/$PACKAGE_NAME.tar.gz"
echo "临时目录将在清理时删除"