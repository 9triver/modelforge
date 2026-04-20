# ModelForge

> 通用模型仓库服务，对标 Hugging Face Hub 的最小自建版本。

**当前阶段**：v2/server 重写——从零实现 Git + LFS 服务端。

## 设计要点

- **协议**：Git Smart HTTP + Git-LFS Batch API
- **存储**：本地文件系统（裸 Git 仓库 + LFS 物件池）
- **元数据**：SQLite
- **认证**：Bearer Token
- **架构**：Python + FastAPI

## 快速使用

```bash
# 1. 安装
pip install -e .

# 2. 启动服务
modelforge serve --port 8000 --data ~/modelforge-data

# 3. 创建用户和 Token（另开终端）
modelforge user create alice
# 输出 Token: mf_xxx

# 4. 创建仓库
curl -X POST http://localhost:8000/api/v1/repos \
  -H "Authorization: Bearer mf_xxx" \
  -d '{"name": "my-model"}'

# 5. 用原生 git push（任意 Git 客户端均可）
git remote add origin http://alice:mf_xxx@localhost:8000/my-model.git
git push -u origin main
```

## 项目结构

```
src/modelforge/
├── config.py           应用配置
├── storage.py          仓库 / LFS / 元数据存储路径
├── db.py               SQLite ORM（用户 / 仓库 / Token）
├── auth.py             Token 校验
├── git_backend.py      git-http-backend 子进程包装
├── lfs.py              LFS Batch API 实现
├── api/                FastAPI 路由
│   ├── repos.py        仓库管理
│   └── git_routes.py   Git + LFS 协议路由
├── server.py           FastAPI 应用工厂
└── cli.py              modelforge CLI
```
