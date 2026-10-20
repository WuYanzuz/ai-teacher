// pages/checkin-edit/checkin-edit.js
const api = require("../../utils/api.js");

function decodeName(raw) {
  if (!raw) return "";
  try { return decodeURIComponent(raw); } catch (e) { return raw; }
}

Page({
  data: {
    classId: 0,
    date: "",
    childName: "",
    categories: [],   // [{code,label,multi_select,options, picked:[], note:''}]
    note: "",
    saving: false,
  },

  onLoad(query) {
    const childName = decodeName(query.child_name);
    this.setData({
      classId: Number(query.class_id),
      date: query.date,
      childName,
    });
    wx.setNavigationBarTitle({ title: childName + " · " + query.date });
    this.init();
  },

  async init() {
    wx.showLoading({ title: "加载中..." });
    try {
      const [tpl, saved] = await Promise.all([
        api.checkinTemplate(),
        api.getCheckin(this.data.classId, this.data.date, this.data.childName),
      ]);
      const prior = {};
      (saved.items || []).forEach((it) => { prior[it.category_code] = it; });
      const categories = tpl.categories.map((c) => ({
        code: c.code,
        label: c.label,
        multi_select: c.multi_select,
        options: c.options,
        picked: (prior[c.code] && prior[c.code].options) || [],
        note: (prior[c.code] && prior[c.code].note) || "",
      }));
      this.setData({ categories, note: saved.note || "" });
    } catch (e) {
      wx.showToast({ title: e.message, icon: "none" });
    } finally {
      wx.hideLoading();
    }
  },

  onToggleOption(e) {
    const { ci, oi } = e.currentTarget.dataset;
    const cat = this.data.categories[ci];
    const label = cat.options[oi];
    let picked;
    if (cat.picked.indexOf(label) >= 0) {
      picked = cat.picked.filter((x) => x !== label);
    } else if (cat.multi_select) {
      picked = cat.picked.concat(label);
    } else {
      picked = [label];
    }
    this.setData({ [`categories[${ci}].picked`]: picked });
  },

  onCatNote(e) {
    const { ci } = e.currentTarget.dataset;
    this.setData({ [`categories[${ci}].note`]: e.detail.value });
  },

  onNote(e) {
    this.setData({ note: e.detail.value });
  },

  async onSave() {
    if (this.data.saving) return;
    this.setData({ saving: true });
    wx.showLoading({ title: "保存中..." });
    const items = this.data.categories
      .filter((c) => c.picked.length || (c.note && c.note.trim()))
      .map((c) => ({ category_code: c.code, options: c.picked, note: c.note }));
    try {
      await api.putCheckin({
        class_id: this.data.classId,
        child_name: this.data.childName,
        date: this.data.date,
        note: this.data.note,
        items,
      });
      wx.showToast({ title: "已保存 ✓" });
      setTimeout(() => wx.navigateBack(), 600);
    } catch (e) {
      wx.hideLoading();
      wx.showToast({ title: e.message, icon: "none" });
    } finally {
      this.setData({ saving: false });
    }
  },
});
