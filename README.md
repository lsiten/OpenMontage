# OpenMontage

本仓库包含 `tool/`（OpenReel）、`method/`（管线、Backlot、PM）和
`contract/`（层间契约）。制作指南见 `method/AGENT_GUIDE.md`；
OpenReel 使用说明见 `tool/README.md`。

本项目视频编辑、合成、渲染和导出统一使用 OpenReel。历史指南、技能或工具菜单中的
Remotion/HyperFrames 选项仅代表保留的能力，不能覆盖本项目的 OpenReel 制作约束，
配置 Remotion 不是 PM 启动或当前交付的前置。

## 本地 PM 入口

使用已有隔离 Python 环境（依赖见 `method/requirements*.txt`）：

```bash
cd method
python -m pm --help
python -m pm serve --port 4751
```

在仓库根启动时使用 `PYTHONPATH=method python -m pm serve --port 4751`。
`OPENMONTAGE_PROJECTS_DIR` 和 `PM_DB_PATH` 可指定隔离项目根与 SQLite 文件。
前台服务退出即停止其消费线程和执行子进程。已有在线服务由统筹维护，本次集成不重启。

PM 的规则提案明确标为离线替身。制作请求锁定 `render_runtime=openreel`，
消费协议携带同一约束；这只是交接路由，不证明实际渲染已接通。
默认没有可信 `PM_AGENT_CONFIG`，状态为未配置／`awaiting_agent`。
真实 CLI 协议包装、本地 AI 模型与 PM → OpenReel 自动成片尚未完成，
不能用 TEST DOUBLE 或历史手工样片证明整片验收通过。
详见 `method/pm/AGENT-CONNECTION.md`。

## 本地验证

测试应使用隔离项目目录和数据库，不写在线项目：

```bash
cd method
OPENMONTAGE_PROJECTS_DIR=/path/to/isolated/projects \
PM_DB_PATH=/path/to/isolated/pm.db \
python -m pytest tests/pm tests/backlot tests/contracts -q
```

生产工具 registry 包含可选外部服务，发现能力不代表允许调用。
本项目默认零付费、本地、自制或明确许可素材；不接入付费生成、密钥、敏感素材或模型下载。
保留的 Remotion 包及其契约测试用于历史能力回归，不作为 OpenReel 交付证据。
