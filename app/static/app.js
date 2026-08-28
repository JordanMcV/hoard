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

  // Drag to reorder. Pointer events cover both mouse and touch, unlike the
  // HTML5 drag events, which iOS Safari never fires.
  document.querySelectorAll("[data-sortable]").forEach(function (container) {
    var endpoint = container.dataset.sortable;
    var saveTimer = null;

    function items() {
      return Array.prototype.slice.call(
        container.querySelectorAll(".sortable-item")
      );
    }

    function save() {
      window.clearTimeout(saveTimer);
      saveTimer = window.setTimeout(function () {
        var ids = items().map(function (el) {
          return Number(el.dataset.id);
        });
        window
          .fetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ids: ids }),
          })
          .catch(function () {
            // The order on screen is now ahead of the server. The next page
            // load shows what was actually stored.
          });
      }, 250);
    }

    function centre(el) {
      var r = el.getBoundingClientRect();
      return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
    }

    function distance(el, x, y) {
      var c = centre(el);
      return Math.pow(x - c.x, 2) + Math.pow(y - c.y, 2);
    }

    // Swap with whichever neighbour the pointer now sits closest to. Comparing
    // against the dragged card's own centre stops it flickering between two
    // slots when the pointer rests on a boundary.
    function reposition(dragged, x, y) {
      var best = null;
      var bestDistance = distance(dragged, x, y);
      items().forEach(function (el) {
        if (el === dragged) {
          return;
        }
        var d = distance(el, x, y);
        if (d < bestDistance) {
          bestDistance = d;
          best = el;
        }
      });
      if (!best) {
        return false;
      }
      var follows =
        dragged.compareDocumentPosition(best) & Node.DOCUMENT_POSITION_FOLLOWING;
      if (follows) {
        best.after(dragged);
      } else {
        best.before(dragged);
      }
      return true;
    }

    container.querySelectorAll(".draghandle").forEach(function (handle) {
      var item = handle.closest(".sortable-item");
      var dragging = false;

      handle.addEventListener("pointerdown", function (event) {
        event.preventDefault();
        dragging = true;
        handle.setPointerCapture(event.pointerId);
        container.classList.add("is-sorting");
        item.classList.add("is-dragging");
      });

      handle.addEventListener("pointermove", function (event) {
        if (dragging) {
          reposition(item, event.clientX, event.clientY);
        }
      });

      function stop() {
        if (!dragging) {
          return;
        }
        dragging = false;
        container.classList.remove("is-sorting");
        item.classList.remove("is-dragging");
        save();
      }

      handle.addEventListener("pointerup", stop);
      handle.addEventListener("pointercancel", stop);

      // Arrow keys move the card one place, for anyone not using a pointer.
      handle.addEventListener("keydown", function (event) {
        var back = event.key === "ArrowLeft" || event.key === "ArrowUp";
        var forward = event.key === "ArrowRight" || event.key === "ArrowDown";
        if (!back && !forward) {
          return;
        }
        var sibling = back
          ? item.previousElementSibling
          : item.nextElementSibling;
        if (!sibling) {
          return;
        }
        event.preventDefault();
        if (back) {
          sibling.before(item);
        } else {
          sibling.after(item);
        }
        handle.focus();
        save();
      });
    });
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
