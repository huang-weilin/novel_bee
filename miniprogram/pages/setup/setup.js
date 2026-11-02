const api = require("../../utils/api");

Page({
  data: {
    genres: [],
    genreLabels: [],
    genreIndex: 0,
    title: "",
    target: "",
    loading: false,
    error: "",
  },

  onLoad() {
    api
      .genres()
      .then((payload) => {
        const genres = payload.genres || [];
        const list = genres.length
          ? genres
          : [{ key: "default", label: "通用" }];
        this.setData({
          genres: list,
          genreLabels: list.map((item) => item.label + "（" + item.key + "）"),
        });
      })
      .catch((error) => this.setData({ error: error.message }));
  },

  onTitleInput(event) {
    this.setData({ title: event.detail.value });
  },

  onTargetInput(event) {
    this.setData({ target: event.detail.value });
  },

  onGenreChange(event) {
    this.setData({ genreIndex: Number(event.detail.value) });
  },

  submit() {
    const title = this.data.title.trim();
    if (!title) {
      wx.showToast({ title: "先给作品起个名字", icon: "none" });
      return;
    }
    const genre =
      (this.data.genres[this.data.genreIndex] || {}).key || "default";
    const rawTarget = this.data.target.trim();
    const target = rawTarget ? Number(rawTarget) : null;
    if (rawTarget && (!Number.isFinite(target) || target < 1)) {
      wx.showToast({ title: "计划章数要大于 0", icon: "none" });
      return;
    }
    this.setData({ loading: true, error: "" });
    api
      .createProject({
        title,
        genre,
        target_chapters: target,
      })
      .then((project) => {
        wx.redirectTo({
          url: "/pages/project/project?id=" + project.id,
        });
      })
      .catch((error) => {
        this.setData({ loading: false, error: error.message });
      });
  },
});
