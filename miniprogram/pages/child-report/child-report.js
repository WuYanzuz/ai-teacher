// pages/child-report/child-report.js
const api = require("../../utils/api.js");
const util = require("../../utils/util.js");

Page({
  data: { classId: 0, childName: "", report: null, loading: true },

  onLoad(query) {
    // query.child_name arrives URL-encoded, decode it
    let childName = query.child_name || "";
    try { childName = decodeURIComponent(childName); } catch (e) { /* keep as-is */ }
    this.setData({ classId: Number(query.class_id), childName });
    wx.setNavigationBarTitle({ title: childName + " 成长报告" });
    this.load();
  },

  async load() {
    try {
      const r = await api.childReport(this.data.childName, this.data.classId);
      this.setData({ report: r, loading: false });
    } catch (e) {
      this.setData({ loading: false });
      wx.showToast({ title: e.message, icon: "none" });
    }
  },
});
