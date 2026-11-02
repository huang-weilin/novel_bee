const api = require("../../utils/api");
const format = require("../../utils/format");
const { waitForJob } = require("../../utils/jobs");

function attributesFrom(item) {
  const attributes = {};
  const delta = (item.detail && item.detail.attributes_delta) || {};
  Object.keys(delta).forEach((key) => {
    const value = delta[key];
    if (value === null || value === undefined || typeof value === "object") {
      return;
    }
    attributes[key] = String(value);
  });
  return attributes;
}

Page({
  data: {
    projectId: "",
    seq: 1,
    nextSeq: 2,
    jobId: "",
    job: null,
    chapter: null,
    statusLabel: "",
    statusClass: "pill-muted",
    scoreText: "未评分",
    failures: [],
    reviewItems: [],
    progress: 5,
    message: "准备中…",
    loading: true,
    error: "",
  },

  onLoad(options) {
    const projectId = options.projectId || "";
    const seq = Number(options.seq || 1);
    this.setData({ projectId, seq, nextSeq: seq + 1 });
    if (options.jobId) {
      this.poll(options.jobId);
    } else {
      this.loadChapter(seq);
    }
  },

  poll(jobId) {
    this.setData({ loading: true, error: "", jobId });
    waitForJob(jobId, {
      timeout: 20 * 60 * 1000,
      onUpdate: (job) => {
        this.setData({
          job,
          progress: job.progress || 0,
          message: job.message || "生成中…",
        });
      },
    })
      .then((job) => {
        if (job.status === "failed") {
          this.setData({
            loading: false,
            job,
            error: job.error || "生成失败",
          });
          return;
        }
        const result = job.result || {};
        const quality = result.quality || null;
        const failures = ((quality && quality.failures) || []).map(
          (item, index) => ({
            key: "failure-" + index,
            text: format.failureText(item),
            suggestion: item.suggestion || "",
          })
        );
        const seq = job.chapter_seq || this.data.seq;
        this.setData({
          job,
          failures,
          seq,
          nextSeq: seq + 1,
          progress: 100,
          message: job.message || "完成",
        });
        this.loadChapter(seq);
      })
      .catch((error) => this.setData({ loading: false, error: error.message }));
  },

  loadChapter(seq) {
    api
      .getChapter(this.data.projectId, seq)
      .then((chapter) => {
        const reviewItems = (chapter.review_items || []).map((item, index) => {
          const canCharacter =
            item.kind === "character" ||
            (item.kind === "info_gain" &&
              item.reason === "unknown_character");
          return {
            ...item,
            key: "review-" + index + "-" + (item.kind || "") + ":" + (item.name || ""),
            kindLabel:
              {
                character: "人物",
                item: "物品",
                info_gain: "情报",
                foreshadowing: "伏笔",
                emotional_thread: "情感债",
                world_rule: "世界规则",
              }[item.kind] || item.kind,
            reasonLabel: format.reviewReason(item),
            canCharacter,
            canItem: item.kind === "item",
            form: {
              status:
                item.detail && typeof item.detail.status === "string"
                  ? item.detail.status
                  : "",
              quantity: "0",
              unit: "件",
            },
            registering: false,
          };
        });
        this.setData({
          chapter,
          reviewItems,
          statusLabel: format.statusLabel(chapter.status),
          statusClass: format.statusClass(chapter.status),
          scoreText: format.scoreText(chapter.score),
          loading: false,
          error: "",
        });
        wx.setNavigationBarTitle({
          title: "第" + seq + "章 · " + format.statusLabel(chapter.status),
        });
      })
      .catch((error) => this.setData({ loading: false, error: error.message }));
  },

  onReviewInput(event) {
    const index = Number(event.currentTarget.dataset.index);
    const field = event.currentTarget.dataset.field;
    const items = this.data.reviewItems.slice();
    if (!items[index] || !field) return;
    items[index] = {
      ...items[index],
      form: { ...items[index].form, [field]: event.detail.value },
    };
    this.setData({ reviewItems: items });
  },

  removeReviewItem(index) {
    const items = this.data.reviewItems.slice();
    items.splice(index, 1);
    this.setData({ reviewItems: items });
  },

  registerCharacter(event) {
    const index = Number(event.currentTarget.dataset.index);
    const item = this.data.reviewItems[index];
    if (!item) return;
    this.setData({ ["reviewItems[" + index + "].registering"]: true });
    api
      .registerCharacter(this.data.projectId, {
        name: item.name,
        status: item.form.status.trim() || null,
        core_attributes: attributesFrom(item),
        first_chapter: this.data.seq,
      })
      .then(() => {
        this.removeReviewItem(index);
        wx.showToast({ title: "已登记，可重写本章", icon: "none" });
      })
      .catch((error) => {
        this.setData({ ["reviewItems[" + index + "].registering"]: false });
        wx.showToast({ title: error.message, icon: "none" });
      });
  },

  registerItem(event) {
    const index = Number(event.currentTarget.dataset.index);
    const item = this.data.reviewItems[index];
    if (!item) return;
    const quantity = Number(item.form.quantity);
    this.setData({ ["reviewItems[" + index + "].registering"]: true });
    api
      .registerItem(this.data.projectId, {
        name: item.name,
        quantity: Number.isFinite(quantity) ? Math.max(0, quantity) : 0,
        unit: item.form.unit.trim() || "件",
        updated_chapter: this.data.seq,
      })
      .then(() => {
        this.removeReviewItem(index);
        wx.showToast({ title: "已登记，可重写本章", icon: "none" });
      })
      .catch((error) => {
        this.setData({ ["reviewItems[" + index + "].registering"]: false });
        wx.showToast({ title: error.message, icon: "none" });
      });
  },

  rewrite() {
    wx.navigateTo({
      url:
        "/pages/outline/outline?projectId=" +
        this.data.projectId +
        "&seq=" +
        this.data.seq +
        "&retry=1",
    });
  },

  nextChapter() {
    wx.navigateTo({
      url:
        "/pages/outline/outline?projectId=" +
        this.data.projectId +
        "&seq=" +
        this.data.nextSeq,
    });
  },

  copyContent() {
    const content = (this.data.chapter && this.data.chapter.content) || "";
    if (!content) return;
    wx.setClipboardData({
      data: content,
      success() {
        wx.showToast({ title: "正文已复制", icon: "success" });
      },
    });
  },

  backProject() {
    wx.reLaunch({
      url: "/pages/project/project?id=" + this.data.projectId,
    });
  },
});
