(function () {
  var root = document.getElementById("dash");
  var mount = document.getElementById("sections");
  var dataEl = document.getElementById("module-data");
  if (!root || !mount || !dataEl) return;

  var gid = root.getAttribute("data-gid");
  var key = root.getAttribute("data-key");
  var csrf = document.body.getAttribute("data-csrf") || "";
  var data = JSON.parse(dataEl.textContent);
  var sections = data.sections || [];

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function send(payload) {
    return fetch("/api/g/" + gid + "/m/" + key + "/action", {
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
        .then(function (body) {
          if (!res.ok) throw new Error(body.error || "Request failed.");
          return body;
        });
    });
  }

  function select(options, current, blank) {
    var node = el("select", "select");
    if (blank) {
      var none = el("option", "", "None");
      none.value = "";
      node.appendChild(none);
    }
    options.forEach(function (o) {
      var opt = el("option", "", o.label);
      opt.value = o.value;
      if (String(o.value) === String(current)) opt.selected = true;
      node.appendChild(opt);
    });
    return node;
  }

  function checklist(items, current, label) {
    var box = el("div", "rolebox");
    var chosen = (current || []).map(String);
    items.forEach(function (item) {
      var row = el("label");
      var input = el("input");
      input.type = "checkbox";
      input.value = item.id;
      input.checked = chosen.indexOf(item.id) !== -1;
      row.appendChild(input);
      var dot = el("i");
      if (item.color) dot.style.background = item.color;
      row.appendChild(dot);
      row.appendChild(document.createTextNode(label(item)));
      box.appendChild(row);
    });
    if (!items.length) box.appendChild(el("span", "setting__help", "Nothing to choose from."));
    return box;
  }

  function control(field, value) {
    var kind = field.kind;
    var node;
    if (kind === "bool") {
      var wrap = el("label", "switch");
      node = el("input");
      node.type = "checkbox";
      node.checked = !!value;
      wrap.appendChild(node);
      wrap.appendChild(el("span", "switch__track"));
      return { root: wrap, read: function () { return node.checked; } };
    }
    if (kind === "textarea" || kind === "lines") {
      node = el("textarea", "textarea");
      node.value = kind === "lines" ? (value || []).join("\n") : value || "";
      if (field.placeholder) node.placeholder = field.placeholder;
      return {
        root: node,
        read: function () {
          if (kind === "lines") {
            return node.value
              .split("\n")
              .map(function (s) { return s.trim(); })
              .filter(Boolean);
          }
          return node.value;
        },
      };
    }
    if (kind === "int") {
      node = el("input", "input input--short");
      node.type = "number";
      node.step = "any";
      if (field.min !== null) node.min = field.min;
      if (field.max !== null) node.max = field.max;
      node.value = value === null || value === undefined ? "" : value;
      return { root: node, read: function () { return node.value; } };
    }
    if (kind === "select") {
      node = select(field.options, value, false);
      return { root: node, read: function () { return node.value; } };
    }
    if (kind === "channel") {
      node = select(data.channels.map(function (c) { return { value: c.id, label: "#" + c.name }; }), value, true);
      return { root: node, read: function () { return node.value; } };
    }
    if (kind === "voice") {
      node = select((data.voices || []).map(function (c) { return { value: c.id, label: c.name }; }), value, true);
      return { root: node, read: function () { return node.value; } };
    }
    if (kind === "role") {
      node = select(data.roles.map(function (r) { return { value: r.id, label: "@" + r.name }; }), value, true);
      return { root: node, read: function () { return node.value; } };
    }
    if (kind === "roles" || kind === "categories") {
      var items = kind === "roles" ? data.roles : data.categories;
      node = checklist(items, value, function (item) { return item.name; });
      return {
        root: node,
        read: function () {
          return Array.prototype.map.call(node.querySelectorAll("input:checked"), function (i) { return i.value; });
        },
      };
    }
    node = el("input", "input");
    node.type = "text";
    node.value = value || "";
    if (field.maxlen) node.maxLength = field.maxlen;
    if (field.placeholder) node.placeholder = field.placeholder;
    return { root: node, read: function () { return node.value; } };
  }

  function dialog(def, rowCtx) {
    var dlg = el("dialog", "dlg");
    var form = el("form", "dlg__form");
    form.method = "dialog";
    form.appendChild(el("h2", "", def.title));
    var error = el("div", "dlg__error");
    error.hidden = true;
    var controls = [];

    if (def.confirm) form.appendChild(el("p", "setting__help", def.confirm));

    (def.fields || []).forEach(function (field) {
      var seed = def.prefill && rowCtx && rowCtx.values ? rowCtx.values[field.key] : field.value;
      var built = control(field, seed);
      var block = el("div", "dlg__field");
      block.appendChild(el("div", "setting__label", field.label));
      if (field.help) block.appendChild(el("div", "setting__help", field.help));
      block.appendChild(built.root);
      form.appendChild(block);
      controls.push({ key: field.key, read: built.read });
    });

    form.appendChild(error);
    var bar = el("div", "dlg__bar");
    var cancel = el("button", "btn btn--ghost btn--sm", "Cancel");
    cancel.type = "button";
    var submit = el("button", "btn btn--sm " + (def.style === "danger" ? "btn--danger" : "btn--primary"), def.submit);
    submit.type = "submit";
    bar.appendChild(cancel);
    bar.appendChild(submit);
    form.appendChild(bar);
    dlg.appendChild(form);
    document.body.appendChild(dlg);

    cancel.addEventListener("click", function () { dlg.close(); });
    dlg.addEventListener("close", function () { dlg.remove(); });
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var values = {};
      controls.forEach(function (c) { values[c.key] = c.read(); });
      submit.disabled = true;
      submit.classList.add("is-loading");
      error.hidden = true;
      send({ action: def.name, id: rowCtx ? rowCtx.id : null, values: values })
        .then(function (body) {
          sections = body.sections || sections;
          render();
          window.toast(body.changes && body.changes.length ? body.changes[0] : "Done.");
          dlg.close();
        })
        .catch(function (err) {
          error.textContent = err.message;
          error.hidden = false;
          submit.disabled = false;
          submit.classList.remove("is-loading");
        });
    });
    dlg.addEventListener("click", function (event) {
      if (event.target === dlg) dlg.close();
    });
    dlg.showModal();
    var first = form.querySelector("input, select, textarea");
    if (first) first.focus();
  }

  function actionButton(def, rowCtx) {
    var cls = def.style === "danger" ? "btn btn--danger btn--sm" : def.style === "primary" ? "btn btn--primary btn--sm" : "btn btn--ghost btn--sm";
    var b = el("button", cls, def.label);
    b.type = "button";
    b.addEventListener("click", function () { dialog(def, rowCtx); });
    return b;
  }

  function tableTools(panel, tbl, rows) {
    var tools = el("div", "tabletools");
    var input = el("input", "input tabletools__search");
    input.type = "search";
    input.placeholder = "Filter this list";
    input.setAttribute("aria-label", "Filter this list");
    var count = el("span", "tabletools__count", rows.length + " item" + (rows.length === 1 ? "" : "s"));
    tools.appendChild(input);
    tools.appendChild(count);
    input.addEventListener("input", function () {
      var q = input.value.trim().toLowerCase();
      var shown = 0;
      Array.prototype.forEach.call(tbl.tBodies[0].rows, function (tr) {
        var match = !q || tr.textContent.toLowerCase().indexOf(q) !== -1;
        tr.hidden = !match;
        if (match) shown += 1;
      });
      count.textContent = shown + " of " + rows.length;
    });
    panel.appendChild(tools);
  }

  function sortable(tbl) {
    var heads = tbl.tHead.rows[0].cells;
    Array.prototype.forEach.call(heads, function (th, index) {
      if (index === heads.length - 1) return;
      th.classList.add("sortable");
      th.tabIndex = 0;
      var run = function () {
        var asc = th.getAttribute("data-sort") !== "asc";
        Array.prototype.forEach.call(heads, function (h) {
          h.removeAttribute("data-sort");
        });
        th.setAttribute("data-sort", asc ? "asc" : "desc");
        var rows = Array.prototype.slice.call(tbl.tBodies[0].rows);
        rows.sort(function (a, b) {
          var x = a.cells[index].textContent.trim();
          var y = b.cells[index].textContent.trim();
          var nx = parseFloat(x.replace(/,/g, ""));
          var ny = parseFloat(y.replace(/,/g, ""));
          var cmp = !isNaN(nx) && !isNaN(ny) ? nx - ny : x.localeCompare(y, undefined, { numeric: true, sensitivity: "base" });
          return asc ? cmp : -cmp;
        });
        rows.forEach(function (tr) {
          tbl.tBodies[0].appendChild(tr);
        });
      };
      th.addEventListener("click", run);
      th.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          run();
        }
      });
    });
  }

  var activePane = "";

  function setupTabs() {
    var bar = document.getElementById("tabs");
    if (!bar) return;
    var panes = Array.prototype.slice.call(root.querySelectorAll("[data-pane]"));
    bar.textContent = "";
    if (panes.length < 2) {
      bar.hidden = true;
      panes.forEach(function (p) { p.hidden = false; });
      return;
    }
    var wanted = decodeURIComponent((location.hash || "").replace("#tab-", ""));
    var ids = panes.map(function (p) { return p.getAttribute("data-pane"); });
    if (ids.indexOf(activePane) === -1) activePane = ids.indexOf(wanted) !== -1 ? wanted : ids[0];
    var show = function (id) {
      activePane = id;
      panes.forEach(function (p) { p.hidden = p.getAttribute("data-pane") !== id; });
      Array.prototype.forEach.call(bar.children, function (b) {
        b.setAttribute("aria-selected", b.getAttribute("data-tab") === id ? "true" : "false");
      });
      history.replaceState(null, "", "#tab-" + encodeURIComponent(id));
    };
    panes.forEach(function (p) {
      var id = p.getAttribute("data-pane");
      var b = el("button", "tab", p.getAttribute("data-title"));
      b.type = "button";
      b.setAttribute("role", "tab");
      b.setAttribute("data-tab", id);
      var n = p.getAttribute("data-count");
      if (n !== null) b.appendChild(el("small", "", n));
      b.addEventListener("click", function () { show(id); });
      bar.appendChild(b);
    });
    bar.hidden = false;
    show(activePane);
  }

  function render() {
    mount.textContent = "";
    sections.forEach(function (sec) {
      var panel = el("section", "panel pane");
      panel.setAttribute("data-pane", sec.key);
      panel.setAttribute("data-title", sec.title.replace(/\s*\(.*\)$/, ""));
      panel.setAttribute("data-count", String(sec.rows.length));
      var head = el("div", "panel__head panel__head--row");
      var titles = el("div");
      titles.appendChild(el("h2", "", sec.title));
      if (sec.description) titles.appendChild(el("p", "", sec.description));
      head.appendChild(titles);
      var tools = el("div", "panel__tools");
      sec.buttons.forEach(function (b) { tools.appendChild(actionButton(b, null)); });
      head.appendChild(tools);
      panel.appendChild(head);

      if (!sec.rows.length) {
        panel.appendChild(el("div", "empty empty--inset", sec.empty));
      } else {
        var wrap = el("div", "tablewrap");
        var tbl = el("table", "table");
        var thead = el("thead");
        var hr = el("tr");
        sec.columns.forEach(function (c) { hr.appendChild(el("th", "", c)); });
        hr.appendChild(el("th", "", ""));
        thead.appendChild(hr);
        tbl.appendChild(thead);
        var body = el("tbody");
        sec.rows.forEach(function (r) {
          var tr = el("tr");
          r.cells.forEach(function (c, i) {
            var td = el("td", "", c);
            td.setAttribute("data-label", sec.columns[i] || "");
            tr.appendChild(td);
          });
          var cell = el("td", "rowtools");
          r.actions.forEach(function (a) { cell.appendChild(actionButton(a, r)); });
          tr.appendChild(cell);
          body.appendChild(tr);
        });
        tbl.appendChild(body);
        if (sec.rows.length > 6) tableTools(panel, tbl, sec.rows);
        wrap.appendChild(tbl);
        panel.appendChild(wrap);
        sortable(tbl);
      }
      mount.appendChild(panel);
    });
    setupTabs();
  }

  render();
})();
