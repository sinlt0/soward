(function () {
  var TIC = 35;
  var SKILLS = ["I'm too young to die", "Hey, not too rough", "Hurt me plenty", "Ultra-violence", "Nightmare!"];
  var TURN_CHOICES = [[30, "30 seconds"], [60, "1 minute"], [120, "2 minutes"], [300, "5 minutes"]];
  var BASE_NAMES = { doom2: "doom2.wad", doomu: "doomu.wad", doom: "doom.wad", doom1: "doom1.wad" };
  var K = { up: 173, down: 175, left: 172, right: 174, fire: 157, use: 32, run: 182, comma: 44, period: 46, enter: 13, esc: 27, tab: 9 };
  var CODE_KEYS = {
    ArrowUp: K.up, KeyW: K.up, ArrowDown: K.down, KeyS: K.down, ArrowLeft: K.left, ArrowRight: K.right,
    KeyA: K.comma, KeyD: K.period, Comma: K.comma, Period: K.period, ControlLeft: K.fire, ControlRight: K.fire, KeyF: K.fire,
    Space: K.use, KeyE: K.use, ShiftLeft: K.run, ShiftRight: K.run, Enter: K.enter, NumpadEnter: K.enter, Escape: K.esc, Tab: K.tab,
    Backspace: 127, KeyY: 121, KeyN: 110, KeyP: 112, Minus: 45, Equal: 61,
    Digit1: 49, Digit2: 50, Digit3: 51, Digit4: 52, Digit5: 53, Digit6: 54, Digit7: 55, Digit8: 56, Digit9: 57, Digit0: 48
  };
  var cache = { module: null, wad: null };
  var D = { root: null, ctx: null, session: null, onExit: null, started: 0, node: null };

  function h() { return D.ctx.h.apply(null, arguments); }
  function instance() { return D.ctx.instanceId || ""; }
  function query() { return "instance=" + encodeURIComponent(instance()); }
  function post(path, body) { body = body || {}; body.instance = instance(); return D.ctx.api("games/doom/" + path, { body: body }); }
  function wait(ms) { return new Promise(function (resolve) { setTimeout(resolve, ms); }); }
  function avatarUrl(player) { return player && player.avatar ? "https://cdn.discordapp.com/avatars/" + player.id + "/" + player.avatar + ".png?size=64" : ""; }
  function megabytes(n) { return (n / 1048576).toFixed(n < 10485760 ? 1 : 0) + " MB"; }

  function fetchBuffer(url) {
    return fetch(url).then(function (res) {
      if (!res.ok) throw new Error("Could not load " + url + " (" + res.status + ")");
      return res.arrayBuffer();
    });
  }

  function loadModule() {
    if (cache.module) return Promise.resolve(cache.module);
    return fetchBuffer("doom.wasm").then(function (bytes) { return WebAssembly.compile(bytes); }).then(function (module) { cache.module = module; return module; });
  }

  function loadBuiltinWad() {
    if (cache.wad) return Promise.resolve(cache.wad);
    return fetchBuffer("doom1.wad").then(function (buffer) { cache.wad = new Uint8Array(buffer); return cache.wad; });
  }

  function inspectWad(bytes) {
    var head = String.fromCharCode(bytes[0], bytes[1], bytes[2], bytes[3]);
    if (bytes.length < 12 || (head !== "IWAD" && head !== "PWAD")) return null;
    var view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    var count = view.getInt32(4, true);
    var offset = view.getInt32(8, true);
    if (count < 0 || count > 200000 || offset < 12 || offset + count * 16 > bytes.length) return null;
    var maps = [];
    for (var i = 0; i < count; i++) {
      var at = offset + i * 16 + 8;
      var name = "";
      for (var j = 0; j < 8; j++) {
        var c = bytes[at + j];
        if (!c) break;
        name += String.fromCharCode(c);
      }
      name = name.toUpperCase();
      if (/^E\dM\d$/.test(name) || /^MAP\d\d$/.test(name)) maps.push(name);
    }
    return { type: head, maps: maps, size: bytes.length };
  }

  function planWads(files) {
    var problems = [];
    var iwad = null;
    var pwads = [];
    files.forEach(function (file) {
      var info = inspectWad(file.bytes);
      if (!info) { problems.push(file.name + " is not a valid WAD file."); return; }
      file.info = info;
      if (info.type === "IWAD") { if (!iwad) iwad = file; else problems.push("Only one IWAD (a full game such as DOOM.WAD) can be used at a time."); }
      else pwads.push(file);
    });
    var kind = "doom1";
    if (iwad) {
      var set = {};
      iwad.info.maps.forEach(function (m) { set[m] = true; });
      kind = set.MAP01 ? "doom2" : set.E4M1 ? "doomu" : set.E2M1 ? "doom" : "doom1";
    }
    var episodic = [];
    var numbered = [];
    pwads.forEach(function (file) {
      file.info.maps.forEach(function (m) { (m.charAt(0) === "E" ? episodic : numbered).push(m); });
    });
    if (numbered.length && !episodic.length && kind !== "doom2") problems.push("These levels are made for Doom II. Add a Doom II IWAD (doom2.wad or freedoom2.wad) too.");
    if (episodic.length && !numbered.length && kind === "doom2") problems.push("These levels are made for Doom 1. Remove the Doom II IWAD or add a Doom 1 IWAD.");
    episodic.sort();
    numbered.sort();
    var first = kind === "doom2" ? numbered[0] : episodic[0];
    return { problems: problems, kind: kind, iwad: iwad, pwads: pwads, first: first || null };
  }

  function buildSession(plan, builtin, skill, start) {
    var files = {};
    var args = [];
    var baseName = BASE_NAMES[plan.kind];
    files[baseName] = plan.iwad ? plan.iwad.bytes : builtin;
    args.push("-skill", String(skill));
    if (start === "map") {
      var first = plan.first;
      if (plan.kind === "doom2") args.push("-warp", first ? String(parseInt(first.slice(3), 10)) : "1");
      else args.push("-warp", first ? first.charAt(1) : "1", first ? first.charAt(3) : "1");
    }
    if (plan.pwads.length) {
      args.push("-file");
      plan.pwads.forEach(function (file, index) {
        var name = "pwad" + (index + 1) + ".wad";
        files[name] = file.bytes;
        args.push(name);
      });
    }
    return { files: files, args: args.join(" ") };
  }

  function createEngine(module, files, args) {
    var memory = null;
    var handles = {};
    var next = 1;
    var lastLine = "";
    var store = {};
    Object.keys(files).forEach(function (name) { store[name.toLowerCase()] = files[name]; });
    var engine = { exited: false, error: "", imageData: null };

    function text(ptr) {
      var bytes = new Uint8Array(memory.buffer);
      var end = ptr;
      while (bytes[end]) end++;
      var out = "";
      for (var i = ptr; i < end; i++) out += String.fromCharCode(bytes[i]);
      return out;
    }

    function baseName(path) {
      var parts = path.split(/[\\/]/);
      return parts[parts.length - 1].toLowerCase();
    }

    var env = {
      host_print: function (ptr) { var line = text(ptr).trim(); if (line) lastLine = line; },
      host_exit: function (code) { engine.exited = true; engine.error = code ? lastLine : ""; throw new Error("doom-exit"); },
      fs_open: function (namePtr, modePtr) {
        var name = baseName(text(namePtr));
        var mode = text(modePtr);
        var id = next++;
        if (mode.indexOf("w") >= 0 || mode.indexOf("a") >= 0) {
          handles[id] = { name: name, data: new Uint8Array(1024), size: 0, pos: 0, write: true };
          return id;
        }
        var data = store[name];
        if (!data) { next--; return 0; }
        handles[id] = { name: name, data: data, size: data.length, pos: 0, write: false };
        return id;
      },
      fs_close: function (id) {
        var file = handles[id];
        if (file && file.write) store[file.name] = file.data.slice(0, file.size);
        delete handles[id];
      },
      fs_read: function (id, buf, count) {
        var file = handles[id];
        var n = Math.max(0, Math.min(count, file.size - file.pos));
        if (n) new Uint8Array(memory.buffer, buf, n).set(file.data.subarray(file.pos, file.pos + n));
        file.pos += n;
        return n;
      },
      fs_write: function (id, buf, count) {
        var file = handles[id];
        var need = file.pos + count;
        if (need > file.data.length) {
          var grown = new Uint8Array(Math.max(need, file.data.length * 2));
          grown.set(file.data.subarray(0, file.size));
          file.data = grown;
        }
        file.data.set(new Uint8Array(memory.buffer, buf, count), file.pos);
        file.pos += count;
        if (file.pos > file.size) file.size = file.pos;
        return count;
      },
      fs_seek: function (id, offset, origin) {
        var file = handles[id];
        file.pos = origin === 0 ? offset : origin === 1 ? file.pos + offset : file.size + offset;
        return 0;
      },
      fs_tell: function (id) { return handles[id].pos; },
      fs_eof: function (id) { return handles[id].pos >= handles[id].size ? 1 : 0; }
    };

    var instance = new WebAssembly.Instance(module, { env: env });
    var x = instance.exports;
    memory = x.memory;
    var argsPtr = x.args_ptr();
    var encoded = new TextEncoder().encode(args + "\0");
    new Uint8Array(memory.buffer).set(encoded, argsPtr);
    try { x.boot(); } catch (err) { engine.exited = true; engine.error = engine.error || lastLine || "Doom could not start."; }

    engine.step = function () {
      if (engine.exited) return false;
      try { x.step(); return true; } catch (err) { engine.exited = true; if (!engine.error && err.message !== "doom-exit") engine.error = lastLine || "Doom stopped unexpectedly."; return false; }
    };
    engine.key = function (code, down) {
      if (engine.exited) return;
      try { if (down) x.key_down(code); else x.key_up(code); } catch (err) { engine.exited = true; }
    };
    engine.draw = function (canvas) {
      if (engine.exited && !engine.imageData) return;
      var context = canvas.getContext("2d");
      if (!engine.imageData) engine.imageData = context.createImageData(320, 200);
      var source = new Uint8Array(memory.buffer, x.framebuffer(), 320 * 200 * 4);
      var target = engine.imageData.data;
      target.set(source);
      for (var i = 3; i < target.length; i += 4) target[i] = 255;
      context.putImageData(engine.imageData, 0, 0);
    };
    engine.sound = function () {
      if (engine.exited) return null;
      try { var at = x.sound(); return new Int16Array(memory.buffer.slice(at, at + 2048)); } catch (err) { return null; }
    };
    engine.tics = function () { return x.tics(); };
    return engine;
  }

  function makeAudio() {
    var self = { ctx: null, node: null, queue: [], gain: null, muted: false, pull: null };
    try { self.muted = localStorage.getItem("soward-doom-muted") === "1"; } catch (e) {}
    self.start = function () {
      if (self.ctx) { if (self.ctx.state === "suspended") self.ctx.resume(); return; }
      var Context = window.AudioContext || window.webkitAudioContext;
      if (!Context) return;
      try {
        self.ctx = new Context();
        var ratio = 11025 / self.ctx.sampleRate;
        var carry = 0;
        var left = 0;
        var right = 0;
        self.node = self.ctx.createScriptProcessor(2048, 0, 2);
        self.node.onaudioprocess = function (event) {
          var outL = event.outputBuffer.getChannelData(0);
          var outR = event.outputBuffer.getChannelData(1);
          for (var i = 0; i < outL.length; i++) {
            if (self.queue.length < 2 && self.pull) {
              var chunk = self.pull();
              if (chunk) for (var k = 0; k + 1 < chunk.length; k += 2) self.queue.push(Math.max(-1, Math.min(1, chunk[k] / 10923)), Math.max(-1, Math.min(1, chunk[k + 1] / 10923)));
            }
            if (self.queue.length >= 2 && !self.muted) {
              outL[i] = left;
              outR[i] = right;
            } else {
              outL[i] = 0;
              outR[i] = 0;
            }
            carry += ratio;
            while (carry >= 1) {
              carry -= 1;
              if (self.queue.length >= 2) { left = self.queue.shift(); right = self.queue.shift(); }
            }
          }
          if (self.queue.length > 44100) self.queue.length = 0;
        };
        self.node.connect(self.ctx.destination);
      } catch (err) { self.ctx = null; }
    };
    self.toggle = function () {
      self.muted = !self.muted;
      try { localStorage.setItem("soward-doom-muted", self.muted ? "1" : "0"); } catch (e) {}
      return self.muted;
    };
    self.close = function () {
      try { if (self.node) self.node.disconnect(); if (self.ctx) self.ctx.close(); } catch (e) {}
      self.ctx = null;
      self.node = null;
      self.queue = [];
    };
    return self;
  }

  function teardown() {
    var s = D.session;
    D.session = null;
    D.node = null;
    if (!s) return;
    s.dead = true;
    if (s.raf) cancelAnimationFrame(s.raf);
    clearTimeout(s.pollTimer);
    clearTimeout(s.sendTimer);
    window.removeEventListener("keydown", s.onKeyDown, true);
    window.removeEventListener("keyup", s.onKeyUp, true);
    window.removeEventListener("blur", s.onBlur);
    if (s.audio) s.audio.close();
    if (s.room && s.joined) post("room/" + s.room.id + "/leave").catch(function () {});
    if (D.ctx && D.ctx.setPresence) D.ctx.setPresence(null);
  }

  function exit() {
    teardown();
    var back = D.onExit;
    D.onExit = null;
    if (back) back();
  }

  function setPresence(state) {
    if (!D.ctx || !D.ctx.setPresence) return;
    if (!D.started) D.started = Date.now();
    D.ctx.setPresence({ details: "Playing DOOM", state: state, start: D.started });
  }

  function screen(title, body, backLabel) {
    D.root.textContent = "";
    var box = h("div", { class: "games doom" },
      h("div", { class: "section-head" }, h("h2", { text: title }), h("button", { class: "btn ghost", type: "button", onclick: exit }, backLabel || "Back")));
    body.forEach(function (node) { if (node) box.appendChild(node); });
    D.root.appendChild(box);
    return box;
  }

  function field(label, control, hint) {
    return h("label", { class: "doom-field" }, h("span", { class: "doom-label", text: label }), control, hint ? h("span", { class: "muted", text: hint }) : null);
  }

  function select(options, value, onchange) {
    var el = h("select", { class: "doom-select" });
    options.forEach(function (item) {
      var option = h("option", { value: String(item[0]) }, item[1]);
      if (String(item[0]) === String(value)) option.selected = true;
      el.appendChild(option);
    });
    el.addEventListener("change", function () { onchange(el.value); });
    return el;
  }

  function readFile(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () { resolve(new Uint8Array(reader.result)); };
      reader.onerror = function () { reject(new Error("Could not read " + file.name)); };
      reader.readAsArrayBuffer(file);
    });
  }

  function setup(root, ctx, mode, onExit) {
    teardown();
    D.root = root;
    D.ctx = ctx;
    D.onExit = onExit;
    D.started = 0;
    var form = { skill: 3, start: "map", source: "builtin", control: "turns", turn: 60, files: [], busy: false };
    var status = h("div", { class: "doom-status muted" });
    var fileList = h("div", { class: "doom-files" });
    var startButton;

    function setStatus(message, bad) {
      status.textContent = message || "";
      status.className = "doom-status" + (bad ? " bad" : " muted");
    }

    function refreshFiles() {
      fileList.textContent = "";
      form.files.forEach(function (file, index) {
        var info = file.info;
        fileList.appendChild(h("div", { class: "doom-file" },
          h("span", { text: file.name + " · " + megabytes(file.bytes.length) + (info ? " · " + info.type : "") }),
          h("button", { class: "btn ghost", type: "button", onclick: function () { form.files.splice(index, 1); refreshFiles(); } }, "Remove")));
      });
      if (form.source === "custom" && form.files.length) {
        var plan = planWads(form.files);
        if (plan.problems.length) setStatus(plan.problems[0], true);
        else setStatus("Ready: " + (plan.iwad ? plan.iwad.name : "Doom 1 shareware") + (plan.pwads.length ? " + " + plan.pwads.length + " add-on WAD" + (plan.pwads.length > 1 ? "s" : "") : ""));
      } else setStatus("");
    }

    var picker = h("input", { type: "file", accept: ".wad,.WAD", multiple: true, class: "doom-picker" });
    picker.addEventListener("change", function () {
      var picked = Array.prototype.slice.call(picker.files || []);
      picker.value = "";
      var limit = mode === "shared" ? 16 * 1048576 : 128 * 1048576;
      var jobs = picked.map(function (file) {
        if (file.size > limit) { setStatus(file.name + " is too large (limit " + megabytes(limit) + ").", true); return Promise.resolve(null); }
        return readFile(file).then(function (bytes) { return { name: file.name, bytes: bytes }; });
      });
      Promise.all(jobs).then(function (list) {
        list.forEach(function (item) { if (item && form.files.length < 4) form.files.push(item); });
        if (mode === "shared") {
          var total = form.files.reduce(function (sum, f) { return sum + f.bytes.length; }, 0);
          if (total > 24 * 1048576) { form.files.pop(); setStatus("Shared rooms take up to 24 MB of WADs in total.", true); return; }
        }
        refreshFiles();
      }).catch(function (err) { setStatus(err.message, true); });
    });

    var customBox = h("div", { class: "doom-custom" },
      h("p", { class: "muted", text: "Pick a full game IWAD (DOOM.WAD, DOOM2.WAD, Freedoom) and/or add-on levels. Files stay in your browser" + (mode === "shared" ? " and are sent to this room so everyone plays the same WADs." : ".") }),
      h("button", { class: "btn ghost", type: "button", onclick: function () { picker.click(); } }, "Choose WAD files"),
      picker,
      fileList);
    customBox.style.display = "none";

    var turnField = field("Turn length", select(TURN_CHOICES, 60, function (v) { form.turn = parseInt(v, 10); }));
    var controlField = field("Who controls the game", select([["turns", "Take turns, one player at a time"], ["vote", "Vote, the majority decides each key"]], "turns", function (v) {
      form.control = v;
      turnField.style.display = v === "turns" ? "" : "none";
    }));

    startButton = h("button", { class: "btn", type: "button", onclick: begin }, mode === "shared" ? "Create room" : "Start playing");

    function begin() {
      if (form.busy) return;
      var files = form.source === "custom" ? form.files : [];
      var plan = planWads(files);
      if (form.source === "custom" && !files.length) { setStatus("Choose at least one WAD file, or switch back to Doom 1.", true); return; }
      if (plan.problems.length) { setStatus(plan.problems[0], true); return; }
      form.busy = true;
      startButton.disabled = true;
      setStatus("Loading…");
      var audio = makeAudio();
      audio.start();
      Promise.all([loadModule(), loadBuiltinWad()]).then(function (loaded) {
        var built = buildSession(plan, loaded[1], form.skill, form.start);
        if (mode === "solo") {
          return play({ mode: "solo", module: loaded[0], built: built, audio: audio, skill: form.skill });
        }
        return createRoom(form, files, plan).then(function (room) {
          return play({ mode: "shared", module: loaded[0], built: built, audio: audio, room: room, skill: form.skill });
        });
      }).catch(function (err) {
        audio.close();
        form.busy = false;
        startButton.disabled = false;
        setStatus(err.message || "Could not start.", true);
      });
    }

    function createRoom(settings, files, plan) {
      var declared = plan.iwad ? [plan.iwad].concat(plan.pwads) : plan.pwads;
      var body = { control: settings.control, skill: settings.skill, start: settings.start, turn_seconds: settings.turn, wads: declared.map(function (f) { return { name: f.name, size: f.bytes.length }; }) };
      return post("rooms", body).then(function (res) {
        var room = res.room;
        var chain = Promise.resolve();
        declared.forEach(function (file, index) {
          chain = chain.then(function () { return upload(room.id, index, file, declared); });
        });
        return chain.then(function () { room.order = declared; return room; });
      });
    }

    function upload(roomId, index, file, all) {
      var size = file.bytes.length;
      var chunk = 192 * 1024;
      var offset = 0;
      function sendNext() {
        if (offset >= size) return Promise.resolve();
        var part = file.bytes.slice(offset, offset + chunk);
        setStatus("Uploading " + file.name + " " + Math.round(offset / size * 100) + "%");
        return D.ctx.api("games/doom/room/" + roomId + "/wad/" + index + "?" + query() + "&offset=" + offset, { binary: part.buffer }).then(function () {
          offset += part.length;
          return sendNext();
        });
      }
      return sendNext();
    }

    var skillField = field("Difficulty", select(SKILLS.map(function (name, i) { return [i + 1, name]; }), 3, function (v) { form.skill = parseInt(v, 10); }));
    var startField = field("Start", select([["map", "Straight into the first level"], ["title", "Title screen and menu"]], "map", function (v) { form.start = v; }));
    var sourceField = field("Game", select([["builtin", "Doom 1 (shareware, episode 1)"], ["custom", "My own WAD files"]], "builtin", function (v) {
      form.source = v;
      customBox.style.display = v === "custom" ? "" : "none";
      refreshFiles();
    }));

    var nodes = [
      h("p", { class: "muted", text: mode === "shared" ? "One game for the whole session. Everyone sees the same screen and controls it together." : "Your own game. Nobody else sees it or controls it." }),
      sourceField,
      customBox,
      skillField,
      startField
    ];
    if (mode === "shared") nodes.push(controlField, turnField);
    nodes.push(h("div", { class: "game-actions" }, startButton), status);
    screen(mode === "shared" ? "Doom: shared room" : "Doom: solo", nodes);
  }

  function join(root, ctx, summary, onExit) {
    teardown();
    D.root = root;
    D.ctx = ctx;
    D.onExit = onExit;
    D.started = 0;
    var status = h("div", { class: "doom-status muted", text: "Joining…" });
    screen("Doom: shared room", [status]);
    var audio = makeAudio();
    var picked;
    var box = D.root.querySelector(".games");
    var go = h("button", { class: "btn", type: "button" }, summary.you ? "Rejoin" : "Join the game");
    status.textContent = "Hosted by " + summary.host + " · " + (summary.control === "turns" ? "taking turns" : "voting") + (summary.custom ? " · custom WADs" : "");
    box.appendChild(h("div", { class: "game-actions" }, go));
    go.addEventListener("click", function () {
      go.disabled = true;
      audio.start();
      status.textContent = "Loading…";
      D.ctx.api("games/doom/room/" + summary.id + "?" + query()).then(function (res) {
        picked = res.room;
        return Promise.all([loadModule(), loadBuiltinWad()]);
      }).then(function (loaded) {
        return downloadWads(picked, status).then(function (files) {
          var plan = planWads(files);
          if (plan.problems.length) throw new Error(plan.problems[0]);
          var built = buildSession(plan, loaded[1], picked.skill, picked.start);
          return play({ mode: "shared", module: loaded[0], built: built, audio: audio, room: picked, skill: picked.skill });
        });
      }).catch(function (err) {
        audio.close();
        go.disabled = false;
        status.textContent = err.message || "Could not join.";
        status.className = "doom-status bad";
      });
    });
  }

  function downloadWads(room, status) {
    var out = [];
    var chain = Promise.resolve();
    room.wads.forEach(function (wad, index) {
      chain = chain.then(function () {
        status.textContent = "Downloading " + wad.name + " (" + megabytes(wad.size) + ")";
        return D.ctx.api("games/doom/room/" + room.id + "/wad/" + index + "?" + query(), { raw: true }).then(function (buffer) {
          out.push({ name: wad.name, bytes: new Uint8Array(buffer) });
        });
      });
    });
    return chain.then(function () { return out; });
  }

  function play(opts) {
    var s = {
      mode: opts.mode, module: opts.module, built: opts.built, audio: opts.audio, room: opts.room, joined: opts.mode === "shared",
      engine: null, canvas: h("canvas", { class: "doom-canvas", width: 320, height: 200, tabindex: "0" }),
      held: {}, pressed: {}, due: 0, last: 0, raf: 0, dead: false, ended: false,
      events: {}, next: 0, epoch: 0, horizon: -1, tic: 0, buffering: true, pollTimer: 0, sendTimer: 0, outbox: [], sending: false,
      players: [], controller: "", turnLeft: 0, effective: [], failures: 0, hud: null, banner: null, full: false
    };
    D.session = s;
    s.audio.pull = function () { return s.engine ? s.engine.sound() : null; };
    boot(s);

    s.banner = h("div", { class: "doom-banner" });
    s.hud = h("div", { class: "doom-hud" });
    var muteButton = h("button", { class: "btn ghost", type: "button", onclick: function () { muteButton.textContent = s.audio.toggle() ? "Sound off" : "Sound on"; } }, s.audio.muted ? "Sound off" : "Sound on");
    var stage = h("div", { class: "doom-stage" }, s.canvas, s.banner);
    var bar = h("div", { class: "doom-bar" },
      h("button", { class: "btn ghost", type: "button", onclick: exit }, "Leave"),
      muteButton,
      s.mode === "solo" ? h("button", { class: "btn ghost", type: "button", onclick: function () { restartSolo(s); } }, "Restart") : null,
      h("button", { class: "btn ghost", type: "button", onclick: function () { s.canvas.requestFullscreen && s.canvas.requestFullscreen().catch(function () {}); } }, "Fullscreen"));
    var help = h("div", { class: "doom-help muted", text: "W/S or ↑/↓ move · ←/→ turn · A/D strafe · Space or E use · Ctrl or F fire · Shift run · 1–7 weapons · Tab map · Esc menu" });
    D.root.textContent = "";
    D.node = h("div", { class: "games doom-play" }, bar, stage, s.mode === "shared" ? s.hud : null, touchPad(s), help);
    D.root.appendChild(D.node);
    renderHud(s);

    s.onKeyDown = function (event) { handleKey(s, event, true); };
    s.onKeyUp = function (event) { handleKey(s, event, false); };
    s.onBlur = function () { releaseAll(s); };
    window.addEventListener("keydown", s.onKeyDown, true);
    window.addEventListener("keyup", s.onKeyUp, true);
    window.addEventListener("blur", s.onBlur);
    s.canvas.addEventListener("pointerdown", function (event) { event.preventDefault(); s.canvas.focus(); press(s, K.fire, true); });
    s.canvas.addEventListener("pointerup", function () { press(s, K.fire, false); });
    s.canvas.addEventListener("pointerleave", function () { press(s, K.fire, false); });
    s.canvas.addEventListener("contextmenu", function (event) { event.preventDefault(); });
    s.canvas.focus();
    setPresence(s.mode === "shared" ? "In a shared room" : "Playing solo");
    s.last = performance.now();
    s.raf = requestAnimationFrame(function (t) { frame(s, t); });
    if (s.mode === "shared") poll(s);
    return Promise.resolve();
  }

  function boot(s) {
    s.engine = createEngine(s.module, s.built.files, s.built.args);
    s.events = {};
    s.tic = 0;
    s.due = 0;
    s.buffering = true;
    s.ended = false;
    Object.keys(s.pressed).forEach(function (k) { delete s.pressed[k]; });
    if (s.engine.exited) endGame(s);
  }

  function restartSolo(s) {
    boot(s);
    renderBanner(s);
    if (s.canvas) s.canvas.focus();
  }

  function endGame(s) {
    s.ended = true;
    renderBanner(s);
  }

  function renderBanner(s) {
    if (!s.banner) return;
    s.banner.textContent = "";
    s.banner.style.display = s.ended || s.full ? "" : "none";
    if (s.full) {
      s.banner.appendChild(h("strong", { text: "This room reached its input limit." }));
      if (s.room && s.room.host_id === D.ctx.user.id) s.banner.appendChild(h("button", { class: "btn", type: "button", onclick: function () { post("room/" + s.room.id + "/restart").catch(function (e) { D.ctx.toast(e.message); }); } }, "Restart game"));
      return;
    }
    if (!s.ended) return;
    s.banner.appendChild(h("strong", { text: s.engine && s.engine.error ? "Doom stopped: " + s.engine.error : "The game has ended." }));
    if (s.mode === "solo") s.banner.appendChild(h("button", { class: "btn", type: "button", onclick: function () { restartSolo(s); } }, "Play again"));
    else if (s.room && s.room.host_id === D.ctx.user.id) s.banner.appendChild(h("button", { class: "btn", type: "button", onclick: function () { post("room/" + s.room.id + "/restart").catch(function (e) { D.ctx.toast(e.message); }); } }, "Restart game"));
    else s.banner.appendChild(h("span", { class: "muted", text: "The host can restart it." }));
  }

  function typing(event) {
    var el = event.target;
    return el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT");
  }

  function handleKey(s, event, down) {
    if (typing(event)) return;
    var key = CODE_KEYS[event.code];
    if (key === undefined) return;
    event.preventDefault();
    event.stopPropagation();
    if (event.repeat) return;
    s.audio.start();
    var tag = event.code;
    if (down) { if (s.held[tag]) return; s.held[tag] = key; } else { if (!s.held[tag]) return; delete s.held[tag]; }
    press(s, key, down);
  }

  function releaseAll(s) {
    Object.keys(s.held).forEach(function (tag) { press(s, s.held[tag], false); delete s.held[tag]; });
    Object.keys(s.pressed).slice().forEach(function (k) { press(s, parseInt(k, 10), false); });
  }

  function press(s, key, down) {
    var count = s.pressed[key] || 0;
    if (down) {
      s.pressed[key] = count + 1;
      if (count > 0) return;
    } else {
      if (count === 0) return;
      if (count > 1) { s.pressed[key] = count - 1; return; }
      delete s.pressed[key];
    }
    if (s.mode === "solo") { if (s.engine) s.engine.key(key, down); return; }
    s.outbox.push([key, down ? 1 : 0]);
    scheduleSend(s);
  }

  function scheduleSend(s) {
    if (s.sendTimer || s.sending) return;
    s.sendTimer = setTimeout(function () { s.sendTimer = 0; flush(s); }, 25);
  }

  function flush(s) {
    if (s.dead || s.sending || !s.outbox.length) return;
    var batch = s.outbox.splice(0, 16);
    s.sending = true;
    post("room/" + s.room.id + "/input", { keys: batch }).then(function () {
      s.sending = false;
      if (s.outbox.length) flush(s);
    }).catch(function (err) {
      s.sending = false;
      if (err.status === 404) { roomGone(s); return; }
      if (err.status !== 429) s.outbox = batch.concat(s.outbox);
      s.sendTimer = setTimeout(function () { s.sendTimer = 0; flush(s); }, 400);
    });
  }

  function roomGone(s) {
    if (s.dead) return;
    D.ctx.toast("This room was closed.");
    s.joined = false;
    exit();
  }

  function poll(s) {
    if (s.dead) return;
    D.ctx.api("games/doom/room/" + s.room.id + "/poll?" + query() + "&since=" + s.next + "&epoch=" + s.epoch).then(function (res) {
      if (s.dead) return;
      s.failures = 0;
      if (res.reset && s.epoch !== 0) {
        boot(s);
        s.horizon = -1;
        s.next = 0;
        s.epoch = res.epoch;
        renderBanner(s);
        s.pollTimer = setTimeout(function () { poll(s); }, 20);
        return;
      }
      s.epoch = res.epoch;
      res.events.forEach(function (ev) { (s.events[ev[0]] = s.events[ev[0]] || []).push([ev[1], ev[2]]); });
      s.next = res.next;
      s.horizon = Math.max(s.horizon, res.horizon);
      s.players = res.players;
      s.controller = res.controller;
      s.turnLeft = res.turn_left;
      s.effective = res.effective;
      if (res.full !== s.full) { s.full = res.full; renderBanner(s); }
      renderHud(s);
      s.pollTimer = setTimeout(function () { poll(s); }, 110);
    }).catch(function (err) {
      if (s.dead) return;
      if (err.status === 404) { roomGone(s); return; }
      s.failures += 1;
      if (s.failures === 4) D.ctx.toast("Connection lost. Retrying…");
      s.pollTimer = setTimeout(function () { poll(s); }, Math.min(2000, 300 * s.failures));
    });
  }

  function frame(s, now) {
    if (s.dead) return;
    var dt = Math.min(250, now - s.last);
    s.last = now;
    var engine = s.engine;
    if (engine && !engine.exited) {
      if (s.mode === "solo") {
        s.due += dt * TIC / 1000;
        var steps = Math.min(6, Math.floor(s.due));
        s.due -= steps;
        for (var i = 0; i < steps; i++) if (!engine.step()) break;
      } else runShared(s, dt);
      if (engine.exited) endGame(s);
    }
    if (engine) engine.draw(s.canvas);
    s.raf = requestAnimationFrame(function (t) { frame(s, t); });
  }

  function runShared(s, dt) {
    var gap = s.horizon - s.tic + 1;
    if (s.buffering) {
      if (gap >= 6 || gap > 60) s.buffering = false;
      else return;
    }
    if (gap <= 0) { s.buffering = true; return; }
    var speed = 1;
    var steps;
    if (gap > 240) steps = Math.min(gap, 400);
    else {
      if (gap > 10) speed = Math.min(4, 1 + (gap - 8) / 16);
      s.due += dt * TIC * speed / 1000;
      steps = Math.min(Math.floor(s.due), gap, 24);
      s.due -= Math.floor(s.due);
    }
    for (var i = 0; i < steps; i++) {
      var list = s.events[s.tic];
      if (list) {
        for (var k = 0; k < list.length; k++) s.engine.key(list[k][0], list[k][1] === 1);
        delete s.events[s.tic];
      }
      if (!s.engine.step()) { s.tic++; break; }
      s.tic++;
    }
  }

  function renderHud(s) {
    if (s.mode !== "shared" || !s.hud) return;
    var me = D.ctx.user.id;
    var turns = s.room.control === "turns";
    var line;
    if (turns) {
      var holder = s.players.filter(function (p) { return p.id === s.controller; })[0];
      line = !holder ? "Waiting for a player" : holder.id === me ? "Your turn" + (s.turnLeft ? " · " + s.turnLeft + "s left" : "") : holder.name + " is playing" + (s.turnLeft ? " · " + s.turnLeft + "s left" : "");
    } else {
      var online = s.players.filter(function (p) { return p.online; }).length;
      line = "Vote mode · a key counts when most of the " + online + " active player" + (online === 1 ? "" : "s") + " hold it";
    }
    s.hud.textContent = "";
    s.hud.appendChild(h("div", { class: "game-status", text: line }));
    var list = h("div", { class: "doom-players" });
    s.players.forEach(function (p) {
      var avatar = avatarUrl(p);
      var active = turns ? p.id === s.controller : p.held > 0 && p.online;
      list.appendChild(h("div", { class: "doom-player" + (active ? " active" : "") + (p.online ? "" : " away") },
        avatar ? h("img", { class: "avatar-sm", src: avatar, alt: "" }) : h("span", { class: "avatar-sm" }),
        h("span", { text: p.name + (p.id === me ? " (you)" : "") })));
    });
    s.hud.appendChild(list);
    var actions = h("div", { class: "game-actions" });
    if (turns && s.controller === me && s.players.filter(function (p) { return p.online; }).length > 1) actions.appendChild(h("button", { class: "btn", type: "button", onclick: function () { post("room/" + s.room.id + "/pass").catch(function () {}); } }, "Pass the turn"));
    if (s.room.host_id === me) {
      actions.appendChild(h("button", { class: "btn ghost", type: "button", onclick: function () { post("room/" + s.room.id + "/restart").catch(function (e) { D.ctx.toast(e.message); }); } }, "Restart game"));
      actions.appendChild(h("button", { class: "btn danger", type: "button", onclick: function () { post("room/" + s.room.id + "/close").catch(function () {}).then(function () { s.joined = false; exit(); }); } }, "Close room"));
    }
    if (actions.childNodes.length) s.hud.appendChild(actions);
    if (turns && s.controller !== me) s.hud.appendChild(h("p", { class: "muted doom-note", text: "Spectating. Your keys are ignored until it is your turn." }));
  }

  function touchPad(s) {
    var pad = h("div", { class: "doom-pad" });
    var buttons = [["◀", K.left], ["▲", K.up], ["▼", K.down], ["▶", K.right], ["⇦", K.comma], ["⇨", K.period], ["Fire", K.fire], ["Use", K.use], ["Run", K.run], ["Map", K.tab], ["Menu", K.esc], ["OK", K.enter]];
    buttons.forEach(function (item) {
      var button = h("button", { class: "doom-key", type: "button" }, item[0]);
      var on = function (event) { event.preventDefault(); s.audio.start(); press(s, item[1], true); };
      var off = function (event) { event.preventDefault(); press(s, item[1], false); };
      button.addEventListener("pointerdown", on);
      button.addEventListener("pointerup", off);
      button.addEventListener("pointerleave", off);
      button.addEventListener("pointercancel", off);
      button.addEventListener("contextmenu", function (event) { event.preventDefault(); });
      pad.appendChild(button);
    });
    return pad;
  }

  window.SowardDoom = {
    setup: setup,
    join: join,
    stop: teardown,
    attach: function (root, ctx) {
      if (!D.session || !D.node) return false;
      D.root = root;
      D.ctx = ctx;
      root.textContent = "";
      root.appendChild(D.node);
      return true;
    }
  };
})();
