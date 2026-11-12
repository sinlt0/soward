(function () {
  "use strict";
  var $app = document.getElementById("app");
  var audio = document.getElementById("audio");
  var clientId = document.body.dataset.clientId;
  var enabled = document.body.dataset.enabled === "1";
  var build = document.body.dataset.build || "";
  var musicOn = document.body.dataset.music === "1";
  var gameIds = (document.body.dataset.games || "").split(",").filter(Boolean);
  var apps = [];
  if (musicOn) apps.push("music");
  if (gameIds.length) apps.push("games");

  var ICON = {
    home: "M3 11l9-8 9 8v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z",
    library: "M4 4v16M9 4v16M14 6l5 14",
    history: "M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 2",
    gear: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19 12a7 7 0 0 0-.1-1.2l2-1.5-2-3.4-2.3 1a7 7 0 0 0-2-1.2L14 3h-4l-.6 2.7a7 7 0 0 0-2 1.2l-2.3-1-2 3.4 2 1.5A7 7 0 0 0 5 12c0 .4 0 .8.1 1.2l-2 1.5 2 3.4 2.3-1a7 7 0 0 0 2 1.2L10 21h4l.6-2.7a7 7 0 0 0 2-1.2l2.3 1 2-3.4-2-1.5c.1-.4.1-.8.1-1.2z",
    search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.3-4.3",
    play: "M7 4l13 8-13 8z",
    pause: "M6 4h4v16H6zM14 4h4v16h-4z",
    prev: "M19 5v14M17 12L6 5v14z",
    next: "M5 5v14M7 12l11-7v14z",
    shuffle: "M16 3h5v5M4 20L21 3M21 16v5h-5M15 15l6 6M4 4l5 5",
    repeat: "M17 2l4 4-4 4M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4M21 13v2a3 3 0 0 1-3 3H3",
    heart: "M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l1 1.1L12 21l7.8-7.5 1-1.1a5.5 5.5 0 0 0 0-7.8z",
    queue: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
    plus: "M12 5v14M5 12h14",
    more: "M12 5h.01M12 12h.01M12 19h.01",
    volume: "M11 5L6 9H2v6h4l5 4zM15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13",
    mute: "M11 5L6 9H2v6h4l5 4zM22 9l-6 6M16 9l6 6",
    trash: "M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14",
    close: "M6 6l12 12M18 6L6 18",
    apps: "M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z",
    music: "M9 18V5l12-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM21 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z",
    games: "M6 12h4M8 10v4M15 13h.01M18 11h.01M17.3 5H6.7a4 4 0 0 0-3.9 3.1l-1.5 6.5A2.5 2.5 0 0 0 3.7 17.5c.9 0 1.6-.4 2.1-1.1L7 15h10l1.2 1.4c.5.7 1.2 1.1 2.1 1.1a2.5 2.5 0 0 0 2.4-2.9l-1.5-6.5A4 4 0 0 0 17.3 5z"
  };

  function icon(name, filled) {
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", "20");
    svg.setAttribute("height", "20");
    svg.setAttribute("fill", filled ? "currentColor" : "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", ICON[name]);
    svg.appendChild(path);
    return svg;
  }

  function h(tag, props) {
    var el = document.createElement(tag);
    props = props || {};
    Object.keys(props).forEach(function (key) {
      var value = props[key];
      if (key === "class") el.className = value;
      else if (key === "text") el.textContent = value;
      else if (key.indexOf("on") === 0) el.addEventListener(key.slice(2), value);
      else if (value !== false && value != null) el.setAttribute(key, value === true ? "" : value);
    });
    for (var i = 2; i < arguments.length; i++) {
      var child = arguments[i];
      if (child == null || child === false) continue;
      el.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    }
    return el;
  }

  function iconButton(name, label, onclick, extra) {
    var props = { class: "icon-btn" + (extra ? " " + extra : ""), type: "button", "aria-label": label, title: label, onclick: onclick };
    return h("button", props, icon(name, name === "play" || name === "pause"));
  }

  function fmt(seconds) {
    seconds = Math.max(0, Math.floor(seconds || 0));
    return Math.floor(seconds / 60) + ":" + String(seconds % 60).padStart(2, "0");
  }

  function save(key, value) { try { localStorage.setItem("zyro_" + key, JSON.stringify(value)); } catch (e) {} }
  function load(key, fallback) { try { var raw = localStorage.getItem("zyro_" + key); return raw == null ? fallback : JSON.parse(raw); } catch (e) { return fallback; } }

  var toastTimer = null;
  function toast(message) {
    var el = document.getElementById("toast");
    el.textContent = message;
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.remove("show"); }, 7000);
  }

  var discord = new MiniDiscord(clientId);
  if (discord.platform === "mobile") document.body.classList.add("mobile");
  var token = "";
  var user = null;
  var state = {
    mode: apps.length === 1 ? apps[0] : "hub",
    view: "home",
    viewArg: null,
    queue: [],
    index: -1,
    shuffle: load("shuffle", false),
    repeat: load("repeat", "off"),
    volume: load("volume", 0.7),
    muted: false,
    likes: new Set(),
    likeList: [],
    playlists: [],
    history: [],
    home: null,
    results: null,
    query: "",
    queueOpen: false,
    busy: false
  };
  audio.volume = state.volume;

  function api(path, options) {
    options = options || {};
    var headers = { Authorization: "Bearer " + token };
    if (options.binary) headers["Content-Type"] = "application/octet-stream";
    else if (options.body) headers["Content-Type"] = "application/json";
    var payload = options.binary || (options.body ? JSON.stringify(options.body) : undefined);
    return fetch("api/" + path, { method: options.method || (payload ? "POST" : "GET"), headers: headers, body: payload }).then(function (res) {
      if (options.raw && res.ok) return res.arrayBuffer();
      return res.text().then(function (text) {
        var data = {};
        try { data = JSON.parse(text); } catch (e) { data = {}; }
        if (!res.ok) {
          var error = new Error((data.error || "The server answered with an error") + " (" + res.status + ")");
          error.status = res.status;
          throw error;
        }
        return data;
      });
    });
  }

  function current() { return state.index >= 0 ? state.queue[state.index] : null; }
  function thumbUrl(track) { return "api/thumb/" + track.id + (/^s\d{10}$/.test(track.id) && track.thumb ? "?src=" + encodeURIComponent(track.thumb) : ""); }

  var presenceTimer = null;
  var lastPresence = 0;
  function updatePresence() {
    if (!discord.embedded || !user || !token) return;
    var wait = Math.max(0, 4000 - (Date.now() - lastPresence));
    clearTimeout(presenceTimer);
    presenceTimer = setTimeout(sendPresence, wait);
  }
  var gamePresence = null;
  function setGamePresence(info) {
    gamePresence = info;
    updatePresence();
  }
  function sendPresence() {
    lastPresence = Date.now();
    var track = current();
    if (!track || audio.paused || audio.ended) {
      if (gamePresence) discord.setActivity({ type: 0, details: gamePresence.details, state: gamePresence.state, timestamps: { start: gamePresence.start } }).catch(function () {});
      else discord.setActivity(null).catch(function () {});
      return;
    }
    var duration = audio.duration && isFinite(audio.duration) ? audio.duration : track.duration;
    var now = Date.now();
    var start = Math.floor(now - audio.currentTime * 1000);
    var activity = {
      type: 2,
      details: track.title.slice(0, 128),
      state: (track.artist || "Unknown artist").slice(0, 128),
      timestamps: { start: start, end: Math.floor(start + duration * 1000) },
      assets: { large_image: track.thumb, large_text: track.title.slice(0, 128) }
    };
    discord.setActivity(activity).catch(function () {});
  }

  function setQueue(tracks, startIndex) {
    state.queue = tracks.slice();
    playIndex(startIndex || 0);
  }

  function playIndex(index) {
    if (index < 0 || index >= state.queue.length) return;
    state.index = index;
    var track = state.queue[index];
    render();
    playRequest(track.id).then(function (res) {
      if (current() !== track) return;
      audio.src = res.src;
      if (res.via === "soundcloud") toast("YouTube is blocked on this server, playing a SoundCloud version.");
      var promise = audio.play();
      if (promise && promise.catch) promise.catch(function (e) {
        if (e && e.name === "AbortError" && current() === track) {
          audio.addEventListener("canplay", function resume() { audio.removeEventListener("canplay", resume); if (current() === track) audio.play().catch(function () {}); });
          return;
        }
        toast(e && e.name === "NotAllowedError" ? "Press play to start." : "Playback was blocked: " + ((e && e.name) || "unknown"));
      });
      api("history", { body: { track: track } }).then(function () {
        state.history = [track].concat(state.history.filter(function (t, i) { return !(i === 0 && t.id === track.id); })).slice(0, 100);
        if (state.view === "history") render();
      }).catch(function () {});
    }).catch(function (err) {
      toast(err.message);
    });
  }

  function playRequest(id) {
    var tries = 0;
    function check(res) {
      if (res.state === "ready") return Promise.resolve(res);
      if (res.state === "error") {
        var failure = new Error(res.error + (res.detail ? " (" + res.detail.slice(0, 160) + ")" : ""));
        failure.final = true;
        return Promise.reject(failure);
      }
      if (++tries > 45) return Promise.reject(new Error("Preparing the song took too long. Try again."));
      if (tries === 2) toast("Preparing the song…");
      return new Promise(function (resolve) { setTimeout(resolve, 1500); }).then(function () { return api("ready/" + id); }).then(check);
    }
    var meta = (state.queue.concat(state.results || [])).filter(function (t) { return t.id === id; })[0] || {};
    return api("play", { body: { id: id, title: meta.title || "", artist: meta.artist || "", duration: meta.duration || 0 } }).then(check);
  }

  function next(auto) {
    if (!state.queue.length) return;
    if (auto && state.repeat === "one") { audio.currentTime = 0; audio.play(); return; }
    var target;
    if (state.shuffle && state.queue.length > 1) {
      do { target = Math.floor(Math.random() * state.queue.length); } while (target === state.index);
    } else {
      target = state.index + 1;
      if (target >= state.queue.length) {
        if (state.repeat === "all" || !auto) target = 0;
        else { audio.pause(); return; }
      }
    }
    playIndex(target);
  }

  function prev() {
    if (audio.currentTime > 4) { audio.currentTime = 0; return; }
    playIndex(state.index > 0 ? state.index - 1 : Math.max(0, state.queue.length - 1));
  }

  function togglePlay() {
    if (!current()) return;
    if (audio.paused) audio.play().catch(function () {}); else audio.pause();
  }

  function enqueue(track, playNext) {
    if (!state.queue.length) { setQueue([track], 0); return; }
    var at = playNext ? state.index + 1 : state.queue.length;
    state.queue.splice(at, 0, track);
    toast(playNext ? "Playing next" : "Added to queue");
    renderPlayer();
    if (state.queueOpen) render();
  }

  function isLiked(track) { return state.likes.has(track.id); }

  function toggleLike(track) {
    var want = !isLiked(track);
    api("like", { body: { track: track, liked: want } }).then(function () {
      if (want) {
        state.likes.add(track.id);
        state.likeList = [track].concat(state.likeList.filter(function (t) { return t.id !== track.id; }));
      } else {
        state.likes.delete(track.id);
        state.likeList = state.likeList.filter(function (t) { return t.id !== track.id; });
      }
      render();
    }).catch(function (err) { toast(err.message); });
  }

  function modal(title, body) {
    var overlay = h("div", { class: "overlay", onclick: function (e) { if (e.target === overlay) overlay.remove(); } },
      h("div", { class: "modal" },
        h("div", { class: "modal-head" }, h("h3", { text: title }), iconButton("close", "Close", function () { overlay.remove(); })),
        body));
    document.body.appendChild(overlay);
    return overlay;
  }

  function addToPlaylist(track) {
    var list = h("div", { class: "modal-list" });
    var overlay = modal("Add to playlist", list);
    function fill() {
      list.textContent = "";
      state.playlists.forEach(function (pl) {
        list.appendChild(h("button", { class: "row-btn", type: "button", onclick: function () {
          api("playlists/" + pl.id, { body: { action: "add", track: track } }).then(function (updated) {
            pl.tracks = updated.tracks;
            toast("Added to " + pl.name);
            overlay.remove();
            if (state.view === "library") render();
          }).catch(function (err) { toast(err.message); });
        } }, pl.name, h("span", { class: "muted", text: pl.tracks.length + " songs" })));
      });
      var input = h("input", { class: "text-input", placeholder: "New playlist name", maxlength: "60" });
      list.appendChild(h("div", { class: "new-row" }, input, h("button", { class: "btn", type: "button", onclick: function () {
        api("playlists", { body: { name: input.value } }).then(function (pl) {
          state.playlists.unshift(pl);
          fill();
        }).catch(function (err) { toast(err.message); });
      } }, "Create")));
    }
    fill();
  }

  function trackMenu(track, anchor) {
    var old = document.querySelector(".menu");
    if (old) old.remove();
    var menu = h("div", { class: "menu" });
    function item(label, fn) {
      menu.appendChild(h("button", { type: "button", onclick: function () { menu.remove(); fn(); } }, label));
    }
    item("Play next", function () { enqueue(track, true); });
    item("Add to queue", function () { enqueue(track, false); });
    item(isLiked(track) ? "Remove from liked" : "Like", function () { toggleLike(track); });
    item("Add to playlist", function () { addToPlaylist(track); });
    document.body.appendChild(menu);
    var rect = anchor.getBoundingClientRect();
    menu.style.top = Math.min(rect.bottom + 4, window.innerHeight - menu.offsetHeight - 100) + "px";
    menu.style.left = Math.max(8, Math.min(rect.right - menu.offsetWidth, window.innerWidth - menu.offsetWidth - 8)) + "px";
    setTimeout(function () {
      document.addEventListener("click", function close(e) { if (!menu.contains(e.target)) { menu.remove(); document.removeEventListener("click", close); } });
    }, 0);
  }

  function trackRow(track, list, index, extra) {
    var playing = current() && current().id === track.id;
    var row = h("div", { class: "track" + (playing ? " is-playing" : ""), tabindex: "0", onclick: function (e) {
      if (e.target.closest(".icon-btn")) return;
      setQueue(list, index);
    }, onkeydown: function (e) { if (e.key === "Enter") setQueue(list, index); } },
      h("img", { class: "thumb", src: thumbUrl(track), alt: "", loading: "lazy" }),
      h("div", { class: "meta" }, h("div", { class: "title", text: track.title }), h("div", { class: "sub", text: track.artist || "Unknown artist" })),
      h("div", { class: "dur", text: fmt(track.duration) }),
      iconButton("heart", isLiked(track) ? "Unlike" : "Like", function () { toggleLike(track); }, isLiked(track) ? "liked" : ""),
      iconButton("more", "More", function (e) { trackMenu(track, e.currentTarget); }),
      extra || null);
    return row;
  }

  function trackList(tracks, extraFor) {
    if (!tracks.length) return h("p", { class: "empty", text: "Nothing here yet." });
    var wrap = h("div", { class: "tracks" });
    tracks.forEach(function (track, i) { wrap.appendChild(trackRow(track, tracks, i, extraFor ? extraFor(track) : null)); });
    return wrap;
  }

  function section(title, trailing) {
    return h("div", { class: "section-head" }, h("h2", { text: title }), trailing || null);
  }

  function viewHome() {
    var box = h("div", { class: "view" });
    if (state.results) {
      box.appendChild(section("Results for “" + state.query + "”", h("button", { class: "btn ghost", type: "button", onclick: function () { state.results = null; state.query = ""; render(); } }, "Clear")));
      var chips = h("div", { class: "chips" });
      ["youtube", "soundcloud"].forEach(function (name) {
        chips.appendChild(h("button", { class: "btn " + ((state.source || "youtube") === name ? "" : "ghost"), type: "button", onclick: function () { search(state.query, name); } }, name === "youtube" ? "YouTube" : "SoundCloud"));
      });
      box.appendChild(chips);
      box.appendChild(trackList(state.results));
      return box;
    }
    box.appendChild(section(state.home && state.home.personal ? "Recommended for you" : "Recommended songs", iconButton("repeat", "Refresh", function () { loadHome(true); })));
    if (state.busy && !state.home) box.appendChild(h("p", { class: "empty", text: "Loading songs…" }));
    else if (state.home) box.appendChild(trackList(state.home.tracks));
    return box;
  }

  function viewLibrary() {
    var box = h("div", { class: "view" });
    var arg = state.viewArg;
    if (arg && arg !== "liked") {
      var pl = state.playlists.filter(function (p) { return p.id === arg; })[0];
      if (!pl) { state.viewArg = null; return viewLibrary(); }
      box.appendChild(h("button", { class: "btn ghost", type: "button", onclick: function () { state.viewArg = null; render(); } }, "← Library"));
      box.appendChild(section(pl.name, h("div", { class: "actions" },
        h("button", { class: "btn", type: "button", onclick: function () { if (pl.tracks.length) setQueue(pl.tracks, 0); } }, "Play all"),
        h("button", { class: "btn ghost", type: "button", onclick: function () {
          var name = window.prompt("Rename playlist", pl.name);
          if (name) api("playlists/" + pl.id, { body: { action: "rename", name: name } }).then(function () { pl.name = name.trim().slice(0, 60); render(); }).catch(function (e) { toast(e.message); });
        } }, "Rename"),
        h("button", { class: "btn danger", type: "button", onclick: function () {
          if (!window.confirm("Delete this playlist?")) return;
          api("playlists/" + pl.id, { body: { action: "delete" } }).then(function () {
            state.playlists = state.playlists.filter(function (p) { return p.id !== pl.id; });
            state.viewArg = null;
            render();
          }).catch(function (e) { toast(e.message); });
        } }, "Delete"))));
      box.appendChild(trackList(pl.tracks, function (track) {
        return iconButton("trash", "Remove from playlist", function () {
          api("playlists/" + pl.id, { body: { action: "remove", track_id: track.id } }).then(function (updated) { pl.tracks = updated.tracks; render(); }).catch(function (e) { toast(e.message); });
        });
      }));
      return box;
    }
    if (arg === "liked") {
      box.appendChild(h("button", { class: "btn ghost", type: "button", onclick: function () { state.viewArg = null; render(); } }, "← Library"));
      box.appendChild(section("Liked songs", h("button", { class: "btn", type: "button", onclick: function () { if (state.likeList.length) setQueue(state.likeList, 0); } }, "Play all")));
      box.appendChild(trackList(state.likeList));
      return box;
    }
    box.appendChild(section("Your library", h("button", { class: "btn", type: "button", onclick: function () {
      var name = window.prompt("Playlist name");
      if (name) api("playlists", { body: { name: name } }).then(function (pl) { state.playlists.unshift(pl); render(); }).catch(function (e) { toast(e.message); });
    } }, "New playlist")));
    var grid = h("div", { class: "cards" });
    grid.appendChild(h("button", { class: "card", type: "button", onclick: function () { state.viewArg = "liked"; render(); } }, icon("heart", true), h("strong", { text: "Liked songs" }), h("span", { class: "muted", text: state.likeList.length + " songs" })));
    state.playlists.forEach(function (pl) {
      grid.appendChild(h("button", { class: "card", type: "button", onclick: function () { state.viewArg = pl.id; render(); } }, icon("queue"), h("strong", { text: pl.name }), h("span", { class: "muted", text: pl.tracks.length + " songs" })));
    });
    box.appendChild(grid);
    return box;
  }

  function viewHistory() {
    var box = h("div", { class: "view" });
    box.appendChild(section("Recently played", state.history.length ? h("button", { class: "btn ghost", type: "button", onclick: function () {
      api("history/clear", { body: {} }).then(function () { state.history = []; render(); }).catch(function (e) { toast(e.message); });
    } }, "Clear history") : null));
    box.appendChild(trackList(state.history));
    return box;
  }

  function viewHub() {
    var cards = [];
    if (musicOn) cards.push(["music", "Music", "Search songs, build playlists and show what you are listening to."]);
    if (gameIds.length) cards.push(["games", "Games", "Play " + gameIds.map(function (id) { return id.charAt(0).toUpperCase() + id.slice(1); }).join(", ") + " with friends in this session."]);
    var box = h("div", { class: "hub" }, h("h1", { text: "Zyro" }), h("p", { class: "muted", text: "Pick an app to open." }));
    var grid = h("div", { class: "hub-grid" });
    cards.forEach(function (card) {
      grid.appendChild(h("button", { class: "hub-card", type: "button", onclick: function () { state.mode = card[0]; render(); } },
        h("span", { class: "hub-icon" }, icon(card[0] === "music" ? "music" : "games")),
        h("strong", { text: card[1] }),
        h("span", { class: "muted", text: card[2] })));
    });
    box.appendChild(grid);
    return box;
  }

  function viewGames() {
    var box = h("div", { class: "view" });
    if (!window.ZyroGames) {
      box.appendChild(h("p", { class: "muted", text: "Games could not load. Reopen the activity." }));
      return box;
    }
    window.ZyroGames.mount(box, { api: api, h: h, toast: toast, user: user, instanceId: discord.instanceId || "", games: gameIds, setPresence: setGamePresence });
    return box;
  }

  function viewSettings() {
    var box = h("div", { class: "view settings" });
    var avatar = user && user.avatar ? "https://cdn.discordapp.com/avatars/" + user.id + "/" + user.avatar + ".png?size=128" : "";
    box.appendChild(h("div", { class: "profile" },
      avatar ? h("img", { class: "avatar", src: avatar, alt: "" }) : h("div", { class: "avatar" }),
      h("h1", { text: user ? user.name : "Guest" }),
      current() && !audio.paused ? h("div", { class: "pill", text: "Listening to: " + current().title }) : null));
    box.appendChild(section("Playback"));
    var vol = h("input", { type: "range", min: "0", max: "100", value: String(Math.round(state.volume * 100)), "aria-label": "Default volume", oninput: function () { setVolume(vol.value / 100); } });
    box.appendChild(h("label", { class: "setting" }, h("span", { text: "Volume" }), vol));
    box.appendChild(h("p", { class: "muted", text: "Your liked songs, playlists and history are saved to your Discord account, so they follow you into any server, DM or voice channel." }));
    box.appendChild(h("button", { class: "btn danger", type: "button", onclick: function () {
      api("history/clear", { body: {} }).then(function () { state.history = []; toast("History cleared"); }).catch(function (e) { toast(e.message); });
    } }, "Clear listening history"));
    box.appendChild(h("p", { class: "muted", text: "Build " + build }));
    if (user) {
      var out = h("pre", { class: "diag", text: "" });
      box.appendChild(section("Diagnostics"));
      box.appendChild(h("button", { class: "btn ghost", type: "button", onclick: function () {
        out.textContent = "Testing search and playback, this can take up to a minute…";
        var report = {};
        api("diag" + (current() ? "?id=" + encodeURIComponent(current().id) + "&title=" + encodeURIComponent(current().title) + "&artist=" + encodeURIComponent(current().artist || "") + "&duration=" + (current().duration || 0) : "")).then(function (r) { report.server = r; return clientTest(report); }).catch(function (e) { report.error = e.message; }).then(function () { out.textContent = JSON.stringify(report, null, 2); });
      } }, "Run music diagnostics"));
      box.appendChild(out);
    }
    return box;
  }

  function clientTest(report) {
    report.player = { events: playerEvents.slice(), src: (audio.currentSrc || "").split("?")[0], networkState: audio.networkState, readyState: audio.readyState, paused: audio.paused, error: audio.error ? audio.error.code : 0 };
    report.client = { canPlayMp4: audio.canPlayType("audio/mp4"), canPlayWebm: audio.canPlayType("audio/webm; codecs=opus"), platform: discord.platform };
    return playRequest(current() ? current().id : "dQw4w9WgXcQ").then(function (res) {
      report.client.src = res.src.split("?")[0];
      return fetch(res.src, { headers: { Range: "bytes=0-1023" } }).then(function (r) {
        report.client.fetch_status = r.status;
        report.client.fetch_type = r.headers.get("Content-Type");
        report.client.fetch_range = r.headers.get("Content-Range");
        return r.arrayBuffer();
      }).then(function (buf) {
        report.client.fetch_bytes = buf.byteLength;
      }).catch(function (e) {
        report.client.fetch_error = String(e && e.message || e);
      }).then(function () {
        return new Promise(function (resolve) {
          var probe = new Audio();
          var done = false;
          function finish(result) { if (done) return; done = true; report.client.element = result; probe.removeAttribute("src"); resolve(); }
          probe.addEventListener("loadedmetadata", function () { finish({ ok: true, duration: probe.duration }); });
          probe.addEventListener("error", function () { finish({ ok: false, code: probe.error && probe.error.code, message: probe.error && probe.error.message }); });
          setTimeout(function () { finish({ ok: false, timeout: true }); }, 15000);
          probe.preload = "auto";
          probe.src = res.src;
          probe.load();
        });
      });
    }).catch(function (e) {
      report.client.prepare_error = e.message;
    });
  }

  function setVolume(value) {
    state.volume = Math.max(0, Math.min(1, value));
    state.muted = false;
    audio.volume = state.volume;
    save("volume", state.volume);
    renderPlayer();
  }

  function renderQueue() {
    var panel = h("aside", { class: "queue" },
      h("div", { class: "modal-head" }, h("h3", { text: "Queue" }), iconButton("close", "Close queue", function () { state.queueOpen = false; render(); })));
    if (!state.queue.length) panel.appendChild(h("p", { class: "empty", text: "The queue is empty." }));
    state.queue.forEach(function (track, i) {
      panel.appendChild(h("div", { class: "track compact" + (i === state.index ? " is-playing" : ""), onclick: function (e) { if (!e.target.closest(".icon-btn")) playIndex(i); } },
        h("img", { class: "thumb", src: thumbUrl(track), alt: "" }),
        h("div", { class: "meta" }, h("div", { class: "title", text: track.title }), h("div", { class: "sub", text: track.artist })),
        iconButton("trash", "Remove from queue", function () {
          state.queue.splice(i, 1);
          if (i < state.index) state.index--;
          else if (i === state.index) { state.index = Math.min(state.index, state.queue.length - 1); if (state.index >= 0) playIndex(state.index); else { audio.pause(); audio.removeAttribute("src"); } }
          render();
        })));
    });
    return panel;
  }

  var playerEl = null;
  function renderPlayer() {
    var track = current();
    var fresh = h("footer", { class: "player" },
      h("div", { class: "now" },
        track ? h("img", { class: "thumb big", src: thumbUrl(track), alt: "" }) : h("div", { class: "thumb big empty-thumb" }),
        h("div", { class: "meta" }, h("div", { class: "title", text: track ? track.title : "Nothing playing" }), h("div", { class: "sub", text: track ? track.artist : "Search for a song to start" }))),
      h("div", { class: "center" },
        h("div", { class: "controls" },
          iconButton("shuffle", "Shuffle", function () { state.shuffle = !state.shuffle; save("shuffle", state.shuffle); renderPlayer(); }, state.shuffle ? "active" : ""),
          iconButton("prev", "Previous", prev),
          iconButton(audio.paused ? "play" : "pause", audio.paused ? "Play" : "Pause", togglePlay, "play-btn"),
          iconButton("next", "Next", function () { next(false); }),
          iconButton("repeat", "Repeat: " + state.repeat, function () { state.repeat = state.repeat === "off" ? "all" : state.repeat === "all" ? "one" : "off"; save("repeat", state.repeat); renderPlayer(); }, state.repeat !== "off" ? "active" : "")),
        h("div", { class: "seek" },
          h("span", { class: "time", id: "t-now", text: fmt(audio.currentTime) }),
          h("input", { type: "range", id: "seek", min: "0", max: "1000", value: "0", "aria-label": "Seek", oninput: function (e) {
            var total = audio.duration && isFinite(audio.duration) ? audio.duration : (track ? track.duration : 0);
            audio.currentTime = (e.target.value / 1000) * total;
          } }),
          h("span", { class: "time", id: "t-total", text: fmt(track ? track.duration : 0) }))),
      h("div", { class: "side" },
        track ? iconButton("heart", isLiked(track) ? "Unlike" : "Like", function () { toggleLike(track); }, isLiked(track) ? "liked" : "") : null,
        iconButton("queue", "Queue", function () { state.queueOpen = !state.queueOpen; render(); }, state.queueOpen ? "active" : ""),
        h("div", { class: "volume" },
          iconButton(state.muted || state.volume === 0 ? "mute" : "volume", "Mute", function () { state.muted = !state.muted; audio.muted = state.muted; renderPlayer(); }),
          h("input", { type: "range", min: "0", max: "100", value: String(Math.round((state.muted ? 0 : state.volume) * 100)), "aria-label": "Volume", oninput: function (e) { setVolume(e.target.value / 100); } }))));
    if (playerEl && playerEl.parentNode) playerEl.parentNode.replaceChild(fresh, playerEl);
    playerEl = fresh;
    if (!fresh.parentNode) { var shell = document.querySelector(".shell"); if (shell) shell.appendChild(fresh); }
    tick();
  }

  function tick() {
    var seek = document.getElementById("seek");
    var now = document.getElementById("t-now");
    var total = document.getElementById("t-total");
    if (!seek) return;
    var track = current();
    var duration = audio.duration && isFinite(audio.duration) ? audio.duration : (track ? track.duration : 0);
    if (document.activeElement !== seek) seek.value = duration ? String(Math.floor((audio.currentTime / duration) * 1000)) : "0";
    now.textContent = fmt(audio.currentTime);
    total.textContent = fmt(duration);
  }

  function search(query, source) {
    query = query.trim();
    if (query.length < 2) return;
    state.query = query;
    state.view = "home";
    state.busy = true;
    state.results = [];
    render();
    state.source = source || state.source || "youtube";
    api("search?q=" + encodeURIComponent(query) + "&source=" + state.source).then(function (res) {
      state.results = res.tracks;
      state.busy = false;
      render();
    }).catch(function (err) { state.busy = false; state.results = null; toast(err.message); render(); });
  }

  function loadHome(force) {
    if (state.home && !force) return;
    state.busy = true;
    if (force) state.home = null;
    render();
    api("home").then(function (res) { state.home = res; state.busy = false; render(); }).catch(function (err) { state.busy = false; toast(err.message); render(); });
  }

  function render() {
    var keepScroll = document.querySelector(".content");
    var scroll = keepScroll ? keepScroll.scrollTop : 0;
    var searchValue = document.getElementById("q") ? document.getElementById("q").value : state.query;
    $app.textContent = "";
    if (state.mode === "hub") {
      if (window.ZyroGames) window.ZyroGames.suspend();
      $app.appendChild(viewHub());
      return;
    }
    var nav = h("nav", { class: "rail" });
    if (apps.length > 1) {
      nav.appendChild(h("button", { class: "rail-btn", type: "button", "aria-label": "All apps", title: "All apps", onclick: function () { state.mode = "hub"; render(); } }, icon("apps")));
    }
    var items = state.mode === "games" ? [] : [["home", "home", "Home"], ["library", "library", "Library"], ["history", "history", "History"], ["settings", "gear", "Settings"]];
    items.forEach(function (item) {
      nav.appendChild(h("button", { class: "rail-btn" + (state.view === item[0] ? " active" : ""), type: "button", "aria-label": item[2], title: item[2], onclick: function () {
        state.view = item[0];
        state.viewArg = null;
        render();
      } }, icon(item[1])));
    });
    var input = h("input", { id: "q", class: "search", type: "search", placeholder: "Search for songs and artists…", value: searchValue, maxlength: "100", onkeydown: function (e) { if (e.key === "Enter") search(e.target.value); } });
    var top = h("header", { class: "top" }, h("div", { class: "search-wrap" }, icon("search"), input, h("button", { class: "search-go", type: "button", onclick: function () { search(input.value); } }, "Search")));
    var body;
    if (state.mode === "games") body = viewGames();
    else if (state.view === "library") body = viewLibrary();
    else if (state.view === "history") body = viewHistory();
    else if (state.view === "settings") body = viewSettings();
    else body = viewHome();
    if (state.mode !== "games" && window.ZyroGames) window.ZyroGames.suspend();
    var content = h("main", { class: "content" }, state.mode === "games" ? null : top, body);
    var shell = h("div", { class: "shell" + (state.mode === "games" ? " games-mode" : "") + (state.mode === "games" && apps.length < 2 ? " no-rail" : ""), }, nav, content, state.queueOpen && state.mode !== "games" ? renderQueue() : null);
    $app.appendChild(shell);
    playerEl = null;
    renderPlayer();
    content.scrollTop = scroll;
  }

  function fail(title, message) {
    $app.textContent = "";
    $app.appendChild(h("div", { class: "boot" }, h("h2", { text: title }), h("p", { text: message })));
  }

  var playerEvents = [];
  ["loadstart", "loadedmetadata", "canplay", "playing", "waiting", "stalled", "suspend", "abort", "emptied", "error", "ended", "pause"].forEach(function (name) {
    audio.addEventListener(name, function () {
      playerEvents.push(name + (name === "error" && audio.error ? ":" + audio.error.code : "") + "@" + Math.round(audio.currentTime) + "s");
      if (playerEvents.length > 30) playerEvents.shift();
    });
  });
  audio.addEventListener("timeupdate", tick);
  audio.addEventListener("play", function () { renderPlayer(); updatePresence(); });
  audio.addEventListener("pause", function () { renderPlayer(); updatePresence(); });
  audio.addEventListener("seeked", updatePresence);
  audio.addEventListener("loadedmetadata", function () { tick(); updatePresence(); });
  audio.addEventListener("ended", function () { next(true); });
  audio.addEventListener("error", function () {
    if (!current() || !audio.getAttribute("src")) return;
    var code = audio.error ? audio.error.code : 0;
    var reasons = { 1: "aborted", 2: "network error", 3: "could not decode", 4: "format or source not supported" };
    toast("That song failed to load: " + (reasons[code] || "unknown") + ". Check Settings > diagnostics.");
  });
  document.addEventListener("keydown", function (e) {
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
    if (e.code === "Space") { e.preventDefault(); togglePlay(); }
    else if (e.key === "ArrowRight" && e.shiftKey) next(false);
    else if (e.key === "ArrowLeft" && e.shiftKey) prev();
  });

  function boot() {
    if (!apps.length) return fail("Not available", "No apps are turned on for this bot.");
    if (!enabled) return fail("Not available", "The music activity is not set up on this bot yet.");
    if (!discord.embedded) return fail("Open this inside Discord", "Zyro Music is a Discord Activity. Launch it from the App Launcher in a server, a DM or a voice channel.");
    discord.ready().then(function () {
      return discord.authorize(["identify", "rpc.activities.write"]);
    }).then(function (res) {
      return fetch("api/token", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code: res.code }) }).then(function (r) {
        return r.json().then(function (data) { if (!r.ok) throw new Error(data.error || "Sign in failed."); return data; });
      });
    }).then(function (res) {
      token = res.access_token;
      return discord.authenticate(token);
    }).then(function (auth) {
      user = { id: auth.user.id, name: auth.user.global_name || auth.user.username, avatar: auth.user.avatar, admin: false };
      render();
      api("me").then(function (me) { user.admin = !!me.admin; if (state.view === "settings") render(); }).catch(function () {});
      return api("library");
    }).then(function (lib) {
      state.likeList = lib.likes;
      state.likes = new Set(lib.likes.map(function (t) { return t.id; }));
      state.playlists = lib.playlists;
      state.history = lib.history;
      render();
      loadHome(false);
    }).catch(function (err) {
      fail("Could not start", (err && err.message) || "Discord did not answer. Close the activity and open it again.");
    });
  }

  boot();
})();
