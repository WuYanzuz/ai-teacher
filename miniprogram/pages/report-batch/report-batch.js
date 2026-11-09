// pages/report-batch/report-batch.js
const api = require("../../utils/api.js");

function todayStr() {
  const d = new Date();
  const p = (n) => (n < 10 ? "0" + n : "" + n);
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

// Monday..Sunday for an anchor date; returns {start, end} 'YYYY-MM-DD'
function weekRange(anchor) {
  const d = new Date(anchor + "T00:00:00");
  const p = (x) => {
    const q = (n) => (n < 10 ? "0" + n : "" + n);
    return `${x.getFullYear()}-${q(x.getMonth() + 1)}-${q(x.getDate())}`;
  };
  const dow = (d.getDay() + 6) % 7; // Monday=0 ... Sunday=6
  const mon = new Date(d);
  mon.setDate(d.getDate() - dow);
  const sun = new Date(mon);
  sun.setDate(mon.getDate() + 6);
  return { start: p(mon), end: p(sun) };
}

const TERMINAL = ["done", "partial", "failed"];
const POLL_MS = 3000;
const MAX_TICKS = 200; // 10 min cap

Page({
  data: {
    classId: 0,
    type: "day",
    date: "",
    weekText: "",
    batch: null,
    starting: false,
    ticks: 0,
  },

  onLoad(query) {
    const date = todayStr();
    this.setData({ classId: Number(query.class_id), date });
    this._updateWeek();
    this._timer = null;
  },

  onShow() {
    if (this.data.batch && TERMINAL.indexOf(this.data.batch.status) < 0) {
      this._startPolling();
    }
  },

  onHide() {
    this._stopPolling();
  },

  onUnload() {
    this._stopPolling();
  },

  _updateWeek() {
    const w = weekRange(this.data.date);
    this.setData({ weekText: `${w.start} ~ ${w.end}` });
  },

  onTypeChange(e) {
    const type = e.currentTarget.dataset.type;
    if (type === this.data.type) return;
    this._stopPolling();
    this.setData({ type, batch: null, ticks: 0 });
    this._updateWeek();
  },

  onDateChange(e) {
    this._stopPolling();
    this.setData({ date: e.detail.value, batch: null, ticks: 0 });
    this._updateWeek();
  },

  async onGenerate() {
    if (this.data.starting) return;
    this.setData({ starting: true });
    wx.showLoading({ title: "处理中..." });
    try {
      const b = await api.createReportBatch({
        class_id: this.data.classId,
        type: this.data.type,
        date: this.data.date,
      });
      this.setData({ batch: b, ticks: 0 });
      if (TERMINAL.indexOf(b.status) < 0) this._startPolling();
    } catch (e) {
      wx.showToast({ title: e.message, icon: "none" });
    } finally {
      wx.hideLoading();
      this.setData({ starting: false });
    }
  },

  async onRegenerate() {
    const r = await new Promise((resolve) => {
      wx.showModal({
        title: "重新生成",
        content: "将清除本周期现有报告并重新生成，确定吗？",
        success: (x) => resolve(x.confirm),
      });
    });
    if (!r) return;
    wx.showLoading({ title: "处理中..." });
    try {
      const b = await api.createReportBatch({
        class_id: this.data.classId,
        type: this.data.type,
        date: this.data.date,
        regenerate: true,
      });
      this.setData({ batch: b, ticks: 0 });
      this._startPolling();
    } catch (e) {
      wx.showToast({ title: e.message, icon: "none" });
    } finally {
      wx.hideLoading();
    }
  },

  _startPolling() {
    this._stopPolling();
    this._timer = setInterval(() => this._pollOnce(), POLL_MS);
    this._pollOnce();
  },

  _stopPolling() {
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
  },

  async _pollOnce() {
    if (!this.data.batch) return;
    const ticks = this.data.ticks + 1;
    if (ticks > MAX_TICKS) {
      this._stopPolling();
      wx.showToast({ title: "生成时间较长，可稍后回来查看", icon: "none" });
      return;
    }
    try {
      const b = await api.getReportBatch(this.data.batch.id);
      this.setData({ batch: b, ticks });
      if (TERMINAL.indexOf(b.status) >= 0) this._stopPolling();
    } catch (e) {
      this._stopPolling();
    }
  },

  onOpenReport(e) {
    const id = e.currentTarget.dataset.id;
    const status = e.currentTarget.dataset.status;
    if (status !== "done") return;
    wx.navigateTo({ url: `/pages/report-detail/report-detail?id=${id}` });
  },

  async onRetry(e) {
    const id = e.currentTarget.dataset.id;
    try {
      await api.retryReport(id);
      wx.showToast({ title: "已重新加入生成" });
      this._startPolling();
    } catch (err) {
      wx.showToast({ title: err.message, icon: "none" });
    }
  },

  async onPublishAll() {
    try {
      const r = await api.publishAllReports(this.data.batch.id);
      if (r.blocked && r.blocked.length) {
        wx.showModal({
          title: "部分报告未发布",
          content: `已发布 ${r.published} 份；${r.blocked.join("、")} 的报告可能含违规内容，已被拦截，请修改后再发布。`,
          showCancel: false,
        });
      } else {
        wx.showToast({ title: `已发布 ${r.published} 份` });
      }
      this._pollOnce();
    } catch (e) {
      wx.showToast({ title: e.message, icon: "none" });
    }
  },
});
