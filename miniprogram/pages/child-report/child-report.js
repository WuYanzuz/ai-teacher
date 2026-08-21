// pages/child-report/child-report.js
const api = require("../../utils/api.js");
const util = require("../../utils/util.js");

function _decodeChildName(raw) {
  if (!raw) return "";
  try { return decodeURIComponent(raw); } catch (e) { return raw; }
}

Page({
  data: { classId: 0, childName: "", report: null, loading: true },

  onLoad(query) {
    const childName = _decodeChildName(query.child_name);
    this.setData({ classId: Number(query.class_id), childName });
    this._setTitle();
    this.load();
  },

  onShow() {
    // Page instance may be reused — re-apply decoded name on every show
    if (this.data.childName) this._setTitle();
  },

  _setTitle() {
    wx.setNavigationBarTitle({ title: (this.data.childName || "") + " 成长报告" });
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
