// pages/homework-detail/homework-detail.js
const api = require("../../utils/api.js");
const app = getApp();

Page({
  data: {
    id: 0,
    hw: null,
    renameValue: "",
    showRename: false,
  },

  onLoad(query) {
    this.setData({ id: Number(query.id) });
    this.load();
  },

  onShow() { this.load(); },

  async load() {
    try {
      const r = await api.getHomework(this.data.id);
      this.setData({ hw: r, renameValue: r.child_name });
    } catch (e) {
      wx.showToast({ title: e.message, icon: "none" });
    }
  },

  onAck() {
    wx.showLoading({ title: "处理中..." });
    api.ackHomework(this.data.id).then(() => {
      wx.hideLoading();
      wx.showToast({ title: "已确认 ✓" });
      this.load();
    }).catch((e) => {
      wx.hideLoading();
      wx.showToast({ title: e.message, icon: "none" });
    });
  },

  onIgnore() {
    wx.showModal({
      title: "忽略这条?",
      content: "标记为非作业, 不计入统计",
      success: (r) => {
        if (!r.confirm) return;
        api.ignoreHomework(this.data.id).then(() => {
          wx.showToast({ title: "已忽略" });
          this.load();
        });
      },
    });
  },

  onShowRename() { this.setData({ showRename: true }); },
  onCancelRename() { this.setData({ showRename: false }); },

  onRenameInput(e) { this.setData({ renameValue: e.detail.value }); },

  onConfirmRename() {
    const name = (this.data.renameValue || "").trim();
    if (!name) return;
    api.renameChild(this.data.id, name).then(() => {
      this.setData({ showRename: false });
      wx.showToast({ title: "已改名" });
      this.load();
    }).catch((e) => wx.showToast({ title: e.message, icon: "none" }));
  },

  onPreviewMedia() {
    if (!this.data.hw || !this.data.hw.media_url) return;
    const fullUrl = (getApp().globalData.apiBase || "") + this.data.hw.media_url;
    if (this.data.hw.media_type === "image") {
      wx.previewImage({ urls: [fullUrl] });
    } else if (this.data.hw.media_type === "video") {
      // navigate to inline video page or just show toast
      wx.navigateTo({ url: `/pages/homework-detail/video?url=${encodeURIComponent(fullUrl)}` });
    }
  },
});
