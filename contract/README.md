# contract/ — 层间契约层（inter-layer contracts）

本目录存放 OpenMontage 伞仓库各层之间的**契约（contract）**定义。
伞仓库结构：`tool/`（OpenReel 通用主工具）+ `method/`（现 OpenMontage 内容）
+ `contract/`（本层）+ `remotion-composer/`（动画解说 niche，并存）。

## 为什么有这一层

`method/`（管线/制作/编排）产出「如何成片」的意图，`tool/`（OpenReel 渲染/编辑
主工具）负责把这些意图渲染/编辑成最终产物。二者之间需要一份**显式、可验证的
契约**，避免隐式耦合、保证能力层完全保全、可复现。

## 本目录内容

- `edit-spec/` — **编辑规格（edit-spec）契约**：描述「一次编辑/合成操作」的
  可验证规格（输入、目标、约束、期望输出、成本门禁）。它是 `method/` 与
  `tool/` 之间的交接契约。

## 与既有 OpenMontage 契约的关系

现 OpenMontage 已有若干契约测试与交付清单，随 Phase 2b 迁入 `method/`：

- `method/docs/contracts/` — 交付清单（如 resolve-blueprint-delivery-manifest.json）
- `method/tests/contracts/` — 契约测试（如 test_backlot_contract.py 等）

这些是 OpenMontage 既有能力的一部分，**已保留在 method/ 内**；本 `contract/`
层是在伞仓库语境下对「跨 tool/method 层」契约的**新增顶层归类**。

## 状态与后续（须由制片统筹/独立质检确认）

- 本目录为 **Phase 2c 新建的起始结构**：`edit-spec/` 提供 README、JSON Schema
  骨架与一个最小示例，用于明确「编辑规格契约」的形态。
- 具体字段/取值/门禁规则 **尚未定稿**，需由制片统筹（或独立质检）依据实际
  制作流程与 OpenReel 能力最终确定；不得以本骨架冒充已验收的正式契约。
- 关联决策：整库 AGPLv3（Phase 3）、第三方署名保留——见 method/ 与 tool/ 的 LICENSE。
