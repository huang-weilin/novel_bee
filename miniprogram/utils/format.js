const STATUS_LABELS = {
  planned: "计划中",
  trial: "试写",
  generating: "生成中",
  pending: "待确认",
  final: "定稿",
  queued: "排队中",
  running: "生成中",
  done: "完成",
  failed: "失败",
};

const REVIEW_KIND_LABELS = {
  character: "人物",
  item: "物品",
  info_gain: "情报",
  foreshadowing: "伏笔",
  emotional_thread: "情感债",
  world_rule: "世界规则",
};

const REVIEW_REASON_LABELS = {
  unknown_character: "记忆里还没有这个人物",
  unknown_item: "物品账本里还没有这个物品",
  foreshadowing_already_exists: "同名伏笔已经存在",
  over_plant_budget: "本章新埋伏笔超过上限",
  target_chapter_not_future: "伏笔回收目标章必须晚于本章",
  no_open_foreshadowing: "没有匹配的未回收伏笔",
  low_confidence: "抽取置信度不足",
};

function statusLabel(status) {
  return STATUS_LABELS[status] || status || "未知";
}

function statusClass(status) {
  if (status === "final") return "pill-final";
  if (status === "pending") return "pill-pending";
  if (status === "failed") return "pill-failed";
  return "pill-muted";
}

function reviewKind(item) {
  const kind = (item && item.kind) || "";
  const name = (item && item.name) || "";
  return (REVIEW_KIND_LABELS[kind] || kind) + "「" + name + "」";
}

function reviewReason(item) {
  const reason = (item && item.reason) || "";
  return REVIEW_REASON_LABELS[reason] || reason || "需要人工确认";
}

function scoreText(score) {
  return score === null || score === undefined ? "未评分" : score + " 分";
}

function failureText(finding) {
  const severity = (finding && finding.severity) || "";
  const rule = (finding && finding.rule_id) || "";
  const evidence = (finding && finding.evidence) || "";
  return "[" + severity + "] " + rule + " " + evidence;
}

module.exports = {
  statusLabel,
  statusClass,
  reviewKind,
  reviewReason,
  scoreText,
  failureText,
};
