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
        });
    });
    dlg.showModal();
  }

  function actionButton(def, rowCtx) {
    var cls = def.style === "danger" ? "btn btn--danger btn--sm" : def.style === "primary" ? "btn btn--primary btn--sm" : "btn btn--ghost btn--sm";
    var b = el("button", cls, def.label);
    b.type = "button";
    b.addEventListener("click", function () { dialog(def, rowCtx); });
    return b;
  }

  function render() {
    mount.textContent = "";
    sections.forEach(function (sec) {
      var panel = el("section", "panel");
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
          r.cells.forEach(function (c) { tr.appendChild(el("td", "", c)); });
          var cell = el("td", "rowtools");
          r.actions.forEach(function (a) { cell.appendChild(actionButton(a, r)); });
          tr.appendChild(cell);
          body.appendChild(tr);
        });
        tbl.appendChild(body);
        wrap.appendChild(tbl);
        panel.appendChild(wrap);
      }
      mount.appendChild(panel);
    });
  }

  render();
})();
