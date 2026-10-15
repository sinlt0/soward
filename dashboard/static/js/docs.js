(function () {
  var search = document.getElementById("doc-search");
  var chips = document.querySelectorAll("#doc-chips .chip");
  if (search) {
    var cards = Array.prototype.slice.call(document.querySelectorAll(".docgrid a"));
    var groups = Array.prototype.slice.call(document.querySelectorAll(".docgroup"));
    var empty = document.getElementById("doc-empty");
    var active = "";
    var apply = function () {
      var q = search.value.trim().toLowerCase();
      var any = false;
      groups.forEach(function (grp) {
        var inGroup = !active || grp.getAttribute("data-group") === active;
        var shown = 0;
        grp.querySelectorAll(".docgrid a").forEach(function (card) {
          var match = inGroup && (!q || card.getAttribute("data-search").indexOf(q) !== -1);
          card.hidden = !match;
          if (match) shown += 1;
        });
        grp.hidden = shown === 0;
        if (shown) any = true;
      });
      if (empty) empty.hidden = any;
    };
    search.addEventListener("input", apply);
    chips.forEach(function (chip) {
      chip.addEventListener("click", function () {
        active = chip.getAttribute("data-group");
        chips.forEach(function (c) {
          c.setAttribute("aria-pressed", c === chip ? "true" : "false");
        });
        apply();
      });
    });
    return;
  }

  var prose = document.getElementById("prose");
  if (!prose) return;

  var filter = document.getElementById("doc-filter");
  var groupsNav = document.querySelectorAll(".docs__group");
  document.querySelectorAll(".docs__gtitle").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var wrap = btn.parentElement;
      var collapsed = wrap.getAttribute("data-collapsed") === "true";
      wrap.setAttribute("data-collapsed", collapsed ? "false" : "true");
      btn.setAttribute("aria-expanded", collapsed ? "true" : "false");
    });
  });
  if (filter) {
    filter.addEventListener("input", function () {
      var q = filter.value.trim().toLowerCase();
      groupsNav.forEach(function (grp) {
        var shown = 0;
        grp.querySelectorAll("a").forEach(function (a) {
          var match = !q || a.getAttribute("data-title").indexOf(q) !== -1;
          a.hidden = !match;
          if (match) shown += 1;
        });
        grp.hidden = shown === 0;
        if (q) grp.setAttribute("data-collapsed", "false");
      });
    });
  }

  prose.querySelectorAll("pre").forEach(function (pre) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "copy copy--code";
    btn.textContent = "Copy";
    btn.addEventListener("click", function () {
      var code = pre.querySelector("code");
      var text = (code || pre).innerText.replace(/\n$/, "");
      if (!navigator.clipboard || !navigator.clipboard.writeText) return;
      navigator.clipboard.writeText(text).then(function () {
        btn.textContent = "Copied";
        btn.classList.add("is-done");
        setTimeout(function () {
          btn.textContent = "Copy";
          btn.classList.remove("is-done");
        }, 1400);
      });
    });
    pre.appendChild(btn);
  });

  var heads = Array.prototype.slice.call(prose.querySelectorAll("h2[id], h3[id]"));
  var toc = document.getElementById("toc");
  var list = document.getElementById("toc-list");
  if (toc && list && heads.length > 2) {
    var links = {};
    heads.forEach(function (h) {
      var a = document.createElement("a");
      a.href = "#" + h.id;
      a.textContent = h.textContent;
      a.className = h.tagName === "H3" ? "toc__sub" : "";
      list.appendChild(a);
      links[h.id] = a;
    });
    toc.hidden = false;
    if ("IntersectionObserver" in window) {
      var observer = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            Object.keys(links).forEach(function (id) {
              links[id].classList.toggle("is-active", id === entry.target.id);
            });
          });
        },
        { rootMargin: "-80px 0px -70% 0px" }
      );
      heads.forEach(function (h) {
        observer.observe(h);
      });
    }
  }
})();
