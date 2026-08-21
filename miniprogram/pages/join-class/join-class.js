// pages/join-class/join-class.js
const api = require("../../utils/api.js");

Page({
  data: { code: "", childName: "" },

  onCodeInput(e) { this.setData({ code: e.detail.value }); },
  onNameInput(e) { this.setData({ childName: e.detail.value }); },

  async onJoin() {
    const code = (this.data.code || "").trim();
    const name = (this.data.childName || "").trim();
    if (!code || code.length !== 6) { wx.showToast({ title: "请输入 6 位加入码", icon: "none" }); return; }
    if (!name) { wx.showToast({ title: "请输入孩子名", icon: "none" }); return; }
    wx.showLoading({ title: "加入中..." });
    try {
      const r = await api.joinClass(code, name);
      wx.hideLoading();
      wx.showToast({ title: `已加入 ${r.name}`, icon: "success" });
      setTimeout(() => wx.navigateBack(), 800);
    } catch (e) {
      wx.hideLoading();
      wx.showToast({ title: e.message, icon: "none" });
    }
  },
});
