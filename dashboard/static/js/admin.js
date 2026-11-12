(function () {
  var csrf = document.body.getAttribute("data-csrf") || "";

  function send(path, payload, timeoutLong) {
    return fetch("/api/admin/" + path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify(payload || {}),
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

  function readFile(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () {
        resolve(String(reader.result));
      };
      reader.onerror = function () {
        reject(new Error("That file could not be read."));
      };
      reader.readAsDataURL(file);
    });
  }

  function collect(form) {
    var body = {};
    var jobs = [];
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!el.name || el.disabled) return;
      if (el.type === "checkbox") body[el.name] = el.checked;
      else if (el.type === "file") {
        if (el.files && el.files[0]) {
          if (el.files[0].size > 8 * 1024 * 1024) throw new Error("Images must be 8 MB or smaller.");
          jobs.push(
            readFile(el.files[0]).then(function (data) {
              body[el.name] = data;
            })
          );
        }
      } else if (el.type === "number") body[el.name] = el.value === "" ? "" : Number(el.value);
      else body[el.name] = el.value;
    });
    var rows = form.querySelectorAll("[data-item-row]");
    if (rows.length || form.querySelector(".itemlist")) {
      body.items = [];
      Array.prototype.forEach.call(rows, function (row) {
        var kind = row.querySelector("[data-f=kind]").value;
        var text = row.querySelector("[data-f=text]").value.trim();
        if (text) body.items.push({ kind: kind, text: text });
      });
    }
    return Promise.all(jobs).then(function () {
      return body;
    });
  }

  function extra(el) {
    var raw = el.getAttribute("data-body");
    if (!raw) return {};
    try {
      return JSON.parse(raw);
    } catch (e) {
      return {};
    }
  }

  function finish(el, data) {
    window.toast(data.message || "Done.");
    var target = el.getAttribute("data-result");
    if (target) {
      var box = document.getElementById(target);
      if (box) {
        var text = data.url || (data.keys ? data.keys.join("\n") : "");
        if (text) {
          box.textContent = text;
          box.hidden = false;
        }
      }
    }
    var redirect = el.getAttribute("data-redirect");
    if (redirect) {
      setTimeout(function () {
        window.location.href = redirect;
      }, 700);
    } else if (el.hasAttribute("data-reload") && !target) {
      setTimeout(function () {
        window.location.reload();
      }, 700);
    } else if (el.hasAttribute("data-reload") && target && data.keys) {
      return;
    }
  }

  function run(el, path, bodyPromise) {
    if (el.getAttribute("data-confirm") && !window.confirm(el.getAttribute("data-confirm"))) return;
    var button = el.tagName === "FORM" ? el.querySelector("button[type=submit]") : el;
    if (button) button.classList.add("is-loading");
    Promise.resolve(bodyPromise)
      .then(function (body) {
        return send(path, Object.assign({}, extra(el), body));
      })
      .then(function (data) {
        finish(el, data);
      })
      .catch(fail)
      .then(function () {
        if (button) button.classList.remove("is-loading");
      });
  }

  document.addEventListener("submit", function (event) {
    var form = event.target.closest("form[data-admin]");
    if (!form) return;
    event.preventDefault();
    var path = form.getAttribute("data-admin");
    var bodyPromise;
    try {
      bodyPromise = collect(form);
    } catch (err) {
      return fail(err);
    }
    var idField = form.getAttribute("data-id-field");
    if (idField) {
      bodyPromise = bodyPromise.then(function (body) {
        var id = String(body[idField] || "").trim();
        if (!/^\d{5,25}$/.test(id)) throw new Error("Enter a valid server ID.");
        delete body[idField];
        path = path.replace("/0/", "/" + id + "/");
        return body;
      });
    }
    run(form, path, bodyPromise);
  });

  document.addEventListener("click", function (event) {
    var button = event.target.closest("button[data-admin]");
    if (button && button.tagName === "BUTTON" && !button.closest("form[data-admin]")) {
      run(button, button.getAttribute("data-admin"), {});
      return;
    }
    var standalone = event.target.closest("button[data-admin]");
    if (standalone && standalone.closest("form[data-admin]") && standalone.type === "button") {
      run(standalone, standalone.getAttribute("data-admin"), {});
      return;
    }
    var add = event.target.closest("[data-add-item]");
    if (add) {
      var list = document.getElementById(add.getAttribute("data-add-item"));
      var rows = list.querySelectorAll("[data-item-row]");
      if (rows.length >= Number(list.getAttribute("data-max") || 10)) return window.toast("That is the maximum number of activities.", true);
      var clone = rows[0].cloneNode(true);
      clone.querySelector("[data-f=text]").value = "";
      list.appendChild(clone);
      return;
    }
    var remove = event.target.closest("[data-remove-item]");
    if (remove) {
      var row = remove.closest("[data-item-row]");
      var parent = row.parentNode;
      if (parent.querySelectorAll("[data-item-row]").length > 1) row.remove();
      else row.querySelector("[data-f=text]").value = "";
      return;
    }
    var copy = event.target.closest("[data-copy]");
    if (copy && navigator.clipboard) {
      navigator.clipboard.writeText(copy.getAttribute("data-copy")).then(function () {
        window.toast("Copied.");
      });
    }
  });

  document.addEventListener("change", function (event) {
    var input = event.target;
    if (!input.matches || !input.matches("input[type=file][data-preview]") || !input.files[0]) return;
    var target = document.getElementById(input.getAttribute("data-preview"));
    if (!target) return;
    var url = URL.createObjectURL(input.files[0]);
    if (target.tagName === "IMG") target.src = url;
    else target.style.backgroundImage = "url('" + url + "')";
  });

  function syncMode(select) {
    var form = select.closest("form");
    var mode = select.value;
    var panel = document.getElementById(select.getAttribute("data-mode-toggle"));
    if (panel) panel.hidden = mode !== "custom";
    Array.prototype.forEach.call(form.querySelectorAll("[data-mode-hint]"), function (el) {
      el.hidden = el.getAttribute("data-mode-hint") !== mode;
    });
  }
  document.addEventListener("change", function (event) {
    if (event.target.matches && event.target.matches("select[data-mode-toggle]")) syncMode(event.target);
  });

  var logs = document.getElementById("logs-load");
  if (logs) {
    logs.addEventListener("click", function () {
      var box = document.getElementById("logbox");
      logs.classList.add("is-loading");
      fetch("/api/admin/logs?lines=300", { credentials: "same-origin" })
        .then(function (res) {
          return res.json().then(function (data) {
            if (!res.ok) throw new Error(data.error || "Could not load logs.");
            return data;
          });
        })
        .then(function (data) {
          box.textContent = data.text || "The log file is empty.";
          box.hidden = false;
          box.scrollTop = box.scrollHeight;
        })
        .catch(fail)
        .then(function () {
          logs.classList.remove("is-loading");
        });
    });
  }
})();
