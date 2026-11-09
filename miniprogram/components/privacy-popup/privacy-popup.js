// components/privacy-popup/privacy-popup.js
// Custom WeChat privacy authorization popup.
//
// App.onLaunch registers wx.onNeedPrivacyAuthorization; when a privacy-gated
// API (wx.chooseMedia / camera) is called without consent, WeChat pauses the
// call and the app notifies this component. Tapping the agree button
// (open-type="agreePrivacyAuthorization") records consent and resumes the
// paused call; rejecting lets it fail as if the user had cancelled.
Component({
  data: {
    visible: false,
  },

  lifetimes: {
    attached() {
      const app = getApp();
      this._show = () => this.setData({ visible: true });
      app.onPrivacyNeedAuth(this._show);
    },
    detached() {
      getApp().offPrivacyNeedAuth(this._show);
    },
  },

  methods: {
    // Fired by the open-type=agreePrivacyAuthorization button after consent.
    onAgree() {
      this.setData({ visible: false });
      getApp().resolvePrivacyAuthorization(true);
    },

    onDisagree() {
      this.setData({ visible: false });
      getApp().resolvePrivacyAuthorization(false);
    },

    // In-app full privacy policy page.
    openPolicy() {
      wx.navigateTo({ url: "/pages/privacy/privacy" });
    },

    // The privacy contract configured in the mp admin console.
    openContract() {
      if (wx.openPrivacyContract) {
        wx.openPrivacyContract({ fail: () => {} });
      }
    },
  },
});
