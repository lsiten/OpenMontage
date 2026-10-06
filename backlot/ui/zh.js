export const LABELS = Object.freeze({
  research: "调研", proposal: "制作提案", idea: "选题", script: "脚本",
  scene_plan: "分镜规划", assets: "素材制作", edit: "剪辑", compose: "合成",
  publish: "发布", character_design: "角色设计", rig_plan: "绑定规划",
  real_capture: "实景录屏", synthetic_terminal: "合成终端演示",
  pending: "尚未执行", completed: "已完成", in_progress: "制作中",
  awaiting_human: "待人工审核", failed: "执行失败", unknown: "未知状态",
  pass: "通过", fail: "未通过", revise: "需修改", approved: "已批准",
  rejected: "已退回", high: "高", medium: "中", low: "低",
  cinematic: "电影短片", animation: "动画", "character-animation": "角色动画",
  "animated-explainer": "动画解说", "avatar-spokesperson": "数字人讲解",
  "talking-head": "口播", "screen-demo": "屏幕演示", "podcast-repurpose": "播客再创作",
  "clip-factory": "片段工厂", "documentary-montage": "纪录片蒙太奇",
  "framework-smoke": "框架冒烟测试", hybrid: "混合制作",
  "localization-dub": "本地化配音", pose_library: "姿态库",
  action_timeline: "动作时间线", character_qa_report: "角色质检报告",
  research_brief: "调研简报", proposal_packet: "制作提案包", brief: "创作简报",
  asset_manifest: "素材清单", edit_decisions: "剪辑决策", render_report: "渲染报告",
  final_review: "最终审查", publish_log: "发布记录", decision_log: "决策记录",
  platform: "目标平台", duration: "时长", tone: "语气", style: "风格",
  runtime: "渲染工具", pipeline: "制作流程", concepts: "创意方案",
  sources: "资料来源", "data points": "数据要点", angles: "选题角度",
  sections: "段落", scenes: "镜头", types: "类型", cuts: "剪辑点",
  outputs: "输出文件", destinations: "发布目标", "estimated cost": "预估费用",
  "generation cost": "生成费用", version: "版本", title: "标题", name: "名称",
  hook: "开场亮点", key_points: "关键要点", characters: "角色", rigs: "绑定",
  target_platform: "目标平台", target_duration_seconds: "目标时长（秒）",
  total_duration_seconds: "总时长（秒）", description: "描述", topic: "主题",
  rationale: "选择理由", status: "状态", summary: "摘要", metadata: "元数据",
  render_runtime: "渲染工具", confidence: "置信度", selected: "已选方案",
  decision: "决策", voice: "声音", music: "配乐", model: "模型", provider: "服务商",
  image: "图片", video: "视频", audio: "音频", narration: "旁白", text_card: "文字卡片",
  sound_effect: "音效", sfx: "音效", transition: "转场", overlay: "叠加层",
  wide: "远景", medium_shot: "中景", close_up: "特写", static: "固定镜头",
  pan: "摇镜头", tilt: "俯仰", zoom: "变焦", tracking: "跟拍", dolly: "推轨",
  pipeline_selection: "制作流程选择", provider_selection: "服务商选择",
  renderer_family_selection: "渲染器类别选择", render_runtime_selection: "渲染工具选择",
  composition_mode: "合成方式", playbook_selection: "风格手册选择",
  fallback_decision: "替代方案决策", budget_tradeoff: "预算权衡",
  downgrade_approval: "降级方案批准", music_source: "配乐来源",
  motion_commitment: "动态画面承诺", concept_selection: "创意方案选择",
  voice_selection: "声音选择", capability_extension: "能力扩展",
  playbook_override: "风格手册调整", visual_accuracy_check: "视觉准确性核查",
  image_generation: "图像生成", "image generation": "图像生成",
  video_generation: "视频生成", "video generation": "视频生成",
  extreme_wide: "大远景", medium_wide: "中远景", medium_close: "近景",
  extreme_close_up: "大特写", over_shoulder: "过肩镜头", insert: "插入镜头", establishing: "环境全景",
  pan_left: "向左摇镜头", pan_right: "向右摇镜头", tilt_up: "上仰", tilt_down: "下俯",
  dolly_in: "推近", dolly_out: "拉远", tracking_left: "向左跟拍", tracking_right: "向右跟拍",
  crane_up: "升降机上升", crane_down: "升降机下降", handheld: "手持", steadicam: "稳定器跟拍",
  whip_pan: "甩镜头", orbital: "环绕", zoom_in: "变焦推近", zoom_out: "变焦拉远", rack_focus: "焦点切换",
  high_key: "高调光", low_key: "低调光", natural: "自然光", golden_hour: "黄金时段",
  blue_hour: "蓝调时段", tungsten_warm: "暖钨丝灯光", neon: "霓虹光", silhouette: "剪影",
  rim_lit: "轮廓光", volumetric: "体积光", overcast_soft: "阴天柔光",
});

export function label(value) {
  if (value == null || value === "") return "—";
  return Object.hasOwn(LABELS, value) ? LABELS[value] : String(value);
}

export function pipelineLabel(value) {
  return !value || value === "unknown" ? "未识别的制作流程" : label(value);
}

export function themeLabel(value) {
  return value === "light" ? "切换为浅色主题" : "切换为深色主题";
}

export function shotLabel(value) {
  return value === "medium" ? "中景" : label(value);
}

export function loadError(error, project = false) {
  if (error.status === 404 && project) return "项目不存在或已移除";
  if (error.status === 403) return "无权读取此内容";
  if (error.status >= 500) return "本地服务暂时不可用，请稍后重试";
  return "加载失败，请检查本地服务连接后重试";
}
