# Self-hosted Deploy

推送到 `v2/server` 分支会触发 `.github/workflows/deploy.yml`，在目标机上的 self-hosted runner 里重新构建前后端并重启 systemd 服务。

## 一次性设置（在目标机 `chun@host` 上执行）

### 1. 初始化代码与数据目录

```bash
git clone https://github.com/9triver/modelforge.git /home/chun/modelforge
cd /home/chun/modelforge
git checkout v2/server

mkdir -p /home/chun/modelforge-data
```

### 2. 首次构建

> ⚠️ Ubuntu 22.04+ 的系统 Python 受 PEP 668 保护，**禁止直接 `pip install`**（会报 `externally-managed-environment`）。必须先建 venv，所有 pip / modelforge 命令都走 `.venv/bin/...`。

```bash
# 后端：先建 venv（这一步必须先做）
cd /home/chun/modelforge
sudo apt install -y python3-venv     # 若未装
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -e .

# 前端
cd /home/chun/modelforge/web
corepack enable pnpm    # 若已有 pnpm 可跳过
pnpm install --frozen-lockfile
pnpm build
```

### 3. 注册 systemd **user** 服务

本项目用 user-mode systemd（不需要 sudo 重启，workflow 里直接 `systemctl --user restart`）。

```bash
# 让 chun 的 user services 开机自启（不登录也能跑）
sudo loginctl enable-linger chun

# 放到 user unit 目录
mkdir -p ~/.config/systemd/user
cp /home/chun/modelforge/deploy/modelforge.service ~/.config/systemd/user/

systemctl --user daemon-reload
systemctl --user enable --now modelforge.service
systemctl --user status modelforge.service
curl -s http://127.0.0.1:8000/healthz   # 预期 {"status":"ok",...}
```

### 4. 安装 GitHub self-hosted runner

到 GitHub → 仓库 **Settings → Actions → Runners → New self-hosted runner**，选 Linux x64，按页面上的命令执行（大致如下，token 每次不同）：

```bash
mkdir /home/chun/actions-runner && cd /home/chun/actions-runner
curl -o actions-runner.tar.gz -L \
  https://github.com/actions/runner/releases/download/v2.319.1/actions-runner-linux-x64-2.319.1.tar.gz
tar xzf actions-runner.tar.gz

./config.sh --url https://github.com/9triver/modelforge \
  --token <GITHUB_TOKEN_FROM_WEB> \
  --labels self-hosted,Linux,modelforge \
  --name $(hostname) \
  --work _work

# 常驻：安装为 systemd 服务
sudo ./svc.sh install chun
sudo ./svc.sh start
sudo ./svc.sh status
```

> workflow 的 `runs-on: [self-hosted, Linux, modelforge]` 会匹配 `--labels` 里的标签。

## 验证

本地 push 一次：

```bash
git push origin v2/server
```

在 GitHub Actions 页面看到 Deploy job 成功，同时：

```bash
curl http://<目标机>:8000/healthz
curl http://<目标机>:8000/api/v1/repos
```

## 故障排查

```bash
# modelforge 服务日志
journalctl --user -u modelforge.service -n 100 --no-pager

# runner 日志
sudo journalctl -u "actions.runner.*" -n 100 --no-pager

# 手动重启
systemctl --user restart modelforge.service
```

## Runner 重置（已注册过要换标签时）

```bash
cd /home/chun/actions-runner

# 1. 先卸载服务
sudo ./svc.sh uninstall

# 2. 强制清理本地配置（token 已失效时用 --local 跳过服务端调用）
./config.sh remove --local

# 3. 到 GitHub 页面重新获取 token，重跑 config.sh
```
