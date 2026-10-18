(function () {
  var card = document.getElementById("verify");
  if (!card) return;
  var status = document.getElementById("verify-status");
  var button = document.getElementById("verify-go");
  var trap = document.getElementById("verify-trap");
  var started = Date.now();

  function say(text, state) {
    status.textContent = text;
    status.setAttribute("data-state", state || "");
  }

  function hex(buffer) {
    return Array.prototype.map.call(new Uint8Array(buffer), function (b) { return ("0" + b.toString(16)).slice(-2); }).join("");
  }

  function sha(text) {
    return crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)).then(hex);
  }

  function solve(nonce, prefix) {
    var counter = 0;
    function step() {
      var batch = [];
      for (var i = 0; i < 400; i++) batch.push(sha(nonce + (counter + i)));
      return Promise.all(batch).then(function (hashes) {
        for (var j = 0; j < hashes.length; j++) {
          if (hashes[j].indexOf(prefix) === 0) return String(counter + j);
        }
        counter += 400;
        return step();
      });
    }
    return step();
  }

  function fingerprint() {
    var canvas = "";
    try {
      var c = document.createElement("canvas");
      var g = c.getContext("2d");
      g.textBaseline = "top";
      g.font = "14px Arial";
      g.fillText("soward-verify", 2, 2);
      canvas = c.toDataURL();
    } catch (e) {}
    var parts = [
      navigator.userAgent, navigator.language, navigator.hardwareConcurrency || "", screen.width + "x" + screen.height,
      screen.colorDepth, Intl.DateTimeFormat().resolvedOptions().timeZone || "", new Date().getTimezoneOffset(), canvas
    ];
    return sha(parts.join("|"));
  }

  function turnstileToken() {
    var field = document.querySelector("[name='cf-turnstile-response']");
    return field ? field.value : "";
  }

  button.addEventListener("click", function () {
    button.disabled = true;
    say("Checking your browser...", "work");
    var wait = Math.max(0, 2500 - (Date.now() - started));
    Promise.all([solve(card.dataset.nonce, card.dataset.prefix), fingerprint(), new Promise(function (r) { setTimeout(r, wait); })])
      .then(function (results) {
        say("Finishing up...", "work");
        return fetch(card.dataset.submit, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            nonce: card.dataset.nonce, issued: card.dataset.issued, sig: card.dataset.sig, counter: results[0],
            fingerprint: results[1], website: trap.value, turnstile: turnstileToken()
          })
        });
      })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        say(data.message || "Done.", data.ok ? "ok" : "bad");
        if (!data.ok) button.hidden = true;
      })
      .catch(function () {
        say("Something went wrong. Reload the page and try again.", "bad");
        button.disabled = false;
      });
  });
})();
