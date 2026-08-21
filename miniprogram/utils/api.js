// utils/api.js
// Wraps wx.request with auth token + base URL.

function getApp_() { return getApp(); }

function request({ url, method = "GET", data, header = {}, auth = true }) {
  const app = getApp_();
  const fullUrl = url.startsWith("http") ? url : app.globalData.apiBase + url;
  const headers = { "Content-Type": "application/json", ...header };
  if (auth && app.globalData.token) {
    headers["Authorization"] = "Bearer " + app.globalData.token;
  }
  return new Promise((resolve, reject) => {
    wx.request({
      url: fullUrl,
      method,
      data,
      header: headers,
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          reject(new Error(res.data?.detail || `HTTP ${res.statusCode}`));
        }
      },
      fail: (err) => reject(err),
    });
  });
}

module.exports = {
  request,

  // auth
  devLogin(openid, name, role) {
    return request({ url: "/api/auth/dev_login", method: "POST", data: { openid, name, role }, auth: false });
  },
  wxLogin(code, name, role) {
    return request({ url: "/api/auth/wx_login", method: "POST", data: { code, name, role }, auth: false });
  },
  me() { return request({ url: "/api/auth/me" }); },

  // classes
  createClass(name) { return request({ url: "/api/classes", method: "POST", data: { name } }); },
  listClasses() { return request({ url: "/api/classes" }); },
  joinClass(code, childName) { return request({ url: "/api/classes/join", method: "POST", data: { code, child_name: childName } }); },
  getClass(classId) { return request({ url: `/api/classes/${classId}` }); },

  // homework
  uploadHomework(filePath, classId, childName) {
    return new Promise((resolve, reject) => {
      const app = getApp_();
      wx.uploadFile({
        url: app.globalData.apiBase + "/api/homework/upload",
        filePath,
        name: "file",
        formData: { class_id: String(classId), child_name: childName },
        header: { Authorization: "Bearer " + app.globalData.token },
        success: (res) => {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            try { resolve(JSON.parse(res.data)); } catch (e) { reject(e); }
          } else {
            try {
              const d = JSON.parse(res.data);
              reject(new Error(d.detail || `HTTP ${res.statusCode}`));
            } catch (e) { reject(new Error(`HTTP ${res.statusCode}`)); }
          }
        },
        fail: reject,
      });
    });
  },
  listHomework(classId) { return request({ url: `/api/homework?class_id=${classId}` }); },
  getHomework(id) { return request({ url: `/api/homework/${id}` }); },
  ackHomework(id) { return request({ url: `/api/homework/${id}/ack`, method: "POST" }); },
  ignoreHomework(id) { return request({ url: `/api/homework/${id}/ignore`, method: "POST" }); },
  renameChild(id, childName) { return request({ url: `/api/homework/${id}/rename`, method: "POST", data: { child_name: childName } }); },
  editFeedback(id, feedback) { return request({ url: `/api/homework/${id}/feedback`, method: "POST", data: { feedback } }); },
  resetFeedback(id) { return request({ url: `/api/homework/${id}/reset_feedback`, method: "POST" }); },

  // children
  childReport(name, classId) { return request({ url: `/api/children/${encodeURIComponent(name)}/report?class_id=${classId}` }); },
};
