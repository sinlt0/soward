(function () {
  var OP = { HANDSHAKE: 0, FRAME: 1, CLOSE: 2, HELLO: 3 };
  var ORIGINS = ["https://discord.com", "https://discordapp.com", "https://ptb.discord.com", "https://ptb.discordapp.com", "https://canary.discord.com", "https://canary.discordapp.com", "https://staging.discord.co", "http://localhost:3333", "https://pax.discord.com", "null", window.location.origin];

  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0;
      return (c === "x" ? r : (r & 3) | 8).toString(16);
    });
  }

  function MiniDiscord(clientId) {
    var params = new URLSearchParams(window.location.search);
    this.clientId = clientId;
    this.frameId = params.get("frame_id");
    this.instanceId = params.get("instance_id");
    this.platform = params.get("platform");
    this.guildId = params.get("guild_id");
    this.channelId = params.get("channel_id");
    this.embedded = !!(this.frameId && this.instanceId && this.platform);
    this.pending = {};
    this.listeners = {};
    this.isReady = false;
    if (!this.embedded) return;
    this.source = window.parent.opener || window.parent;
    this.origin = document.referrer ? document.referrer : "*";
    var self = this;
    window.addEventListener("message", function (event) { self.onMessage(event); });
    this.post(OP.HANDSHAKE, { v: 1, encoding: "json", client_id: clientId, frame_id: this.frameId, sdk_version: "2.5.0" });
  }

  MiniDiscord.prototype.post = function (op, payload) {
    this.source.postMessage([op, payload], this.origin);
  };

  MiniDiscord.prototype.on = function (evt, fn) {
    (this.listeners[evt] = this.listeners[evt] || []).push(fn);
  };

  MiniDiscord.prototype.emit = function (evt, data) {
    (this.listeners[evt] || []).slice().forEach(function (fn) { fn(data); });
  };

  MiniDiscord.prototype.onMessage = function (event) {
    if (ORIGINS.indexOf(event.origin) === -1) return;
    var tuple = event.data;
    if (!Array.isArray(tuple)) return;
    var op = tuple[0], data = tuple[1];
    if (op !== OP.FRAME || !data) return;
    if (data.cmd === "DISPATCH") {
      if (data.evt === "READY") this.isReady = true;
      this.emit(data.evt, data.data);
      return;
    }
    var waiting = data.nonce ? this.pending[data.nonce] : null;
    if (!waiting) return;
    delete this.pending[data.nonce];
    if (data.evt === "ERROR") waiting.reject(data.data || new Error("Discord error"));
    else waiting.resolve(data.data);
  };

  MiniDiscord.prototype.ready = function () {
    var self = this;
    if (self.isReady) return Promise.resolve();
    return new Promise(function (resolve) { self.on("READY", resolve); });
  };

  MiniDiscord.prototype.command = function (cmd, args) {
    var self = this;
    var nonce = uuid();
    return new Promise(function (resolve, reject) {
      self.pending[nonce] = { resolve: resolve, reject: reject };
      self.post(OP.FRAME, { cmd: cmd, args: args || {}, nonce: nonce });
    });
  };

  MiniDiscord.prototype.authorize = function (scopes) {
    return this.command("AUTHORIZE", { client_id: this.clientId, response_type: "code", state: "", prompt: "none", scope: scopes });
  };

  MiniDiscord.prototype.authenticate = function (token) {
    return this.command("AUTHENTICATE", { access_token: token });
  };

  MiniDiscord.prototype.setActivity = function (activity) {
    return this.command("SET_ACTIVITY", { activity: activity });
  };

  window.MiniDiscord = MiniDiscord;
})();
