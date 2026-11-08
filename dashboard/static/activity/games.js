(function () {
  var GLYPH = { K: "♚", Q: "♛", R: "♜", B: "♝", N: "♞", P: "♟" };
  var TEXT = "︎";
  var CATALOG = { doom: { title: "Doom", glyph: "\u2620", text: "Doom 1 in your browser, with your own WAD files too. Play solo, or share one game with the whole session by taking turns or voting." }, chess: { title: "Chess", glyph: "\u265E", text: "Full rules including castling, en passant and promotion. Everyone in this session can watch." } };
  var START_COUNTS = { P: 8, N: 2, B: 2, R: 2, Q: 1 };
  var VALUE = { P: 1, N: 3, B: 3, R: 5, Q: 9 };
  var G = { view: "lobby", rooms: [], doomRooms: [], room: null, selected: -1, promotion: null, flipped: null, root: null, ctx: null, timer: null, busy: false, ticks: 0, confirmResign: false, resignTimer: null, started: 0 };

  function h() { return G.ctx.h.apply(null, arguments); }
  function instance() { return G.ctx.instanceId || ""; }
  function query() { return "instance=" + encodeURIComponent(instance()); }
  function squareName(index) { return "abcdefgh".charAt(index % 8) + (Math.floor(index / 8) + 1); }
  function squareIndex(name) { return (parseInt(name.charAt(1), 10) - 1) * 8 + "abcdefgh".indexOf(name.charAt(0)); }
  function seatName(side) { return side === "w" ? "White" : "Black"; }
  function avatarUrl(player) { return player && player.avatar ? "https://cdn.discordapp.com/avatars/" + player.id + "/" + player.avatar + ".png?size=64" : ""; }

  function post(path, body) {
    body = body || {};
    body.instance = instance();
    return G.ctx.api("games/" + path, { body: body });
  }

  function setRoom(room) {
    var previous = G.room;
    G.room = room;
    if (!previous || previous.id !== room.id || previous.version !== room.version) {
      if (G.selected >= 0 && (room.status !== "playing" || room.you !== room.turn || (previous && previous.moves.length !== room.moves.length))) G.selected = -1;
      G.promotion = null;
    }
    updatePresence();
  }

  function updatePresence() {
    if (!G.ctx.setPresence) return;
    if (G.view !== "room" || !G.room) { G.ctx.setPresence(null); return; }
    var room = G.room;
    var opponent = room.you === "w" ? room.players.b : room.you === "b" ? room.players.w : null;
    var state = room.status === "waiting" ? "Waiting for an opponent" : room.you === "s" ? "Watching a game" : opponent ? "vs " + opponent.name : "In a game";
    if (!G.started) G.started = Date.now();
    G.ctx.setPresence({ details: "Playing Chess", state: state.slice(0, 120), start: G.started });
  }

  function enter(room) {
    G.view = "room";
    G.started = 0;
    G.selected = -1;
    G.promotion = null;
    G.flipped = null;
    G.room = null;
    setRoom(room);
    draw();
  }

  function leave() {
    G.view = "lobby";
    G.room = null;
    G.selected = -1;
    G.promotion = null;
    updatePresence();
    refreshRooms();
    draw();
  }

  function refreshRooms() {
    var doomOn = (G.ctx.games || []).indexOf("doom") >= 0;
    var chessOn = (G.ctx.games || []).indexOf("chess") >= 0;
    var jobs = [
      chessOn ? G.ctx.api("games/rooms?" + query()).then(function (res) { G.rooms = res.rooms || []; }) : Promise.resolve(),
      doomOn ? G.ctx.api("games/doom/rooms?" + query()).then(function (res) { G.doomRooms = res.rooms || []; }) : Promise.resolve()
    ];
    return Promise.all(jobs.map(function (job) { return job.catch(function () {}); })).then(function () {
      if (G.view === "lobby") draw();
    });
  }

  function poll() {
    if (!G.root || !G.root.isConnected || !instance()) return;
    if (G.busy || G.view === "doom") return;
    G.busy = true;
    var task;
    if (G.view === "room" && G.room) {
      task = G.ctx.api("games/room/" + G.room.id + "?" + query() + "&v=" + G.room.version).then(function (res) {
        if (res.changed && G.view === "room") { setRoom(res.room); draw(); }
      }).catch(function (err) {
        if (err.status === 404 && G.view === "room") { G.ctx.toast("This room was closed."); leave(); }
      });
    } else {
      G.ticks += 1;
      task = G.ticks % 2 === 0 ? refreshRooms() : Promise.resolve();
    }
    task.then(function () { G.busy = false; }, function () { G.busy = false; });
  }

  function startPolling() {
    if (G.timer) return;
    G.timer = setInterval(poll, 1500);
  }

  function stopPolling() {
    if (G.timer) clearInterval(G.timer);
    G.timer = null;
  }

  function act(path, body) {
    if (!G.room) return Promise.resolve();
    return post("room/" + G.room.id + "/" + path, body).then(function (res) {
      if (res.room) { setRoom(res.room); draw(); } else { leave(); }
    }).catch(function (err) { G.ctx.toast(err.message); poll(); });
  }

  function createRoom(game, color) {
    post("rooms", { game: game, color: color }).then(function (res) { enter(res.room); }).catch(function (err) { G.ctx.toast(err.message); });
  }

  function openRoom(summary) {
    var action = summary.you ? Promise.resolve() : (summary.players.w && summary.players.b ? Promise.resolve() : post("room/" + summary.id + "/join"));
    action.then(function () {
      return G.ctx.api("games/room/" + summary.id + "?" + query() + "&v=0");
    }).then(function (res) { enter(res.room); }).catch(function (err) { G.ctx.toast(err.message); refreshRooms(); });
  }

  function startDoom(mode, summary) {
    G.view = "doom";
    var back = function () { G.view = "lobby"; updatePresence(); refreshRooms(); draw(); };
    if (mode === "join") window.SowardDoom.join(G.root, G.ctx, summary, back);
    else window.SowardDoom.setup(G.root, G.ctx, mode, back);
  }

  function drawLobby() {
    var box = h("div", { class: "games" });
    box.appendChild(h("div", { class: "section-head" }, h("h2", { text: "Games" })));
    if (!instance()) {
      box.appendChild(h("p", { class: "muted", text: "Open this inside a Discord Activity to play with friends." }));
      return box;
    }
    (G.ctx.games || []).forEach(function (id) {
      var info = CATALOG[id];
      if (!info) return;
      var card = h("div", { class: "game-card" },
        h("div", { class: "game-glyph", text: info.glyph + TEXT }),
        h("div", { class: "game-info" },
          h("h3", { text: info.title }),
          h("p", { class: "muted", text: info.text })));
      var row = h("div", { class: "game-actions" });
      if (id === "doom") {
        row.appendChild(h("button", { class: "btn", type: "button", onclick: function () { startDoom("solo"); } }, "Play solo"));
        row.appendChild(h("button", { class: "btn ghost", type: "button", onclick: function () { startDoom("shared"); } }, "Host a shared room"));
      } else {
        [["w", "Play as White"], ["b", "Play as Black"], ["random", "Random"]].forEach(function (item) {
          row.appendChild(h("button", { class: "btn" + (item[0] === "random" ? " ghost" : ""), type: "button", onclick: function () { createRoom(id, item[0]); } }, item[1]));
        });
      }
      card.appendChild(row);
      box.appendChild(card);
    });
    box.appendChild(h("div", { class: "section-head" }, h("h2", { text: "Open rooms" }), h("button", { class: "btn ghost", type: "button", onclick: refreshRooms }, "Refresh")));
    if (!G.rooms.length && !G.doomRooms.length) {
      box.appendChild(h("p", { class: "muted", text: "No rooms yet. Create one and ask a friend to join." }));
    }
    G.doomRooms.forEach(function (room) {
      var label = room.status === "loading" ? "Loading" : room.you ? "Rejoin" : "Join";
      box.appendChild(h("div", { class: "room-row" },
        h("div", { class: "room-text" },
          h("strong", { text: "Doom with " + room.host }),
          h("span", { class: "muted", text: "Shared · " + (room.control === "turns" ? "taking turns" : "voting") + " · " + room.players + " playing" + (room.custom ? " · custom WADs" : "") })),
        h("button", { class: "btn", type: "button", disabled: room.status === "loading", onclick: function () { startDoom("join", room); } }, label)));
    });
    G.rooms.forEach(function (room) {
      var white = room.players.w || "Waiting…";
      var black = room.players.b || "Waiting…";
      var label = room.you ? "Rejoin" : room.status === "waiting" ? "Join" : "Watch";
      box.appendChild(h("div", { class: "room-row" },
        h("div", { class: "room-text" },
          h("strong", { text: white + " vs " + black }),
          h("span", { class: "muted", text: "Chess · " + (room.status === "waiting" ? "waiting for a player" : room.status === "playing" ? room.moves + " moves played" : "finished") })),
        h("button", { class: "btn", type: "button", onclick: function () { openRoom(room); } }, label)));
    });
    return box;
  }

  function material(board) {
    var counts = { w: {}, b: {} };
    for (var i = 0; i < 64; i++) {
      var piece = board.charAt(i);
      if (piece === "." || piece.toLowerCase() === "k") continue;
      var side = piece === piece.toUpperCase() ? "w" : "b";
      var kind = piece.toUpperCase();
      counts[side][kind] = (counts[side][kind] || 0) + 1;
    }
    var taken = { w: [], b: [] };
    var score = { w: 0, b: 0 };
    ["Q", "R", "B", "N", "P"].forEach(function (kind) {
      ["w", "b"].forEach(function (side) {
        var missing = START_COUNTS[kind] - (counts[side][kind] || 0);
        var other = side === "w" ? "b" : "w";
        for (var n = 0; n < missing; n++) taken[other].push(kind);
        if (missing > 0) score[other] += missing * VALUE[kind];
      });
    });
    return { taken: taken, lead: score.w - score.b };
  }

  function playerBar(room, side, mat) {
    var player = room.players[side];
    var active = room.status === "playing" && room.turn === side;
    var glyphs = mat.taken[side].map(function (kind) { return GLYPH[kind] + TEXT; }).join("");
    var lead = side === "w" ? mat.lead : -mat.lead;
    var url = avatarUrl(player);
    return h("div", { class: "player-bar" + (active ? " active" : "") },
      url ? h("img", { class: "avatar-sm", src: url, alt: "" }) : h("div", { class: "avatar-sm empty" }),
      h("div", { class: "player-name" },
        h("strong", { text: player ? player.name + (player.id === G.ctx.user.id ? " (you)" : "") : "Waiting for a player…" }),
        h("span", { class: "muted" }, seatName(side))),
      h("div", { class: "captured", text: glyphs + (lead > 0 ? " +" + lead : "") }));
  }

  function resultText(room) {
    var result = room.result;
    if (!result) return "";
    var reason = result.reason.charAt(0).toUpperCase() + result.reason.slice(1);
    if (!result.winner) return "Draw · " + reason;
    var winnerSide = seatName(result.winner);
    if (room.you === result.winner) return "You win · " + reason;
    if (room.you === "w" || room.you === "b") return "You lose · " + reason;
    return winnerSide + " wins · " + reason;
  }

  function statusText(room) {
    if (room.status === "waiting") return "Waiting for an opponent to join…";
    if (room.status === "finished") return resultText(room);
    var base = room.you === room.turn ? "Your move" : room.you === "s" ? seatName(room.turn) + " to move" : "Opponent's move";
    return room.check >= 0 ? base + " · Check!" : base;
  }

  function targetsFrom(room, from) {
    var list = [];
    room.legal.forEach(function (text) {
      if (squareIndex(text.slice(0, 2)) === from) list.push({ to: squareIndex(text.slice(2, 4)), promo: text.slice(4) });
    });
    return list;
  }

  function sendMove(text) {
    G.selected = -1;
    G.promotion = null;
    act("move", { move: text });
  }

  function tapSquare(square) {
    var room = G.room;
    if (!room || room.status !== "playing" || room.you !== room.turn) return;
    if (G.promotion) return;
    if (G.selected >= 0) {
      var options = targetsFrom(room, G.selected).filter(function (item) { return item.to === square; });
      if (options.length) {
        var from = squareName(G.selected);
        var to = squareName(square);
        if (options.length > 1) { G.promotion = { from: from, to: to }; draw(); return; }
        sendMove(from + to + options[0].promo);
        return;
      }
    }
    var piece = room.board.charAt(square);
    var mine = piece !== "." && ((room.you === "w") === (piece === piece.toUpperCase()));
    G.selected = mine && targetsFrom(room, square).length ? (G.selected === square ? -1 : square) : -1;
    draw();
  }

  function drawBoard(room) {
    var flipped = G.flipped === null ? room.you === "b" : G.flipped;
    var last = room.moves.length ? room.moves[room.moves.length - 1].m : "";
    var lastFrom = last ? squareIndex(last.slice(0, 2)) : -1;
    var lastTo = last ? squareIndex(last.slice(2, 4)) : -1;
    var targets = G.selected >= 0 ? targetsFrom(room, G.selected) : [];
    var board = h("div", { class: "chess-board" + (flipped ? " flipped" : "") });
    for (var i = 0; i < 8; i++) {
      for (var j = 0; j < 8; j++) {
        var rank = flipped ? i : 7 - i;
        var file = flipped ? 7 - j : j;
        var square = rank * 8 + file;
        var piece = room.board.charAt(square);
        var classes = "sq " + ((rank + file) % 2 === 0 ? "dark" : "light");
        if (square === G.selected) classes += " sel";
        if (square === lastFrom || square === lastTo) classes += " last";
        if (square === room.check) classes += " check";
        var isTarget = targets.some(function (item) { return item.to === square; });
        if (isTarget) classes += piece !== "." ? " capture" : " target";
        var cell = h("button", { class: classes, type: "button", "aria-label": squareName(square) + (piece !== "." ? " " + piece : ""), onclick: (function (s) { return function () { tapSquare(s); }; })(square) });
        if (piece !== ".") {
          var white = piece === piece.toUpperCase();
          cell.appendChild(h("span", { class: "pc " + (white ? "wp" : "bp"), text: GLYPH[piece.toUpperCase()] + TEXT }));
        }
        if (j === 0) cell.appendChild(h("i", { class: "coord rank", text: String(rank + 1) }));
        if (i === 7) cell.appendChild(h("i", { class: "coord file", text: "abcdefgh".charAt(file) }));
        board.appendChild(cell);
      }
    }
    var wrap = h("div", { class: "board-wrap" }, board);
    if (G.promotion) {
      var picker = h("div", { class: "promo" }, h("strong", { text: "Promote to" }));
      var side = room.you;
      [["q", "Q"], ["r", "R"], ["b", "B"], ["n", "N"]].forEach(function (item) {
        picker.appendChild(h("button", { class: "promo-btn", type: "button", "aria-label": item[1], onclick: function () { sendMove(G.promotion.from + G.promotion.to + item[0]); } },
          h("span", { class: "pc " + (side === "w" ? "wp" : "bp"), text: GLYPH[item[1]] + TEXT })));
      });
      picker.appendChild(h("button", { class: "btn ghost", type: "button", onclick: function () { G.promotion = null; draw(); } }, "Cancel"));
      wrap.appendChild(picker);
    }
    return wrap;
  }

  function movesList(room) {
    var list = h("div", { class: "move-list" });
    if (!room.moves.length) { list.appendChild(h("span", { class: "muted", text: "No moves yet." })); return list; }
    for (var i = 0; i < room.moves.length; i += 2) {
      var line = h("span", { class: "move-pair" }, h("b", { text: (i / 2 + 1) + "." }), h("span", { text: room.moves[i].san }));
      if (room.moves[i + 1]) line.appendChild(h("span", { text: room.moves[i + 1].san }));
      list.appendChild(line);
    }
    return list;
  }

  function resign() {
    if (!G.confirmResign) {
      G.confirmResign = true;
      clearTimeout(G.resignTimer);
      G.resignTimer = setTimeout(function () { G.confirmResign = false; if (G.view === "room") draw(); }, 3500);
      draw();
      return;
    }
    G.confirmResign = false;
    act("resign");
  }

  function drawActions(room) {
    var row = h("div", { class: "game-actions" });
    var seated = room.you === "w" || room.you === "b";
    if (room.status === "waiting" && !seated && (!room.players.w || !room.players.b)) {
      row.appendChild(h("button", { class: "btn", type: "button", onclick: function () { act("join"); } }, "Join this game"));
    }
    if (room.status === "playing" && seated) {
      if (room.drawOffer && room.drawOffer !== room.you) {
        row.appendChild(h("button", { class: "btn", type: "button", onclick: function () { act("draw", { action: "accept" }); } }, "Accept draw"));
        row.appendChild(h("button", { class: "btn ghost", type: "button", onclick: function () { act("draw", { action: "decline" }); } }, "Decline"));
      } else {
        row.appendChild(h("button", { class: "btn ghost", type: "button", disabled: room.drawOffer === room.you, onclick: function () { act("draw", { action: "offer" }); } }, room.drawOffer === room.you ? "Draw offered" : "Offer draw"));
      }
      row.appendChild(h("button", { class: "btn danger", type: "button", onclick: resign }, G.confirmResign ? "Tap again to resign" : "Resign"));
    }
    if (room.status === "finished" && seated) {
      var label = room.rematch === room.you ? "Waiting for rematch…" : room.rematch ? "Accept rematch" : "Rematch";
      row.appendChild(h("button", { class: "btn", type: "button", disabled: room.rematch === room.you, onclick: function () { act("rematch"); } }, label));
    }
    if (room.status !== "playing" && (seated || room.host === G.ctx.user.id)) {
      row.appendChild(h("button", { class: "btn ghost", type: "button", onclick: function () { act("close"); } }, "Close room"));
    }
    row.appendChild(h("button", { class: "btn ghost", type: "button", onclick: function () { G.flipped = !(G.flipped === null ? room.you === "b" : G.flipped); draw(); } }, "Flip board"));
    return row;
  }

  function drawRoom() {
    var room = G.room;
    var box = h("div", { class: "games room-view" });
    box.appendChild(h("div", { class: "section-head" },
      h("button", { class: "btn ghost", type: "button", onclick: leave }, "← Lobby"),
      h("h2", { text: "Chess" })));
    if (!room) { box.appendChild(h("p", { class: "muted", text: "Loading…" })); return box; }
    var flipped = G.flipped === null ? room.you === "b" : G.flipped;
    var top = flipped ? "w" : "b";
    var bottom = flipped ? "b" : "w";
    var mat = material(room.board);
    box.appendChild(playerBar(room, top, mat));
    box.appendChild(drawBoard(room));
    box.appendChild(playerBar(room, bottom, mat));
    box.appendChild(h("div", { class: "game-status" + (room.status === "finished" ? " done" : ""), text: statusText(room) }));
    box.appendChild(drawActions(room));
    box.appendChild(movesList(room));
    return box;
  }

  function draw() {
    if (!G.root || G.view === "doom") return;
    var scroll = G.root.parentNode ? G.root.parentNode.scrollTop : 0;
    G.root.textContent = "";
    G.root.appendChild(G.view === "room" ? drawRoom() : drawLobby());
    if (G.root.parentNode) G.root.parentNode.scrollTop = scroll;
  }

  window.SowardGames = {
    mount: function (root, ctx) {
      G.root = root;
      G.ctx = ctx;
      if (G.view === "doom" && !(window.SowardDoom && window.SowardDoom.attach(root, ctx))) G.view = "lobby";
      draw();
      startPolling();
      setTimeout(function () {
        if (G.view === "room" && G.room) poll(); else refreshRooms();
        updatePresence();
      }, 60);
    },
    suspend: function () {
      stopPolling();
      if (window.SowardDoom) window.SowardDoom.stop();
      if (G.view === "doom") G.view = "lobby";
      G.root = null;
      if (G.ctx && G.ctx.setPresence) G.ctx.setPresence(null);
    }
  };
})();
