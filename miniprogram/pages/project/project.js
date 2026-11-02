const api = require("../../utils/api");
const format = require("../../utils/format");

Page({
  data: {
    projectId: "",
    project: null,
    memory: null,
    chapters: [],
    nextSeq: 1,
    loading: false,
    error: "",
  },

  onLoad(options) {
    this.setData({ projectId: options.id || "" });
  },

  onShow() {
    if (this.data.projectId) {
      this.load();
    }
  },

  load() {
    const projectId = this.data.projectId;
    this.setData({ loading: true, error: "" });
    Promise.all([api.getProject(projectId), api.getMemory(projectId)])
      .then(([project, memory]) => {
        const chapters = (project.chapters || []).map((item) => ({
          ...item,
          statusLabel: format.statusLabel(item.status),
          statusClass: format.statusClass(item.status),
          scoreText: format.scoreText(item.score),
        }));
        this.setData({
          project,
          memory,
          chapters,
          nextSeq: project.next_chapter_seq || 1,
          loading: false,
        });
        wx.setNavigationBarTitle({ title: project.title || "作品" });
      })
      .catch((error) => this.setData({ loading: false, error: error.message }));
  },

  goOutline() {
    wx.navigateTo({
      url:
        "/pages/outline/outline?projectId=" +
        this.data.projectId +
        "&seq=" +
        this.data.nextSeq,
    });
  },

  openChapter(event) {
    wx.navigateTo({
      url:
        "/pages/chapter/chapter?projectId=" +
        this.data.projectId +
        "&seq=" +
        event.currentTarget.dataset.seq,
    });
  },

  copyExport() {
    const projectId = this.data.projectId;
    const copyUrl = () => {
      wx.setClipboardData({
        data: api.exportUrl(projectId),
        success() {
          wx.showToast({ title: "导出链接已复制", icon: "none" });
        },
      });
    };
    api
      .exportText(projectId)
      .then((text) => {
        if (!text) throw new Error("空文件");
        wx.setClipboardData({
          data: text,
          success() {
            wx.showToast({ title: "全文已复制", icon: "success" });
          },
          fail: copyUrl,
        });
      })
      .catch(copyUrl);
  },
});
