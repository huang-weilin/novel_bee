App({
  globalData: {
    apiBaseUrl: "",
  },

  onLaunch() {
    const saved = wx.getStorageSync("apiBaseUrl");
    if (saved) {
      this.globalData.apiBaseUrl = saved;
    }
  },
});
