// pages/child-report/child-report.js
const api = require("../../utils/api.js");
const util = require("../../utils/util.js");

Page({
  data: { classId: 0, childName: "", report: null, loading: true },

  onLoad(query) {
    this.setData({ classId: Number(query.class_id), childName: query.child_name });
    wx.setNavigationBarTitle({ title: query.child_name + " 成长报告" });
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
