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
  if (search) {
    var active = "";
    var groups = document.querySelectorAll(".modgroup");
    var empty = document.getElementById("mod-empty");

    function apply() {
      var q = search.value.trim().toLowerCase();
      var any = false;
      groups.forEach(function (group) {
        var shown = 0;
        group.querySelectorAll(".mod").forEach(function (card) {
          var match =
            (!q || card.getAttribute("data-search").indexOf(q) !== -1) &&
            (!active || group.getAttribute("data-group") === active);
          card.hidden = !match;
          if (match) shown += 1;
        });
        group.hidden = shown === 0;
        if (shown) any = true;
      });
      if (empty) empty.hidden = any;
    }

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
