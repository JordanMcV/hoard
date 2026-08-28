// The filter forms submit themselves. The Apply button stays in the markup as
// the fallback for browsers without JavaScript, so hide it here.
(function () {
  var SEARCH_DELAY = 400;
  var REFOCUS_KEY = "hoard:refocus";

  function submit(form) {
    if (form.requestSubmit) {
      form.requestSubmit();
    } else {
      form.submit();
    }
  }

  function remember(key, value) {
    try {
      window.sessionStorage.setItem(key, value);
    } catch (e) {
      // Private windows and blocked site data throw. Focus restore is optional.
    }
  }

  function take(key) {
    try {
      var value = window.sessionStorage.getItem(key);
      window.sessionStorage.removeItem(key);
      return value;
    } catch (e) {
      return null;
    }
  }

  document.querySelectorAll("form.filters").forEach(function (form) {
    var apply = form.querySelector("button[type=submit]");
    if (apply) {
      apply.hidden = true;
    }

    form.querySelectorAll("select").forEach(function (select) {
      select.addEventListener("change", function () {
        submit(form);
      });
    });

    var search = form.querySelector("input[type=search]");
    if (!search) {
      return;
    }

    var timer = null;
    search.addEventListener("input", function () {
      window.clearTimeout(timer);
      timer = window.setTimeout(function () {
        remember(REFOCUS_KEY, window.location.pathname);
        submit(form);
      }, SEARCH_DELAY);
    });

    // Enter submits straight away, so drop the pending reload.
    form.addEventListener("submit", function () {
      window.clearTimeout(timer);
    });

    if (take(REFOCUS_KEY) === window.location.pathname) {
      search.focus();
      search.setSelectionRange(search.value.length, search.value.length);
    }
  });

  // Remember whether each accordion is open, per browser.
  document.querySelectorAll("details[id]").forEach(function (details) {
    var key = "hoard:open:" + details.id;
    var stored = null;
    try {
      stored = window.localStorage.getItem(key);
    } catch (e) {
      stored = null;
    }
    if (stored !== null) {
      details.open = stored === "1";
    }
    details.addEventListener("toggle", function () {
      try {
        window.localStorage.setItem(key, details.open ? "1" : "0");
      } catch (e) {
        // Nothing to do. The accordion still works for this page view.
      }
    });
  });
})();
