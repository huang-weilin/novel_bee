const api = require("../../utils/api");
const { waitForJob } = require("../../utils/jobs");

function draftKey(projectId, seq) {
  return "draft:" + projectId + ":" + seq;
}

function lastKey(projectId, seq) {
  return "last:" + projectId + ":" + seq;
}

Page({
  data: {
    projectId: "",
    seq: 1,
    jobId: "",
    draft: null,
    job: null,
    content: "",
    chars: 0,
    progress: 5,
    message: "准备试写…",
    loading: true,
    submitting: false,
    error: "",
  },

  onLoad(options) {
    const projectId = options.projectId || "";
    const seq = Number(options.seq || 1);
    const draft = wx.getStorageSync(draftKey(projectId, seq)) || null;
    this.setData({
      projectId,
      seq,
      jobId: options.jobId || "",
      draft,
    });
    if (!options.jobId) {
      this.setData({
        loading: false,
        error: "没有找到试写任务，请返回大纲重新提交。",
      });
      return;
    }
    this.poll(options.jobId);
  },

  poll(jobId) {
    this.setData({ loading: true, error: "", jobId, content: "", chars: 0 });
    waitForJob(jobId, {
      onUpdate: (job) => {
        this.setData({
          job,
          progress: job.progress || 0,
          message: job.message || "试写中…",
        });
      },
    })
      .then((job) => {
        const result = job.result || {};
        if (job.status === "failed") {
          this.setData({
            loading: false,
            error: job.error || "试写失败",
          });
          return;
        }
        this.setData({
          loading: false,
          job,
          progress: 100,
          message: job.message || "试写完成",
          content: result.content || "",
          chars: result.chars || 0,
        });
      })
      .catch((error) => this.setData({ loading: false, error: error.message }));
  },

  confirmTrial() {
    if (!this.data.draft || !this.data.content) {
      wx.showToast({ title: "试写内容还没有准备好", icon: "none" });
      return;
    }
    const payload = {
      ...this.data.draft.payload,
      trial_text: this.data.content.slice(0, 2000),
    };
    this.setData({ submitting: true, error: "" });
    api
      .generate(this.data.projectId, payload)
      .then((job) => {
        wx.setStorageSync(lastKey(this.data.projectId, job.chapter_seq), {
          payload,
          trialWords: this.data.draft.trialWords,
        });
        wx.redirectTo({
          url:
            "/pages/chapter/chapter?projectId=" +
            this.data.projectId +
            "&seq=" +
            job.chapter_seq +
            "&jobId=" +
            job.id,
        });
      })
      .catch((error) => this.setData({ submitting: false, error: error.message }))
      .finally(() => this.setData({ submitting: false }));
  },

  retryTrial() {
    if (!this.data.draft) {
      this.backToOutline();
      return;
    }
    const payload = {
      ...this.data.draft.payload,
      target_words: this.data.draft.trialWords || 500,
    };
    this.setData({ loading: true, error: "", content: "", chars: 0 });
    api
      .trial(this.data.projectId, payload)
      .then((job) => {
        wx.setStorageSync(draftKey(this.data.projectId, job.chapter_seq), {
          payload: this.data.draft.payload,
          trialWords: this.data.draft.trialWords,
        });
        this.setData({ jobId: job.id, seq: job.chapter_seq });
        this.poll(job.id);
      })
      .catch((error) => this.setData({ loading: false, error: error.message }));
  },

  backToOutline() {
    wx.navigateBack();
  },
});
