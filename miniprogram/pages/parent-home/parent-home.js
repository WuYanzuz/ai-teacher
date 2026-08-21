// pages/parent-home/parent-home.js
const api = require("../../utils/api.js");
const app = getApp();

Page({
  data: { classes: [] },

  onShow() {
    if (!app.globalData.token) { wx.redirectTo({ url: "/pages/login/login" }); return; }
    this.load();
  },

  async load() {
    try { this.setData({ classes: await api.listClasses() }); }
    catch (e) { wx.showToast({ title: e.message, icon: "none" }); }
  },

  onOpenClass(e) {
    const { id, child } = e.currentTarget.dataset;
    wx.navigateTo({ url: `/pages/upload/upload?class_id=${id}&child_name=${encodeURIComponent(child || "")}` });
  },

  onJoinClass() {
    wx.navigateTo({ url: "/pages/join-class/join-class" });
  },

  onChildReport(e) {
    const { classId, childName } = e.currentTarget.dataset;
    wx.navigateTo({ url: `/pages/child-report/child-report?class_id=${classId}&child_name=${encodeURIComponent(childName)}` });
  },

  onLogout() {
    wx.showModal({
      title: "退出登录", content: "确定?",
      success: (r) => { if (r.confirm) app.logout(); },
    });
  },
});
