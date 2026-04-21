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

```bash
# 前端
cd /home/chun/modelforge/web
corepack enable pnpm    # 若已有 pnpm 可跳过
pnpm install --frozen-lockfile
pnpm build

# 后端
cd /home/chun/modelforge
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -e .
```

### 3. 注册 systemd 服务

```bash
sudo cp /home/chun/modelforge/deploy/modelforge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now modelforge.service
sudo systemctl status modelforge.service
curl -s http://127.0.0.1:8000/healthz   # 预期 {"status":"ok",...}
```

### 4. 允许 runner 无密码重启服务

`.github/workflows/deploy.yml` 里有一行 `sudo systemctl restart modelforge.service`，需要给 `chun` 账号免密权限：

```bash
sudo visudo -f /etc/sudoers.d/modelforge
# 填入：
chun ALL=(root) NOPASSWD: /bin/systemctl restart modelforge.service, /bin/journalctl -u modelforge.service *
```

### 5. 安装 GitHub self-hosted runner

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
# runner 日志
sudo journalctl -u actions.runner.9triver-modelforge.$(hostname).service -n 100 --no-pager

# 服务日志
sudo journalctl -u modelforge.service -n 100 --no-pager

# 手动拉起
sudo systemctl restart modelforge.service
```
