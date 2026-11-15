/**
 * Username suggestions for the new direct-chat form.
 */
(function () {
  "use strict";

  var input = document.getElementById("id_other_username");
  if (!input) return;

  var list = document.createElement("ul");
  list.id = "chat-user-suggest";
  list.className = "chat-suggest";
  list.setAttribute("role", "listbox");
  list.hidden = true;
  input.insertAdjacentElement("afterend", list);
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-expanded", "false");
  input.setAttribute("aria-controls", list.id);

  var timer = 0;
  var active = -1;
  var controller = null;

  function setExpanded(open) {
    input.setAttribute("aria-expanded", open ? "true" : "false");
    list.hidden = !open;
    if (!open) {
      active = -1;
      input.removeAttribute("aria-activedescendant");
    }
  }

  function options() {
    return list.querySelectorAll("[role='option']");
  }

  function highlight(index) {
    var rows = options();
    active = index;
    rows.forEach(function (row, i) {
      if (i === index) {
        row.classList.add("is-active");
        input.setAttribute("aria-activedescendant", row.id);
        row.scrollIntoView({ block: "nearest" });
      } else {
        row.classList.remove("is-active");
      }
    });
  }

  function choose(row) {
    if (!row || row.getAttribute("aria-disabled") === "true") return;
    input.value = row.getAttribute("data-username") || row.textContent;
    setExpanded(false);
    input.focus();
  }

  function clearList() {
    while (list.firstChild) list.removeChild(list.firstChild);
  }

  function render(rows, note) {
    clearList();
    if (note) {
      var empty = document.createElement("li");
      empty.id = "chat-user-suggest-empty";
      empty.setAttribute("role", "option");
      empty.setAttribute("aria-disabled", "true");
      empty.textContent = note;
      list.appendChild(empty);
      setExpanded(true);
      return;
    }
    rows.forEach(function (row, index) {
      var item = document.createElement("li");
      item.id = "chat-user-suggest-" + index;
      item.setAttribute("role", "option");
      item.setAttribute("data-username", row.username);
      var avatar = document.createElement("span");
      avatar.className = "chat-suggest__avatar";
      avatar.setAttribute("aria-hidden", "true");
      var letters = document.createElement("span");
      letters.textContent = row.initials || "?";
      avatar.appendChild(letters);
      if (row.avatar_url) {
        var img = document.createElement("img");
        img.alt = "";
        img.src = row.avatar_url;
        avatar.appendChild(img);
      }
      var name = document.createElement("span");
      name.className = "chat-suggest__name";
      name.textContent = row.username;
      name.title = row.username;
      item.appendChild(avatar);
      item.appendChild(name);
      item.addEventListener("mousedown", function (event) {
        event.preventDefault();
        choose(item);
      });
      list.appendChild(item);
    });
    setExpanded(rows.length > 0);
  }

  function search(query) {
    if (controller) controller.abort();
    controller = new AbortController();
    fetch("/api/chat/users/?q=" + encodeURIComponent(query), {
      credentials: "same-origin",
      signal: controller.signal,
    }).then(function (response) {
      if (!response.ok) throw new Error("search failed");
      return response.json();
    }).then(function (data) {
      if ((input.value || "").trim() !== query) return;
      var rows = (data && data.results) || [];
      render(rows, rows.length ? "" : "No matching players");
    }).catch(function (failure) {
      if (failure && failure.name === "AbortError") return;
      setExpanded(false);
    });
  }

  input.addEventListener("input", function () {
    var query = (input.value || "").trim();
    window.clearTimeout(timer);
    if (query.length < 2) {
      if (controller) controller.abort();
      setExpanded(false);
      clearList();
      return;
    }
    timer = window.setTimeout(function () { search(query); }, 250);
  });

  input.addEventListener("keydown", function (event) {
    var rows = options();
    if (list.hidden || !rows.length) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      highlight(Math.min(active + 1, rows.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      highlight(Math.max(active - 1, 0));
    } else if (event.key === "Enter" && active >= 0) {
      event.preventDefault();
      choose(rows[active]);
    } else if (event.key === "Escape") {
      setExpanded(false);
    }
  });

  input.addEventListener("blur", function () {
    window.setTimeout(function () { setExpanded(false); }, 150);
  });
})();
