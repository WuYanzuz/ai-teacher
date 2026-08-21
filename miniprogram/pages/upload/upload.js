// pages/upload/upload.js
const api = require("../../utils/api.js");

Page({
  data: {
    classId: 0,
    childName: "",
    filePath: "",
    fileKind: "",  // image / video
    uploading: false,
  },

  onLoad(query) {
    // query.child_name arrives URL-encoded from parent-home, decode it
    let childName = query.child_name || "";
    try { childName = decodeURIComponent(childName); } catch (e) { /* keep as-is */ }
    this.setData({
      classId: Number(query.class_id),
      childName,
    });
  },

  onChangeChild(e) { this.setData({ childName: e.detail.value }); },

  onChooseImage() {
    wx.chooseMedia({
      count: 1,
      mediaType: ["image"],
      sourceType: ["album", "camera"],
      maxDuration: 30,
      camera: "back",
      success: (res) => {
        const f = res.tempFiles[0];
        this.setData({ filePath: f.tempFilePath, fileKind: "image" });
      },
    });
  },

  onChooseVideo() {
    wx.chooseMedia({
      count: 1,
      mediaType: ["video"],
      sourceType: ["album", "camera"],
      maxDuration: 120,
      camera: "back",
      success: (res) => {
        const f = res.tempFiles[0];
        // 100MB cap
        if (f.size > 100 * 1024 * 1024) {
          wx.showToast({ title: "视频不能超过 100MB", icon: "none" });
          return;
        }
        this.setData({ filePath: f.tempFilePath, fileKind: "video" });
      },
    });
  },

  onSubmit() {
    if (!this.data.filePath) { wx.showToast({ title: "请先选择文件", icon: "none" }); return; }
    if (!this.data.childName.trim()) { wx.showToast({ title: "请输入孩子名", icon: "none" }); return; }
    this.setData({ uploading: true });
    wx.showLoading({ title: "上传中..." });
    api.uploadHomework(this.data.filePath, this.data.classId, this.data.childName.trim())
      .then((r) => {
        wx.hideLoading();
        wx.showModal({
          title: "上传成功 ✓",
          content: `正在处理, 大约 10-30 秒后老师在「班级」里就能看到点评。`,
          showCancel: false,
          success: () => {
            this.setData({ filePath: "", fileKind: "" });
            wx.navigateBack();
          },
        });
      })
      .catch((e) => {
        wx.hideLoading();
        this.setData({ uploading: false });
        wx.showToast({ title: e.message, icon: "none" });
      });
  },
});
