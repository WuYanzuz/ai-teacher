// pages/class-detail/class-detail.js
const api = require("../../utils/api.js");
const util = require("../../utils/util.js");

Page({
  data: {
    classId: 0,
    className: "",
    homework: [],
    loading: true,
    childFilter: "",  // optional: filter by child name
  },

  onLoad(query) {
    this.setData({ classId: Number(query.class_id) });
    this.loadClass();
    this.loadHomework();
  },

  onShow() {
    this.loadHomework();
  },

  onPullDownRefresh() {
    this.loadHomework().then(() => wx.stopPullDownRefresh());
  },

  async loadClass() {
    try {
      const r = await api.getClass(this.data.classId);
      this.setData({ className: r.name });
      wx.setNavigationBarTitle({ title: r.name });
    } catch (e) {
      wx.showToast({ title: e.message, icon: "none" });
    }
  },

  async loadHomework() {
    try {
      const r = await api.listHomework(this.data.classId);
      const filtered = this.data.childFilter
        ? r.filter((h) => h.child_name === this.data.childFilter)
        : r;
      this.setData({ homework: filtered, loading: false });
    } catch (e) {
      this.setData({ loading: false });
      wx.showToast({ title: e.message, icon: "none" });
    }
  },

  onFilterInput(e) {
    this.setData({ childFilter: e.detail.value });
    this.loadHomework();
  },

  onClearFilter() {
    this.setData({ childFilter: "" });
    this.loadHomework();
  },

  onOpen(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/homework-detail/homework-detail?id=${id}` });
  },
});
