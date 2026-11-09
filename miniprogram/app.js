// app.js
App({
  globalData: {
    // API base URL. For local dev, set to your machine's LAN IP + port 8000.
    // The mini program dev tools allow http://localhost:8000 only after
    //   "不校验合法域名" is turned on in the dev tools settings.
    apiBase: "http://192.168.123.243:8000",
    token: "",
    user: null,  // {id, openid, role, name, avatar_url}
    privacyPopupVisible: false,  // a privacy-interface call is waiting on consent
  },

  onLaunch() {
    // Restore login state from local storage
    const token = wx.getStorageSync("token");
    const user = wx.getStorageSync("user");
    if (token && user) {
      this.globalData.token = token;
      this.globalData.user = user;
    }

    // Privacy protection: when a privacy-gated API (wx.chooseMedia, camera...)
    // is invoked and the user has not agreed to the privacy guidelines yet,
    // WeChat pauses the call and fires this event. The privacy-popup component
    // subscribes via onPrivacyNeedAuth; agreeing resumes the paused call.
    this._privacyListeners = [];
    this._privacyResolve = null;
    if (wx.onNeedPrivacyAuthorization) {
      wx.onNeedPrivacyAuthorization((resolve) => {
        this.globalData.privacyPopupVisible = true;
        this._privacyResolve = resolve;
        this._privacyListeners.forEach((fn) => {
          try { fn(true); } catch (e) { /* page gone */ }
        });
      });
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

  // ---- privacy popup wiring ----
  onPrivacyNeedAuth(fn) {
    this._privacyListeners.push(fn);
    if (this.globalData.privacyPopupVisible) fn(true);
  },

  offPrivacyNeedAuth(fn) {
    this._privacyListeners = this._privacyListeners.filter((f) => f !== fn);
  },

  resolvePrivacyAuthorization(agreed) {
    this.globalData.privacyPopupVisible = false;
    const resolve = this._privacyResolve;
    this._privacyResolve = null;
    if (resolve) {
      // buttonId must match the agree button's id in privacy-popup.wxml
      resolve({ event: agreed ? "agree" : "disagree", buttonId: "privacy-agree-btn" });
    }
  },
});
