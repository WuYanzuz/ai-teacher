// pages/report-detail/report-detail.js
const api = require("../../utils/api.js");

Page({
  data: {
    id: 0,
    report: null,
    loading: true,
    isTeacher: false,
    showEdit: false,
    editValue: "",
    busy: false,
  },

  onLoad(query) {
    const app = getApp();
    this.setData({
      id: Number(query.id),
      isTeacher: (app.globalData.user || {}).role === "teacher",
    });
    this.load();
  },

  async load() {
    try {
      const r = await api.getReport(this.data.id);
      wx.setNavigationBarTitle({ title: `${r.child_name} · ${r.report_type === "day" ? "日报" : "周报"}` });
      this.setData({ report: r, loading: false });
    } catch (e) {
      this.setData({ loading: false });
      wx.showToast({ title: e.message, icon: "none" });
    }
  },

  onShowEdit() {
    this.setData({
      showEdit: true,
      editValue: this.data.report.teacher_edit || this.data.report.content || "",
    });
  },

  onCancelEdit() {
    this.setData({ showEdit: false });
  },

  onEditInput(e) {
    this.setData({ editValue: e.detail.value });
  },

  async onSaveEdit() {
    const text = (this.data.editValue || "").trim();
    if (!text) {
      wx.showToast({ title: "内容不能为空", icon: "none" });
      return;
    }
    if (this.data.busy) return;
    this.setData({ busy: true });
    wx.showLoading({ title: "保存中..." });
    try {
      const r = await api.editReport(this.data.id, text);
      this.setData({ report: r, showEdit: false });
      wx.showToast({ title: "已保存 ✓" });
    } catch (e) {
      wx.showToast({ title: e.message, icon: "none" });
    } finally {
      wx.hideLoading();
      this.setData({ busy: false });
    }
  },

  async onPublish() {
    wx.showLoading({ title: "发布中..." });
    try {
      const r = await api.publishReport(this.data.id);
      this.setData({ report: r });
      wx.showToast({ title: "已发布 ✓" });
    } catch (e) {
      wx.showToast({ title: e.message, icon: "none" });
    } finally {
      wx.hideLoading();
    }
  },

  async onUnpublish() {
    const ok = await new Promise((resolve) => {
      wx.showModal({
        title: "撤回发布",
        content: "撤回后家长端将看不到这份报告，确定吗？",
        success: (x) => resolve(x.confirm),
      });
    });
    if (!ok) return;
    wx.showLoading({ title: "处理中..." });
    try {
      const r = await api.unpublishReport(this.data.id);
      this.setData({ report: r });
      wx.showToast({ title: "已撤回" });
    } catch (e) {
      wx.showToast({ title: e.message, icon: "none" });
    } finally {
      wx.hideLoading();
    }
  },
});
