const { defaultBaseUrl } = require("../config");

function getBaseUrl() {
  const saved = wx.getStorageSync("apiBaseUrl");
  return String(saved || defaultBaseUrl).replace(/\/+$/, "");
}

function setBaseUrl(url) {
  const cleaned = String(url || "").trim().replace(/\/+$/, "");
  if (cleaned) {
    wx.setStorageSync("apiBaseUrl", cleaned);
  } else {
    wx.removeStorageSync("apiBaseUrl");
  }
  return getBaseUrl();
}

function detailText(detail) {
  if (!detail) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const where = Array.isArray(item.loc) ? item.loc.join(".") : "";
        return (where ? where + "：" : "") + (item.msg || JSON.stringify(item));
      })
      .join("；");
  }
  return JSON.stringify(detail);
}

function request(path, options) {
  const opts = options || {};
  return new Promise((resolve, reject) => {
    wx.request({
      url: getBaseUrl() + path,
      method: opts.method || "GET",
      data: opts.data,
      header: { "content-type": "application/json" },
      timeout: opts.timeout || 60000,
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
          return;
        }
        const message =
          detailText(res.data && res.data.detail) ||
          "请求失败（HTTP " + res.statusCode + "）";
        reject(new Error(message));
      },
      fail(err) {
        reject(
          new Error(
            "连不上后端服务：" +
              ((err && err.errMsg) || "请检查地址和网络") +
              "。本地版需要先运行 python -m novel_pipeline.server。"
          )
        );
      },
    });
  });
}

function requestText(path) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: path.indexOf("http") === 0 ? path : getBaseUrl() + path,
      method: "GET",
      responseType: "text",
      dataType: "其他",
      timeout: 60000,
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(typeof res.data === "string" ? res.data : "");
          return;
        }
        reject(new Error("导出失败（HTTP " + res.statusCode + "）"));
      },
      fail(err) {
        reject(new Error((err && err.errMsg) || "导出失败"));
      },
    });
  });
}

function projectPath(projectId, suffix) {
  return "/api/projects/" + projectId + (suffix || "");
}

module.exports = {
  getBaseUrl,
  setBaseUrl,
  request,
  requestText,

  health() {
    return request("/api/health");
  },
  genres() {
    return request("/api/genres");
  },
  listProjects() {
    return request("/api/projects");
  },
  createProject(data) {
    return request("/api/projects", { method: "POST", data });
  },
  getProject(projectId) {
    return request(projectPath(projectId));
  },
  getMemory(projectId) {
    return request(projectPath(projectId, "/memory"));
  },
  listChapters(projectId) {
    return request(projectPath(projectId, "/chapters"));
  },
  getChapter(projectId, seq) {
    return request(projectPath(projectId, "/chapters/" + seq));
  },
  generate(projectId, data) {
    return request(projectPath(projectId, "/chapters/generate"), {
      method: "POST",
      data,
    });
  },
  trial(projectId, data) {
    return request(projectPath(projectId, "/chapters/trial"), {
      method: "POST",
      data,
    });
  },
  getJob(jobId) {
    return request("/api/jobs/" + jobId);
  },
  registerCharacter(projectId, data) {
    return request(projectPath(projectId, "/characters"), {
      method: "POST",
      data,
    });
  },
  registerItem(projectId, data) {
    return request(projectPath(projectId, "/items"), {
      method: "POST",
      data,
    });
  },
  exportUrl(projectId) {
    return getBaseUrl() + projectPath(projectId, "/export");
  },
  exportText(projectId) {
    return requestText(projectPath(projectId, "/export"));
  },
};
