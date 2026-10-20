// pages/checkin/checkin.js
const api = require("../../utils/api.js");

function todayStr() {
  const d = new Date();
  const p = (n) => (n < 10 ? "0" + n : "" + n);
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

Page({
  data: {
    classId: 0,
    date: "",
    children: [],
    loading: true,
    doneCount: 0,
  },

  onLoad(query) {
    this.setData({ classId: Number(query.class_id), date: todayStr() });
  },

  onShow() {
    if (this.data.classId) this.load();
  },

  onPullDownRefresh() {
    this.load().then(() => wx.stopPullDownRefresh());
  },

  onDateChange(e) {
    this.setData({ date: e.detail.value });
    this.load();
  },

  async load() {
    this.setData({ loading: true });
    try {
      const r = await api.checkinDay(this.data.classId, this.data.date);
      const doneCount = r.children.filter((c) => c.done).length;
      this.setData({ children: r.children, doneCount, loading: false });
    } catch (e) {
      this.setData({ loading: false });
      wx.showToast({ title: e.message, icon: "none" });
    }
  },

  onOpenChild(e) {
    const name = e.currentTarget.dataset.name;
    const url = `/pages/checkin-edit/checkin-edit?class_id=${this.data.classId}`
      + `&date=${this.data.date}&child_name=${encodeURIComponent(name)}`;
    wx.navigateTo({ url });
  },
});
