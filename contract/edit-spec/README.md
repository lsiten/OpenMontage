# edit-spec — 编辑规格契约（骨架，未定稿）

> 状态：**起始骨架（skeleton），未定稿、未验收**。字段/取值/门禁规则须由
> 制片统筹或独立质检依据实际制作流程与 OpenReel 能力最终确定。
> 不得以本骨架冒充已验收的正式契约（对应任务「不冒充真实 AI 服务已接入或
> 生成质量已验收」）。

## 用途

`edit-spec` 是 `method/`（管线/制作）与 `tool/`（OpenReel 渲染/编辑主工具）
之间的交接契约：给定一个「编辑/合成操作」的**可验证规格**，使该操作在
tool 侧可被确定地执行、校验、复现。

## 建议字段（骨架，待确认）

- `id`：规格唯一标识（稳定、可引用）。
- `intent`：编辑意图描述（自然语言 + 结构化标签）。
- `inputs`：输入素材清单（路径、类型、许可/来源——须为自制或授权明确）。
- `operations`：有序操作列表（剪辑/转场/叠加/调色/字幕/配音/配乐等）。
- `constraints`：硬约束（时长、分辨率、帧率、安全区、成本门禁上限）。
- `expected`：期望输出（格式、时长区间、质量门、可复现种子/参数）。
- `cost_gate`：成本门禁（是否允许付费服务、上限；默认零付费本地）。
- `provenance`：来源/许可/生成工具/已核实成本（默认本地自制/mock 须标注）。

## 关联

- 既有 OpenMontage 契约：`method/docs/contracts/`、`method/tests/contracts/`。
- 工具侧能力：`tool/`（OpenReel 5 apps + 10 packages）。
- 本骨架对应文件：`edit-spec.schema.json`（JSON Schema 骨架）、`example.json`
  （最小示例，非真实生成结果）。
