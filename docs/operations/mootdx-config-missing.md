# mootdx 行情源配置缺失故障处理

## 现象

后端或扫描任务日志出现类似信息：

```text
未找到配置文件 /root/.mootdx/config.json, 正在生成配置文件.
请选择最快的服务器...
请手动运行 `python -m mootdx bestip`
```

常见影响：

- 后端 `/api/health` 可能仍然正常。
- 扫描任务或行情拉取失败。
- `/api/scan/status` 可能显示行情源不可用。

## 原因

项目使用 `mootdx` 连接通达信行情服务器。`mootdx` 需要在容器内保存一个服务器选择配置：

```text
/root/.mootdx/config.json
```

如果 Docker 容器被重建、服务器定时清理容器，或者部署流程没有持久化 `/root/.mootdx`，该配置会丢失。下一次扫描时，`mootdx` 无法找到可用行情服务器，就会提示手动运行 `bestip`。

## 临时修复

在服务器项目目录执行：

```bash
docker compose exec -T backend python -m mootdx bestip
docker compose restart backend
```

如果服务名不是 `backend`，先查看服务名：

```bash
docker compose ps
```

验证：

```bash
curl http://127.0.0.1:9091/api/health
docker compose logs --tail=100 backend
```

健康检查返回：

```json
{"status":"ok"}
```

并且日志不再出现 `请手动运行 python -m mootdx bestip`，说明临时修复生效。

## 长期方案

本项目已做两层预防：

1. Docker Compose 持久化 `mootdx` 配置目录：

```yaml
volumes:
  - mootdx_config:/root/.mootdx
```

2. 后端镜像启动前自动检查 `/root/.mootdx/config.json`。如果文件不存在，会自动执行：

```bash
python -m mootdx bestip
```

相关文件：

- `docker-compose.yml`
- `docker-compose.deploy.yml`
- `K-line-back/Dockerfile`
- `K-line-back/docker-entrypoint.sh`

服务器更新后执行：

```bash
docker compose up -d --build
```

## 注意事项

不要使用下面的命令清理本项目，除非明确要删除所有持久化数据：

```bash
docker compose down -v
```

`-v` 会删除 Docker 命名卷，包括：

- `kline_data`
- `mootdx_config`

删除 `mootdx_config` 后，下次启动会重新选择行情服务器。删除 `kline_data` 会影响容器内本地数据卷。

## 强制刷新行情服务器

如果通达信节点本身变慢或失效，可以主动刷新：

```bash
docker compose exec -T backend python -m mootdx bestip
docker compose restart backend
```

也可以临时设置启动时强制刷新：

```bash
KLINE_MOOTDX_REFRESH_ON_START=true docker compose up -d
```

常规部署不建议每天强制刷新，持久化已有配置即可。
