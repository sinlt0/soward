(function () {
  var explorer = document.getElementById("explorer");
  if (explorer) {
    var tabs = explorer.querySelectorAll("[data-tab]");
    var panes = explorer.querySelectorAll("[data-pane]");
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        var index = tab.getAttribute("data-tab");
        tabs.forEach(function (t) {
          t.setAttribute("aria-selected", t === tab ? "true" : "false");
        });
        panes.forEach(function (p) {
          p.setAttribute("data-active", p.getAttribute("data-pane") === index ? "true" : "false");
        });
      });
    });
  }

  var feed = document.getElementById("demo-feed");
  var open = document.getElementById("demo-open");
  if (!feed || !open) return;

  var avatar = feed.querySelector(".dc__pfp");
  var avatarStyle = avatar ? avatar.getAttribute("style") || "" : "";
  var botName = feed.querySelector(".dc__name").firstChild.textContent;

  function node(tag, className, text) {
    var el = document.createElement(tag);
    if (className) el.className = className;
    if (text) el.textContent = text;
    return el;
  }

  function message(name, tag, build) {
    var row = node("div", "dc__msg");
    var pfp = node("div", "dc__pfp");
    if (tag) pfp.setAttribute("style", avatarStyle);
    var body = node("div");
    var who = node("div", "dc__name", name);
    if (tag) who.appendChild(node("span", "dc__tag", "APP"));
    body.appendChild(who);
    build(body);
    row.appendChild(pfp);
    row.appendChild(body);
    feed.appendChild(row);
  }

  function card(parent, title, text, kind) {
    var c = node("div", "dc__card" + (kind ? " dc__card--" + kind : ""));
    c.appendChild(node("div", "dc__title", title));
    c.appendChild(node("div", "dc__text", text));
    parent.appendChild(c);
    return c;
  }

  function buttons(parent, defs) {
    parent.appendChild(node("div", "dc__sep"));
    var row = node("div", "dc__row");
    defs.forEach(function (d) {
      var b = node("button", "dc__btn dc__btn--" + d.color, d.label);
      b.type = "button";
      b.addEventListener("click", function () {
        d.run(b);
      });
      row.appendChild(b);
    });
    parent.appendChild(row);
  }

  open.addEventListener("click", function () {
    open.disabled = true;
    message("You", false, function (body) {
      body.appendChild(node("div", "dc__text", "Pressed Open a ticket"));
    });
    setTimeout(function () {
      message(botName, true, function (body) {
        var c = card(body, "Ticket #0042", "Welcome. Staff have been pinged and will reply here. Tell us what you need.");
        var claim = null;
        buttons(c, [
          {
            color: "blue",
            label: "Claim",
            run: function (b) {
              b.disabled = true;
              b.textContent = "Claimed by Staff";
              message(botName, true, function (inner) {
                card(inner, "Ticket claimed", "A staff member is now handling this ticket.", "ok");
              });
              claim = b;
            },
          },
          {
            color: "red",
            label: "Close",
            run: function (b) {
              b.disabled = true;
              if (claim) claim.disabled = true;
              message(botName, true, function (inner) {
                card(inner, "Ticket closed", "A transcript was saved to the log channel and sent to you by DM. This channel will be deleted.", "bad");
              });
            },
          },
        ]);
      });
    }, 450);
  });
})();
