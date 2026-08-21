// pages/video-play/video-play.js
Page({
  data: { url: "" },
  onLoad(query) {
    let url = query.url || "";
    try { url = decodeURIComponent(url); } catch (e) { /* keep */ }
    this.setData({ url });
    wx.setNavigationBarTitle({ title: "播放作业视频" });
  },
});
