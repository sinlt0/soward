(function () {
  var root = document.getElementById("dash");
  if (!root) return;
  var gid = root.getAttribute("data-gid");
  var csrf = document.body.getAttribute("data-csrf") || "";

  function send(url, payload) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify(payload),
    }).then(function (res) {
      return res
        .json()
        .catch(function () {
          return {};
        })
        .then(function (data) {
          if (!res.ok) throw new Error(data.error || "Request failed.");
          return data;
        });
    });
  }

  function fail(err) {
    window.toast(err && err.message ? err.message : "Something went wrong.", true);
  }

  var store = {
    get: function (name, fallback) {
      try {
        var raw = window.localStorage.getItem(name);
        return raw === null ? fallback : JSON.parse(raw);
      } catch (e) {
        return fallback;
      }
    },
    set: function (name, value) {
      try {
        window.localStorage.setItem(name, JSON.stringify(value));
      } catch (e) {
        return;
      }
    },
  };

  var sideToggle = document.getElementById("dside-toggle");
  var sideBox = document.getElementById("dside");
  if (sideToggle && sideBox) {
    sideToggle.addEventListener("click", function () {
      var open = sideBox.getAttribute("data-open") === "true";
      sideBox.setAttribute("data-open", open ? "false" : "true");
      sideToggle.setAttribute("aria-expanded", open ? "false" : "true");
    });
  }

  var sideFilter = document.getElementById("side-filter");
  if (sideFilter) {
    sideFilter.addEventListener("input", function () {
      var q = sideFilter.value.trim().toLowerCase();
      document.querySelectorAll(".dside__group").forEach(function (group) {
        var shown = 0;
        group.querySelectorAll("a").forEach(function (a) {
          var match = !q || a.getAttribute("data-name").indexOf(q) !== -1;
          a.hidden = !match;
          if (match) shown += 1;
        });
        group.hidden = shown === 0;
      });
    });
  }

  function syncModuleState(key, enabled) {
    document.querySelectorAll('[data-dot-for="' + key + '"]').forEach(function (dot) {
      dot.className = "dot-s " + (enabled ? "is-on" : "is-off");
    });
    var card = document.querySelector('.mod[data-key="' + key + '"]');
    if (card) card.setAttribute("data-state", enabled ? "on" : "off");
    var stat = document.getElementById("stat-on");
    if (stat) {
      var total = document.querySelectorAll(".mod[data-state='on'], .mod[data-state='off']").length;
      var on = document.querySelectorAll(".mod[data-state='on']").length;
      stat.innerHTML = on + "<small> / " + total + "</small>";
    }
  }

  var prefix = document.getElementById("prefix");
  var prefixSave = document.getElementById("prefix-save");
  if (prefix && prefixSave) {
    prefixSave.addEventListener("click", function () {
      prefixSave.disabled = true;
      send("/api/g/" + gid + "/settings", { prefix: prefix.value })
        .then(function (data) {
          window.toast(data.changes.length ? "Prefix saved." : "Prefix unchanged.");
        })
        .catch(fail)
        .then(function () {
          prefixSave.disabled = false;
        });
    });
  }

  document.querySelectorAll("[data-setting]").forEach(function (box) {
    box.addEventListener("change", function () {
      var body = {};
      body[box.getAttribute("data-setting")] = box.checked;
      send("/api/g/" + gid + "/settings", body)
        .then(function () {
          window.toast("Saved.");
        })
        .catch(function (err) {
          box.checked = !box.checked;
          fail(err);
        });
    });
  });

  document.querySelectorAll("[data-module]").forEach(function (box) {
    box.addEventListener("change", function () {
      var key = box.getAttribute("data-module");
      var label = document.querySelector('[data-state-for="' + key + '"]');
      send("/api/g/" + gid + "/m/" + key + "/toggle", { enabled: box.checked })
        .then(function (data) {
          if (label) label.textContent = data.enabled ? "On" : "Off";
          syncModuleState(key, data.enabled);
          apply && apply();
          window.toast(data.enabled ? "Module enabled." : "Module disabled.");
        })
        .catch(function (err) {
          box.checked = !box.checked;
          fail(err);
        });
    });
  });

  var search = document.getElementById("mod-search");
  var chips = document.querySelectorAll("#chips .chip");
  var segs = document.querySelectorAll("#seg button");
  var pins = store.get("soward-pins-" + gid, []);
  var apply = null;
  if (search) {
    var active = "";
    var status = "";
    var groups = document.querySelectorAll(".modgroup");
    var empty = document.getElementById("mod-empty");

    var paintPins = function () {
      document.querySelectorAll(".pin").forEach(function (pin) {
        var on = pins.indexOf(pin.getAttribute("data-pin")) !== -1;
        pin.setAttribute("aria-pressed", on ? "true" : "false");
        pin.closest(".mod").classList.toggle("is-pinned", on);
      });
    };

    apply = function () {
      var q = search.value.trim().toLowerCase();
      var any = false;
      groups.forEach(function (group) {
        var shown = 0;
        group.querySelectorAll(".mod").forEach(function (card) {
          var state = card.getAttribute("data-state");
          var pinned = pins.indexOf(card.getAttribute("data-key")) !== -1;
          var okStatus = !status || (status === "pinned" ? pinned : status === state);
          var match =
            (!q || card.getAttribute("data-search").indexOf(q) !== -1) &&
            (!active || group.getAttribute("data-group") === active) &&
            okStatus;
          card.hidden = !match;
          if (match) shown += 1;
        });
        group.hidden = shown === 0;
        if (shown) any = true;
      });
      if (empty) empty.hidden = any;
    };

    search.addEventListener("input", apply);
    chips.forEach(function (chip) {
      chip.addEventListener("click", function () {
        active = chip.getAttribute("data-cat");
        chips.forEach(function (c) {
          c.setAttribute("aria-pressed", c === chip ? "true" : "false");
        });
        apply();
      });
    });
    segs.forEach(function (seg) {
      seg.addEventListener("click", function () {
        status = seg.getAttribute("data-status");
        segs.forEach(function (s) {
          s.setAttribute("aria-pressed", s === seg ? "true" : "false");
        });
        apply();
      });
    });
    document.querySelectorAll(".pin").forEach(function (pin) {
      pin.addEventListener("click", function () {
        var k = pin.getAttribute("data-pin");
        var at = pins.indexOf(k);
        if (at === -1) pins.push(k);
        else pins.splice(at, 1);
        store.set("soward-pins-" + gid, pins);
        paintPins();
        window.toast(at === -1 ? "Pinned. Use the Pinned filter to see your favorites." : "Unpinned.");
        apply();
      });
    });
    paintPins();
  }

  var key = root.getAttribute("data-key");
  if (!key) return;

  var toggle = document.getElementById("mod-toggle");
  var state = document.getElementById("mod-state");
  if (toggle) {
    toggle.addEventListener("change", function () {
      send("/api/g/" + gid + "/m/" + key + "/toggle", { enabled: toggle.checked })
        .then(function (data) {
          if (state) state.textContent = data.enabled ? "Enabled" : "Disabled";
          syncModuleState(key, data.enabled);
          window.toast(data.enabled ? "Module enabled." : "Module disabled.");
        })
        .catch(function (err) {
          toggle.checked = !toggle.checked;
          fail(err);
        });
    });
  }

  var bar = document.getElementById("savebar");
  var saveBtn = document.getElementById("save");
  var discard = document.getElementById("discard");
  var inputs = root.querySelectorAll("[data-field]");
  if (!bar || !saveBtn) return;

  function read(el) {
    var kind = el.getAttribute("data-kind");
    if (kind === "bool") return el.checked;
    if (kind === "roles") {
      return Array.prototype.map.call(el.querySelectorAll("input:checked"), function (i) {
        return i.value;
      });
    }
    if (kind === "lines") {
      return el.value
        .split("\n")
        .map(function (s) {
          return s.trim();
        })
        .filter(Boolean);
    }
    return el.value;
  }

  function write(el, value) {
    var kind = el.getAttribute("data-kind");
    if (kind === "bool") el.checked = value;
    else if (kind === "roles") {
      el.querySelectorAll("input").forEach(function (i) {
        i.checked = value.indexOf(i.value) !== -1;
      });
    } else if (kind === "lines") el.value = value.join("\n");
    else el.value = value;
  }

  var baseline = {};
  function snapshot() {
    inputs.forEach(function (el) {
      baseline[el.getAttribute("data-field")] = read(el);
    });
  }
  snapshot();

  function dirty() {
    return Array.prototype.some.call(inputs, function (el) {
      return JSON.stringify(read(el)) !== JSON.stringify(baseline[el.getAttribute("data-field")]);
    });
  }

  function refresh() {
    bar.hidden = !dirty();
  }

  inputs.forEach(function (el) {
    el.addEventListener("input", refresh);
    el.addEventListener("change", refresh);
  });

  discard.addEventListener("click", function () {
    inputs.forEach(function (el) {
      write(el, baseline[el.getAttribute("data-field")]);
    });
    refresh();
  });

  saveBtn.addEventListener("click", function () {
    var values = {};
    inputs.forEach(function (el) {
      values[el.getAttribute("data-field")] = read(el);
    });
    saveBtn.disabled = true;
    send("/api/g/" + gid + "/m/" + key, { values: values })
      .then(function (data) {
        snapshot();
        refresh();
        window.toast(data.changes.length ? "Saved " + data.changes.length + " change(s)." : "Nothing changed.");
      })
      .catch(fail)
      .then(function () {
        saveBtn.disabled = false;
      });
  });

  window.addEventListener("beforeunload", function (event) {
    if (dirty()) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
})();
