(function () {
  var toasts = document.getElementById("toasts");

  window.toast = function (message, isError) {
    if (!toasts) return;
    var el = document.createElement("div");
    el.className = "toast" + (isError ? " toast--error" : "");
    el.textContent = message;
    toasts.appendChild(el);
    setTimeout(function () {
      el.remove();
    }, isError ? 6000 : 3200);
  };

  document.addEventListener("keydown", function (event) {
    if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) return;
    var tag = (event.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return;
    var search = document.getElementById("cmd-search") || document.getElementById("mod-search");
    if (search) {
      event.preventDefault();
      search.focus();
    }
  });

  document.addEventListener("click", function (event) {
    var menu = document.querySelector(".menu[open]");
    if (menu && !menu.contains(event.target)) menu.removeAttribute("open");
  });
})();
