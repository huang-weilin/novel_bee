const api = require("../../utils/api");

Page({
  data: {
    projects: [],
    healthText: "正在检查后端…",
    healthOk: false,
    baseUrlInput: "",
    loading: false,
    error: "",
  },

  onShow() {
    this.setData({ baseUrlInput: api.getBaseUrl() });
    this.load();
  },

  onBaseInput(event) {
    this.setData({ baseUrlInput: event.detail.value });
  },

  saveBase() {
    const url = api.setBaseUrl(this.data.baseUrlInput);
    this.setData({ baseUrlInput: url });
    wx.showToast({ title: "已保存", icon: "success" });
    this.load();
  },

  load() {
    this.setData({ loading: true, error: "" });
    Promise.all([api.health(), api.listProjects()])
      .then(([health, projects]) => {
        const llm = health.llm || {};
        this.setData({
          projects: projects.projects || [],
          healthOk: Boolean(llm.configured),
          healthText: llm.configured
            ? "AI 已就绪 · " + (llm.provider || "?") + " · " + (llm.model || "?")
            : "AI 未配置：在电脑端 .env 填 key 并重启后端",
          loading: false,
        });
      })
      .catch((error) => {
        this.setData({
          loading: false,
          error: error.message,
          healthText: "后端未连接",
          healthOk: false,
        });
      });
  },

  goCreate() {
    wx.navigateTo({ url: "/pages/setup/setup" });
  },

  openProject(event) {
    wx.navigateTo({
      url: "/pages/project/project?id=" + event.currentTarget.dataset.id,
    });
  },
});
