// pages/teacher-home/teacher-home.js
const api = require("../../utils/api.js");
const app = getApp();

Page({
  data: {
    classes: [],
    newName: "",
  },

  onShow() {
    if (!app.globalData.token) {
      wx.redirectTo({ url: "/pages/login/login" });
      return;
    }
    this.load();
  },

  async load() {
    try {
      const r = await api.listClasses();
      this.setData({ classes: r });
    } catch (e) {
      wx.showToast({ title: e.message, icon: "none" });
    }
  },

  onInputName(e) { this.setData({ newName: e.detail.value }); },

  async onCreate() {
    const name = (this.data.newName || "").trim();
    if (!name) {
      wx.showToast({ title: "请输入班级名", icon: "none" });
      return;
    }
    try {
      const r = await api.createClass(name);
      wx.showToast({ title: `已创建, 加入码: ${r.code}`, icon: "none", duration: 3000 });
      this.setData({ newName: "" });
      this.load();
    } catch (e) {
      wx.showToast({ title: e.message, icon: "none" });
    }
  },

  onOpenClass(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/class-detail/class-detail?class_id=${id}` });
  },

  onLogout() {
    wx.showModal({
      title: "退出登录",
      content: "确定要退出吗?",
      success: (r) => { if (r.confirm) app.logout(); },
    });
  },

  onCopyCode(e) {
    wx.setClipboardData({ data: e.currentTarget.dataset.code });
  },
});
