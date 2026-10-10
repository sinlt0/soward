(function () {
  var input = document.getElementById("cmd-search");
  var list = document.getElementById("cmdlist");
  if (!input || !list) return;
  var empty = document.getElementById("cmd-empty");
  var sections = list.querySelectorAll(".cmdcat");
  var links = document.querySelectorAll("#cmdnav a");

  function filter() {
    var q = input.value.trim().toLowerCase();
    var any = false;
    sections.forEach(function (section) {
      var shown = 0;
      section.querySelectorAll(".cmd").forEach(function (cmd) {
        var match = !q || cmd.getAttribute("data-search").indexOf(q) !== -1;
        cmd.hidden = !match;
        if (match) shown += 1;
        if (q && match && shown <= 3) cmd.open = false;
      });
      section.hidden = shown === 0;
      if (shown) any = true;
    });
    if (empty) empty.hidden = any;
  }

  input.addEventListener("input", filter);

  if ("IntersectionObserver" in window) {
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          links.forEach(function (a) {
            a.setAttribute("aria-current", a.getAttribute("data-cat") === entry.target.id ? "true" : "false");
          });
        });
      },
      { rootMargin: "-20% 0px -70% 0px" }
    );
    sections.forEach(function (s) {
      observer.observe(s);
    });
  }
})();
