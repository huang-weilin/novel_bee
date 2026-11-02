const api = require("../../utils/api");

const TRIAL_WORD_OPTIONS = [300, 500, 800];

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
    isRetry: false,
    project: null,
    sceneFields: [],
    title: "",
    targetWords: "2000",
    pov: "第三人称",
    outline: "",
    style: "",
    characterBrief: "",
    trialWordOptions: TRIAL_WORD_OPTIONS,
    trialWordIndex: 1,
    submitting: false,
    loading: true,
    error: "",
  },

  onLoad(options) {
    const seq = Number(options.seq || 1);
    this.setData({
      projectId: options.projectId || "",
      seq,
      isRetry: options.retry === "1",
    });
    this.load(seq);
  },

  load(seq) {
    const projectId = this.data.projectId;
    Promise.all([api.getProject(projectId), api.genres()])
      .then(([project, genres]) => {
        const key = (project.profile && project.profile.key) || project.genre;
        const profile = (genres.genres || []).find(
          (item) => item.key === key || item.label === project.genre
        );
        const fields = ((profile && profile.scene_fields) || []).map((item) => ({
          name: item.name,
          label: item.label,
          required: Boolean(item.required),
          value: "",
        }));

        const saved =
          wx.getStorageSync(draftKey(projectId, seq)) ||
          wx.getStorageSync(lastKey(projectId, seq));
        if (saved && saved.payload) {
          this.applyDraft(saved.payload, fields, saved.trialWords);
        } else {
          this.setData({ sceneFields: fields });
        }
        this.setData({ project, loading: false });
        wx.setNavigationBarTitle({
          title: this.data.isRetry ? "重写第" + seq + "章" : "大纲确认",
        });
      })
      .catch((error) => this.setData({ loading: false, error: error.message }));
  },

  applyDraft(payload, fields, trialWords) {
    const plan = payload.scene_plan || {};
    const filled = fields.map((field) => ({
      ...field,
      value: typeof plan[field.name] === "string" ? plan[field.name] : "",
    }));
    const index = TRIAL_WORD_OPTIONS.indexOf(Number(trialWords));
    this.setData({
      sceneFields: filled,
      title: payload.title || "",
      targetWords: String(payload.target_words || 2000),
      pov: payload.pov || "第三人称",
      outline: payload.outline || "",
      style: payload.style_constraints || "",
      characterBrief: payload.character_brief || "",
      trialWordIndex: index >= 0 ? index : 1,
    });
  },

  onInput(event) {
    const field = event.currentTarget.dataset.field;
    if (!field) return;
    this.setData({ [field]: event.detail.value });
  },

  onSceneInput(event) {
    const index = Number(event.currentTarget.dataset.index);
    const fields = this.data.sceneFields.slice();
    if (!fields[index]) return;
    fields[index] = { ...fields[index], value: event.detail.value };
    this.setData({ sceneFields: fields });
  },

  onTrialWordChange(event) {
    this.setData({ trialWordIndex: Number(event.detail.value) });
  },

  collectPayload() {
    const outline = this.data.outline.trim();
    if (!outline) {
      wx.showToast({ title: "先写本章大纲", icon: "none" });
      return null;
    }
    const targetWords = Number(this.data.targetWords);
    if (!Number.isFinite(targetWords) || targetWords < 200 || targetWords > 20000) {
      wx.showToast({ title: "目标字数要在 200–20000 之间", icon: "none" });
      return null;
    }
    const plan = {};
    for (const field of this.data.sceneFields) {
      const value = String(field.value || "").trim();
      if (value) plan[field.name] = value;
    }
    const payload = {
      outline,
      target_words: targetWords,
      pov: this.data.pov.trim() || "第三人称",
      style_constraints: this.data.style.trim(),
      character_brief: this.data.characterBrief.trim(),
      scene_plan: plan,
    };
    const title = this.data.title.trim();
    if (title) payload.title = title;
    if (this.data.isRetry) payload.chapter_seq = this.data.seq;
    return payload;
  },

  saveDraft(projectId, seq, payload, trialWords) {
    const data = { payload, trialWords };
    wx.setStorageSync(draftKey(projectId, seq), data);
    wx.setStorageSync(lastKey(projectId, seq), data);
  },

  startTrial() {
    const payload = this.collectPayload();
    if (!payload) return;
    const trialWords = TRIAL_WORD_OPTIONS[this.data.trialWordIndex];
    const trialPayload = {
      ...payload,
      target_words: trialWords,
    };
    this.setData({ submitting: true, error: "" });
    api
      .trial(this.data.projectId, trialPayload)
      .then((job) => {
        const seq = job.chapter_seq || this.data.seq;
        this.saveDraft(this.data.projectId, seq, payload, trialWords);
        wx.navigateTo({
          url:
            "/pages/trial/trial?projectId=" +
            this.data.projectId +
            "&seq=" +
            seq +
            "&jobId=" +
            job.id,
        });
      })
      .catch((error) => this.setData({ submitting: false, error: error.message }))
      .finally(() => this.setData({ submitting: false }));
  },

  startGenerate() {
    const payload = this.collectPayload();
    if (!payload) return;
    this.setData({ submitting: true, error: "" });
    api
      .generate(this.data.projectId, payload)
      .then((job) => {
        const seq = job.chapter_seq || this.data.seq;
        this.saveDraft(
          this.data.projectId,
          seq,
          payload,
          TRIAL_WORD_OPTIONS[this.data.trialWordIndex]
        );
        wx.navigateTo({
          url:
            "/pages/chapter/chapter?projectId=" +
            this.data.projectId +
            "&seq=" +
            seq +
            "&jobId=" +
            job.id,
        });
      })
      .catch((error) => this.setData({ submitting: false, error: error.message }))
      .finally(() => this.setData({ submitting: false }));
  },
});
