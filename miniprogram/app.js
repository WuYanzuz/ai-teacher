// app.js
App({
  globalData: {
    // API base URL. For local dev, set to your machine's LAN IP + port 8000.
    // The mini program dev tools allow http://localhost:8000 only after
    //   "不校验合法域名" is turned on in the dev tools settings.
    apiBase: "http://127.0.0.1:8000",
    token: "",
    user: null,  // {id, openid, role, name, avatar_url}
  },

  onLaunch() {
    // Restore login state from local storage
    const token = wx.getStorageSync("token");
    const user = wx.getStorageSync("user");
    if (token && user) {
      this.globalData.token = token;
      this.globalData.user = user;
    }
  },

  // Persist login
  saveAuth(token, user) {
    this.globalData.token = token;
    this.globalData.user = user;
    wx.setStorageSync("token", token);
    wx.setStorageSync("user", user);
  },

  logout() {
    this.globalData.token = "";
    this.globalData.user = null;
    wx.removeStorageSync("token");
    wx.removeStorageSync("user");
    wx.reLaunch({ url: "/pages/login/login" });
  },
});
