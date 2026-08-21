// pages/login/login.js
const app = getApp();
const api = require("../../utils/api.js");

Page({
  data: {
    role: "parent",  // default
    devOpenid: "demo_parent_001",
    devName: "测试家长",
  },

  onLoad() {
    // If already logged in, go to the right home page
    if (app.globalData.token) {
      this._routeHome(app.globalData.user.role);
    }
  },

  onSelectRole(e) {
    const role = e.currentTarget.dataset.role;
    const presets = {
      parent: { openid: "demo_parent_001", name: "测试家长" },
      teacher: { openid: "demo_teacher_001", name: "测试老师" },
    };
    this.setData({
      role,
      devOpenid: presets[role].openid,
      devName: presets[role].name,
    });
  },

  onInput(e) {
    const k = e.currentTarget.dataset.k;
    this.setData({ [k]: e.detail.value });
  },

  async onLogin() {
    wx.showLoading({ title: "登录中..." });
    try {
      const r = await api.devLogin(this.data.devOpenid, this.data.devName, this.data.role);
      app.saveAuth(r.token, r.user);
      wx.hideLoading();
      this._routeHome(r.user.role);
    } catch (e) {
      wx.hideLoading();
      wx.showToast({ title: "登录失败: " + e.message, icon: "none" });
    }
  },

  async onWxLogin() {
    // Real WeChat login (requires appid configured on server)
    wx.showLoading({ title: "微信登录..." });
    try {
      const codeRes = await new Promise((res, rej) => wx.login({ success: res, fail: rej }));
      const r = await api.wxLogin(codeRes.code, this.data.devName, this.data.role);
      app.saveAuth(r.token, r.user);
      wx.hideLoading();
      this._routeHome(r.user.role);
    } catch (e) {
      wx.hideLoading();
      wx.showToast({ title: "微信登录失败: " + e.message, icon: "none" });
    }
  },

  _routeHome(role) {
    const url = role === "teacher" ? "/pages/teacher-home/teacher-home" : "/pages/parent-home/parent-home";
    wx.redirectTo({ url });
  },
});
