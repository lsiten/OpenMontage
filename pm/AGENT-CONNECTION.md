# 本地消费适配

PM 只管理请求、进程、租约和证据。真实 agent 仍须阅读 AGENT_GUIDE、管线 manifest、director skills、工具 registry 和 checkpoint 协议，执行创意决策并保留审批。本适配不生成脚本、分镜、素材或审批决定。

## 默认行为与生命周期

`python -m pm serve` 的应用 lifespan 拥有消费线程及其子进程。未设置可信配置时，请求保存为 `awaiting_agent`，连接与就绪均为 false。服务关闭会停止并回收当前子进程、释放租约，将未取消的中断请求保留为待恢复；没有独立守护进程或定时任务。

`PM_AGENT_CONFIG` 指向管理员提供的 UTF-8 JSON。网页不能设置该变量，API 不接受 executable、shell、路径或 endpoint。配置字段见 `AgentConfig`：绝对 executable、内容 SHA-256、固定 args、allowed_modes、本地/零服务费/已授权声明、授权和许可证据，以及可选 timeout_seconds、test_double。默认只允许已批准的 local_technical_test。配置本身是信任边界：声明不等于费用审计，也不是操作系统沙箱。管理员须审核整个入口及固定参数引用的脚本、模型来源、联网行为和权限；不要把普通 shell 或未经审计的代理作为入口。

启动与每次接手前执行独立健康握手；失败时不取得制作租约，不把“已配置”显示为“已连接”。`ready` 代表实际健康检查结果，附 checked_at；`agent_connected` 只在本项目子进程握手后、实际执行连接存活时为 true。有限执行进程退出后连接为 false，产物仍保留。

## 进程协议 v1

stdin 一行 JSON，接着 EOF。固定 `operation=health` 或 `execute`。执行输入包含 project_id、request_id、mode、attempt_token、可信派生 projects_dir/request_file 和仓库约束提示。原始需求从该项目读取，不插入 shell；不提供创意流程实现。

stdout 为每行以换行符结束的 JSON：

```json
{"protocol":1,"kind":"ready","local_only":true,"service_fee_usd":0,"test_double":true}
```

随后可发送 `kind=log`，最后发送且仅发送一次 `kind=result`；两者必须原样回传本次 project_id、request_id、attempt_token。终态 status 仅允许 completed、awaiting_human、failed、cancelled。message 为日志/错误文本，上限 4000 字符；退出码必须为 0，非零退出即失败。test_double 必须与可信配置一致。就绪握手须真实检查执行器与已安装本地模型；不得在健康检查时下载模型、生成内容或调用云服务。

示例中的 test_double=true 仅用于自制测试替身，不能据此声称 AI 或整片验收通过。真实入口须返回 false，并提供独立核实的本地、费用与授权证据。

## 持久化、恢复与取消

队列位于 projects 根的 `.pm-production/queue.sqlite3`；每个项目仅有一个不可变请求，同项目重复提交复用 request_id，显式冲突返回 409。request_id 不能被另一个项目复用。旧 production_request.json 在服务启动时导入，保持原 ID。

项目租约使用 POSIX flock，配合 SQLite 原子事务与每次尝试的 token。子进程继承租约 FD，因此父服务突然退出、子进程仍存活时，其他消费端不能同时接单。实际入口必须拥有并等待自己的工具子进程；不得脱离进程会话启动后台任务。异常退出后消费端重新接手同一 request_id，agent 必须使用 lib.checkpoint.get_next_stage 恢复并对工具副作用保持幂等。这里不保证跨外部服务副作用的“恰好一次”。

事件追加保留，重试不抹掉原失败；checkpoint 的归档继续由既有 lib.checkpoint 管理。每次尝试的原始 stdout、stderr、实际 PID/退出码保存在项目 `agent-runs/<attempt_token>/`。这些是本地诊断数据，上传前须确认无秘密或私有素材。UI 读取最后 100 条事件及日志尾部，完整历史仍在数据库与尝试目录中。

POST `/api/projects/{project_id}/run/cancel` 与 `/run/retry` 只接受 request_id。取消优先于同时到达的完成回执。恢复不会批准任何阶段：有待审批 checkpoint 时，agent 仍须等待原管线规定的人工决定。已验证成功的请求不能通过重试重复制作；需要新内容时创建新项目。完成证据失效的请求可以显式重试。

## 完成证据

completed 回执不能单独显示成功。消费端核验同 project_id/pipeline/request_id 的原管线 compose 及前序 checkpoint、必需人工审批标记、render_report、final_review、固定成片位置、ffprobe 和整片解码；技术测试额外核验 15 秒、1280×720、24fps、360 帧、三镜头。checkpoint metadata.request_id 必须关联原请求。发布不在授权范围，检查止于 compose。

成功记录绑定视频和 canonical 证据内容哈希；缺片、项目不匹配、校验失败或后续篡改均不会提供播放/下载地址。适配器不写 human_approved，不创建创意 checkpoint，不把历史手工样片当作新请求的自动执行结果。

## 当前验证边界

tests/pm/agent_double.py 是明确标注的本地 TEST DOUBLE。它可返回故障、保持活动连接或写入原 screen-demo 的 awaiting_human checkpoint，从不批准该阶段。成片校验单测使用独立的合成 compose-only manifest 和自制纯色文件；这个测试夹具不代表完整 OpenMontage 流程、真实 AI、视觉质量或原管线审批通过。

真实 CLI 还需要协议包装入口；普通 codex exec 的 JSON 事件不是本协议。选择并授权实际本地 provider 后，工程集成应在包装入口完成输入/日志/终态映射，先验证本地模型和工具调用，再开展全新项目的浏览器到成片验收。当前不默认使用已有登录、代理、云模型或下载模型。运行租约适用本项目 macOS/POSIX 环境；Windows 尚未覆盖。
