(function () {
  var card = document.getElementById("appeal");
  if (!card) return;
  document.querySelectorAll("[data-time]").forEach(function (el) {
    var stamp = parseInt(el.getAttribute("data-time"), 10);
    if (stamp) el.textContent = "on " + new Date(stamp * 1000).toLocaleString();
  });
  var form = document.getElementById("appeal-form");
  if (!form) return;
  var status = document.getElementById("appeal-status");
  var button = document.getElementById("appeal-go");
  var max = parseInt(card.getAttribute("data-max"), 10) || 1000;
  var fields = form.querySelectorAll("textarea");

  function say(text, state) {
    status.textContent = text;
    status.setAttribute("data-state", state || "");
  }

  fields.forEach(function (field) {
    var counter = field.parentNode.querySelector(".appeal__count");
    field.addEventListener("input", function () {
      counter.textContent = field.value.length + " / " + max;
    });
  });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var answers = [];
    for (var i = 0; i < fields.length; i++) {
      var text = fields[i].value.trim();
      if (text.length < 10) {
        say("Answer " + (i + 1) + " needs at least a sentence.", "bad");
        fields[i].focus();
        return;
      }
      answers.push(text);
    }
    button.disabled = true;
    say("Sending your appeal...", "work");
    fetch(card.getAttribute("data-submit"), {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": document.body.getAttribute("data-csrf") || "" },
      body: JSON.stringify({ answers: answers })
    }).then(function (response) {
      return response.json().then(function (data) { return { status: response.status, data: data }; });
    }).then(function (result) {
      var data = result.data || {};
      if (data.ok) {
        say(data.message, "ok");
        form.querySelectorAll("textarea").forEach(function (f) { f.disabled = true; });
        button.hidden = true;
        return;
      }
      say(data.message || data.error || "Something went wrong. Try again.", "bad");
      button.disabled = false;
    }).catch(function () {
      say("Could not reach the server. Try again.", "bad");
      button.disabled = false;
    });
  });
})();
