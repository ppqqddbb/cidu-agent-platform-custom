# Dify 二开 Git 工作流

这份文档用于规范 Dify 二次开发仓库的 Git 使用方式，目标是：

- 持续接收 Dify 官方仓库更新
- 保持我们的二开代码独立演进
- 避免本地开发影响官方同步分支

## 远程仓库分工

- `upstream`：Dify 官方仓库
- `origin`：我们自己的 GitLab 仓库

使用原则：

- `upstream` 只用于拉取官方更新
- `origin` 只用于推送我们自己的二开代码

## 分支分工

- `main`：官方同步分支，只做官方镜像，不做业务开发
- `custom/main`：我们的二开主分支
- `feature/*`：具体功能开发分支

## 核心规则

1. 不要在 `main` 上直接开发业务功能。
2. `main` 必须始终与 `upstream/main` 保持一致。
3. 所有二开功能都在 `custom/main` 或 `feature/*` 上完成。
4. 自定义代码只推送到 `origin`。
5. 官方更新只从 `upstream` 获取。

## 日常开发流程

新功能一律从 `custom/main` 切分支：

```powershell
git checkout custom/main
git pull origin custom/main
git checkout -b feature/你的功能名称
```

开发完成后合回 `custom/main`：

```powershell
git checkout custom/main
git merge feature/你的功能名称
git push origin custom/main
```

## 如何把 Dify 官方同步到 main

`main` 分支的职责是保存官方最新代码，不允许承载我们的二开改动。

同步官方到 `main` 的标准命令如下：

```powershell
git checkout main
git fetch upstream
git reset --hard upstream/main
```

每条命令的含义：

- `git checkout main`
  切换到官方同步分支

- `git fetch upstream`
  拉取 Dify 官方仓库的最新提交

- `git reset --hard upstream/main`
  让本地 `main` 与官方 `upstream/main` 完全一致

注意事项：

- 不要在 `main` 上做功能开发
- 不要在 `main` 上保留本地实验改动
- `git reset --hard upstream/main` 会丢弃 `main` 上的本地修改

## 将官方更新合入二开分支

当 `main` 同步完官方后，再把官方更新合入我们的二开主分支：

```powershell
git checkout custom/main
git merge main
git push origin custom/main
```

如果团队更偏好线性历史，也可以使用 `rebase`：

```powershell
git checkout custom/main
git rebase main
git push origin custom/main --force-with-lease
```

## 常用命令速查

查看远程仓库：

```powershell
git remote -v
```

查看分支跟踪关系：

```powershell
git branch -vv
```

推送二开主分支：

```powershell
git push origin custom/main
```

推送功能分支：

```powershell
git push -u origin feature/你的功能名称
```

## 推荐团队协作方式

- 指定一位维护者负责同步官方更新到 `main`
- 官方升级统一从 `main` 合入 `custom/main`
- 业务开发人员只基于 `custom/main` 开发
- 处理升级冲突时，只在 `custom/main` 解决，不要改动 `main`

## 快速操作 SOP

### 1. 同步官方 Dify 到 `main`

```powershell
git checkout main
git fetch upstream
git reset --hard upstream/main
```

### 2. 将官方更新带入二开分支

```powershell
git checkout custom/main
git merge main
git push origin custom/main
```

### 3. 从二开主分支开始开发新功能

```powershell
git checkout custom/main
git pull origin custom/main
git checkout -b feature/你的功能名称
```

## 总结

这套工作流的核心是把“官方代码”和“二开代码”严格分开：

- `main` 永远只跟踪官方 Dify
- `custom/main` 永远承载我们的二开内容
- `feature/*` 用于日常功能开发

这样在后续接收 Dify 官方更新时，会更容易定位差异、解决冲突、稳定升级。

