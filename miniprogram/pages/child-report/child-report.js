// pages/child-report/child-report.js
const api = require("../../utils/api.js");

function _decodeChildName(raw) {
  if (!raw) return "";
  try { return decodeURIComponent(raw); } catch (e) { return raw; }
}

function fmt(d) {
  const p = (n) => (n < 10 ? "0" + n : "" + n);
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

Page({
  data: {
    classId: 0,
    childName: "",
    reports: [],
    checkins: [],
    labels: {},
    report: null,
    loading: true,
  },

  onLoad(query) {
    const childName = _decodeChildName(query.child_name);
    this.setData({ classId: Number(query.class_id), childName });
    this._setTitle();
    this.load();
  },

  onShow() {
    if (this.data.childName) this._setTitle();
    // Reports may have been (un)published while this page was in background.
    if (this.data.classId) this._loadReports();
  },

  _setTitle() {
    wx.setNavigationBarTitle({ title: (this.data.childName || "") + " 成长档案" });
  },

  async load() {
    const { classId, childName } = this.data;
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - 30);
    const startStr = fmt(start);
    const endStr = fmt(end);
    try {
      const [tpl, reportList, checkinRes, hwReport] = await Promise.all([
        api.checkinTemplate().catch(() => ({ categories: [] })),
        api.listReportsForChild(classId, childName).catch(() => ({ reports: [] })),
        api.childCheckins(classId, childName, startStr, endStr).catch(() => ({ days: [] })),
        api.childReport(childName, classId).catch(() => null),
      ]);
      const labels = {};
      (tpl.categories || []).forEach((c) => { labels[c.code] = c.label; });
      const reports = (reportList.reports || []).map((r) => ({
        ...r,
        type_text: r.report_type === "day" ? "日报" : "周报",
      }));
      const checkins = (checkinRes.days || []).slice().reverse().map((d) => ({
        ...d,
        items: d.items.map((it) => ({
          ...it,
          label: labels[it.category_code] || it.category_code,
          optionsText: (it.options || []).join("、"),
        })),
      }));
      this.setData({ labels, reports, checkins, report: hwReport, loading: false });
    } catch (e) {
      this.setData({ loading: false });
      wx.showToast({ title: e.message, icon: "none" });
    }
  },

  async _loadReports() {
    try {
      const reportList = await api.listReportsForChild(this.data.classId, this.data.childName);
      const reports = (reportList.reports || []).map((r) => ({
        ...r,
        type_text: r.report_type === "day" ? "日报" : "周报",
      }));
      this.setData({ reports });
    } catch (e) { /* leave existing */ }
  },

  onOpenReport(e) {
    wx.navigateTo({ url: `/pages/report-detail/report-detail?id=${e.currentTarget.dataset.id}` });
  },
});
