// pages/homework-detail/homework-detail.js
const api = require("../../utils/api.js");
const app = getApp();

Page({
  data: {
    id: 0,
    hw: null,
    renameValue: "",
    showRename: false,
    showEdit: false,
    editValue: "",
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

  onShowEdit() {
    this.setData({ showEdit: true, editValue: (this.data.hw && this.data.hw.polished_feedback) || "" });
  },
  onCancelEdit() { this.setData({ showEdit: false }); },
  onEditInput(e) { this.setData({ editValue: e.detail.value }); },
  onConfirmEdit() {
    const text = (this.data.editValue || "").trim();
    if (!text) { wx.showToast({ title: "内容不能为空", icon: "none" }); return; }
    wx.showLoading({ title: "保存中..." });
    api.editFeedback(this.data.id, text).then(() => {
      wx.hideLoading();
      this.setData({ showEdit: false });
      wx.showToast({ title: "已保存 ✓" });
      this.load();
    }).catch((e) => {
      wx.hideLoading();
      wx.showToast({ title: e.message, icon: "none" });
    });
  },

  onResetEdit() {
    wx.showModal({
      title: "恢复自动点评?",
      content: "会清掉'已编辑'标记, 但不会改回原文。",
      success: (r) => {
        if (!r.confirm) return;
        api.resetFeedback(this.data.id).then(() => {
          wx.showToast({ title: "已重置" });
          this.load();
        });
      },
    });
  },

  onPreviewMedia() {
    // Image: tap to view fullscreen
    if (!this.data.hw || !this.data.hw.media_url) return;
    if (this.data.hw.media_type === "image") {
      const fullUrl = (getApp().globalData.apiBase || "") + this.data.hw.media_url;
      wx.previewImage({ urls: [fullUrl] });
    }
  },

  onPlayVideo() {
    if (!this.data.hw || !this.data.hw.media_url) return;
    const fullUrl = (getApp().globalData.apiBase || "") + this.data.hw.media_url;
    wx.navigateTo({
      url: `/pages/video-play/video-play?url=${encodeURIComponent(fullUrl)}`,
    });
  },
});
