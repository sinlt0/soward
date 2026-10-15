(function () {
  var input = document.getElementById("cmd-search");
  var list = document.getElementById("cmdlist");
  if (!input || !list) return;
  var empty = document.getElementById("cmd-empty");
  var status = document.getElementById("cmd-status");
  var tabs = Array.prototype.slice.call(document.querySelectorAll("#cmdnav [data-cat]"));
  var sections = Array.prototype.slice.call(list.querySelectorAll(".cmdcat"));
  var current = "";

  function pick() {
    var hash = decodeURIComponent((location.hash || "").replace("#", ""));
    var found = tabs.filter(function (t) {
      return t.getAttribute("data-cat") === hash;
    })[0];
    return found ? hash : tabs[0].getAttribute("data-cat");
  }

  function render() {
    var q = input.value.trim().toLowerCase();
    var shownTotal = 0;
    var counts = {};
    sections.forEach(function (section) {
      var cat = section.getAttribute("data-cat");
      var shown = 0;
      section.querySelectorAll(".cmd").forEach(function (cmd) {
        var match = !q || cmd.getAttribute("data-search").indexOf(q) !== -1;
        cmd.hidden = !match;
        if (match) shown += 1;
      });
      counts[cat] = shown;
      var visible = q ? shown > 0 : current === "all" || current === cat;
      section.hidden = !visible || shown === 0;
      if (!section.hidden) shownTotal += shown;
    });
    tabs.forEach(function (tab) {
      var cat = tab.getAttribute("data-cat");
      var count = cat === "all" ? Object.keys(counts).reduce(function (n, k) { return n + counts[k]; }, 0) : counts[cat];
      tab.querySelector("small").textContent = count;
      tab.setAttribute("aria-selected", !q && cat === current ? "true" : "false");
      tab.classList.toggle("is-dim", !!q && count === 0);
    });
    if (empty) empty.hidden = shownTotal > 0;
    if (status) {
      status.textContent = q
        ? shownTotal + " result" + (shownTotal === 1 ? "" : "s") + " for “" + input.value.trim() + "”"
        : shownTotal + " command" + (shownTotal === 1 ? "" : "s") + (current === "all" ? " in every category" : "");
    }
  }

  function select(cat, push) {
    current = cat;
    if (push) history.replaceState(null, "", "#" + cat);
    render();
  }

  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      input.value = "";
      select(tab.getAttribute("data-cat"), true);
      window.scrollTo({ top: Math.min(window.scrollY, document.querySelector(".cmdpage").offsetTop - 70), behavior: "smooth" });
    });
  });

  input.addEventListener("input", render);
  window.addEventListener("hashchange", function () {
    input.value = "";
    select(pick(), false);
  });

  document.getElementById("cmd-expand").addEventListener("click", function () {
    list.querySelectorAll(".cmd:not([hidden])").forEach(function (d) {
      d.open = true;
    });
  });
  document.getElementById("cmd-collapse").addEventListener("click", function () {
    list.querySelectorAll(".cmd").forEach(function (d) {
      d.open = false;
    });
  });

  list.addEventListener("click", function (event) {
    var btn = event.target.closest(".copy");
    if (!btn) return;
    var text = btn.getAttribute("data-copy");
    var done = function () {
      btn.textContent = "Copied";
      btn.classList.add("is-done");
      setTimeout(function () {
        btn.textContent = "Copy";
        btn.classList.remove("is-done");
      }, 1400);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done);
  });

  select(pick(), false);
})();
