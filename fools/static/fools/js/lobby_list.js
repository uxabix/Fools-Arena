/**
 * Public lobby list and the create-lobby form.
 * The server remains the source of truth for names, passwords, and rules.
 */
(function () {
  "use strict";

  var API = "/api/fools/lobbies/";
  var page = document.querySelector(".lobby-list-page");
  if (!page) return;

  var userId = (page.getAttribute("data-user-id") || "").toLowerCase();
  var currentLobbyId = (page.getAttribute("data-current-lobby-id") || "").toLowerCase();
  var currentLobbyName = page.getAttribute("data-current-lobby-name") || "your current lobby";
  var currentLobbyUrl = page.getAttribute("data-current-lobby-url") || "";
  var listEl = document.getElementById("lobby-list");
  var loadingEl = document.getElementById("lobby-loading");
  var errorEl = document.getElementById("lobby-error");
  var errorText = document.getElementById("lobby-error-text");
  var emptyEl = document.getElementById("lobby-empty");
  var refreshBtn = document.getElementById("lobby-refresh");
  var form = document.getElementById("create-form");
  var openBtn = document.getElementById("create-open");
  var cancelBtn = document.getElementById("create-cancel");
  var submitBtn = document.getElementById("create-submit");
  var submitLabel = document.getElementById("create-submit-label");
  var privateBox = document.getElementById("id_is_private");
  var passwordWrap = document.getElementById("password-field");
  var passwordInput = document.getElementById("id_password");
  var creating = false;
  var createConfirmed = false;
  var pendingJoinButton = null;
  var loading = false;
  var listSocket = null;
  var reconnectTimer = 0;
  var leaveDialog = document.getElementById("leave-lobby-dialog");

  function csrf() {
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function sameId(a, b) {
    return String(a || "").toLowerCase() === String(b || "").toLowerCase();
  }

  async function api(method, url, body) {
    var opts = { method: method, credentials: "same-origin", headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.headers["X-CSRFToken"] = csrf();
      opts.body = JSON.stringify(body);
    }
    var response = await fetch(url, opts);
    var text = await response.text();
    var data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch (ignore) {
      data = { detail: text || response.statusText };
    }
    if (!response.ok) {
      var error = new Error(
        (data && data.detail) || response.statusText || String(response.status)
      );
      error.data = data;
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function messageOf(value) {
    if (Array.isArray(value)) return value.join(" ");
    if (value && typeof value === "object") return value.detail || "Could not create the lobby.";
    return value ? String(value) : "Could not create the lobby.";
  }

  function setFieldError(name, message) {
    var field = form.querySelector('[data-field="' + name + '"]');
    if (!field) {
      setFormError(message);
      return;
    }
    field.classList.add("is-invalid");
    var input = field.querySelector("input, select");
    if (input) input.setAttribute("aria-invalid", "true");
    var slot = field.querySelector(".lobby-field__error");
    if (!slot) return;
    slot.hidden = false;
    slot.textContent = message;
  }

  function setFormError(message) {
    var slot = document.getElementById("create-error");
    slot.hidden = !message;
    slot.textContent = message || "";
  }

  function clearErrors() {
    form.querySelectorAll(".is-invalid").forEach(function (field) {
      field.classList.remove("is-invalid");
    });
    form.querySelectorAll("[aria-invalid]").forEach(function (input) {
      input.removeAttribute("aria-invalid");
    });
    form.querySelectorAll(".lobby-field__error").forEach(function (slot) {
      slot.hidden = true;
      slot.textContent = "";
    });
  }

  function applyErrors(data) {
    clearErrors();
    if (!data || typeof data !== "object") {
      setFormError(messageOf(data));
      return;
    }
    var placed = false;
    Object.keys(data).forEach(function (key) {
      if (key === "detail" || key === "non_field_errors") return;
      setFieldError(key, messageOf(data[key]));
      placed = true;
    });
    if (data.non_field_errors) {
      setFormError(messageOf(data.non_field_errors));
      placed = true;
    }
    if (!placed && data.detail) setFormError(messageOf(data.detail));
    var first = form.querySelector(".is-invalid input, .is-invalid select, #create-error:not([hidden])");
    if (first && first.focus) first.focus();
  }

  function syncPassword() {
    var on = privateBox.checked;
    passwordWrap.hidden = !on;
    passwordInput.required = on;
    if (!on) {
      var field = form.querySelector('[data-field="password"]');
      field.classList.remove("is-invalid");
      passwordInput.removeAttribute("aria-invalid");
      document.getElementById("password-error").hidden = true;
    }
  }

  function openForm() {
    form.hidden = false;
    openBtn.hidden = true;
    document.getElementById("id_name").focus();
    form.scrollIntoView({ block: "nearest" });
  }

  function closeForm() {
    form.hidden = true;
    openBtn.hidden = false;
    openBtn.focus();
  }

  function rulesText(lobby) {
    var settings = lobby.settings || {};
    var parts = [
      lobby.active_player_count + " of " + settings.max_players + " players",
      settings.card_count + "-card deck",
    ];
    if (settings.neighbor_throw_only) parts.push("Neighbors only");
    if (settings.allow_jokers) parts.push("Jokers");
    return parts.join(" · ");
  }

  function isMine(lobby) {
    if (currentLobbyId && sameId(lobby.id, currentLobbyId)) return true;
    return (lobby.players || []).some(function (player) {
      return sameId(player.user_id, userId);
    });
  }

  function isFull(lobby) {
    var settings = lobby.settings || {};
    return lobby.active_player_count >= settings.max_players;
  }

  function buildRow() {
    var li = document.createElement("li");
    li.className = "lobby-row";
    li.innerHTML =
      '<div class="lobby-row__body">' +
        '<p class="lobby-row__badge">Your lobby</p>' +
        '<h3 class="lobby-row__name"></h3>' +
        '<p class="lobby-row__meta"></p>' +
        '<p class="lobby-row__seats">No seats</p>' +
      "</div>" +
      '<div class="lobby-row__actions">' +
        '<a class="game-btn game-btn--secondary lobby-open">Open lobby</a>' +
        '<button type="button" class="game-btn game-btn--primary lobby-join">Join</button>' +
      "</div>";
    return li;
  }

  function fillRow(li, lobby) {
    var mine = isMine(lobby);
    var full = isFull(lobby);
    li.dataset.lobbyId = lobby.id;
    li.classList.toggle("is-current", mine);
    li.querySelector(".lobby-row__badge").hidden = !mine;
    li.querySelector(".lobby-row__name").textContent = lobby.name;
    li.querySelector(".lobby-row__meta").textContent = rulesText(lobby);
    li.querySelector(".lobby-row__seats").hidden = !full;
    var open = li.querySelector(".lobby-open");
    open.href = "/fools/lobbies/" + lobby.id + "/";
    var join = li.querySelector(".lobby-join");
    join.hidden = mine || full;
    join.setAttribute("data-join", lobby.id);
  }

  function rowFor(id) {
    return listEl.querySelector('[data-lobby-id="' + id + '"]');
  }

  function preserveScroll(mutate) {
    var y = window.scrollY;
    var probe = document.elementFromPoint(Math.min(window.innerWidth / 2, 200), 160);
    var anchor = probe && probe.closest ? probe.closest("[data-lobby-id]") : null;
    var id = anchor ? anchor.dataset.lobbyId : "";
    var top = anchor ? anchor.getBoundingClientRect().top : 0;
    mutate();
    if (!id) return;
    var next = rowFor(id);
    if (!next) return;
    window.scrollTo(0, y + (next.getBoundingClientRect().top - top));
  }

  function renderList(rows) {
    var seen = {};
    preserveScroll(function () {
      rows.forEach(function (lobby) {
        seen[lobby.id] = true;
        var li = rowFor(lobby.id);
        if (!li) {
          li = buildRow();
          listEl.appendChild(li);
        }
        fillRow(li, lobby);
      });
      rows.forEach(function (lobby) {
        var li = rowFor(lobby.id);
        if (li) listEl.appendChild(li);
      });
      Array.prototype.slice.call(listEl.children).forEach(function (li) {
        if (!seen[li.dataset.lobbyId]) li.remove();
      });
    });
    var hasRows = rows.length > 0;
    listEl.hidden = !hasRows;
    emptyEl.hidden = hasRows;
    errorEl.hidden = true;
    loadingEl.hidden = true;
  }

  function showLoadError(error) {
    loadingEl.hidden = true;
    errorText.textContent = "Could not load lobbies. " + (error.message || "Try again.");
    errorEl.hidden = false;
    if (!listEl.children.length) {
      listEl.hidden = true;
      emptyEl.hidden = true;
    }
  }

  async function refresh(manual) {
    if (loading) return;
    loading = true;
    if (manual) {
      refreshBtn.disabled = true;
      refreshBtn.textContent = "Refreshing…";
    }
    try {
      var rows = await api("GET", API);
      renderList(rows || []);
    } catch (error) {
      showLoadError(error);
    } finally {
      loading = false;
      refreshBtn.disabled = false;
      refreshBtn.textContent = "Refresh";
    }
  }

  function openLeaveDialog(mode, joinButton) {
    var confirmButton = document.getElementById("leave-confirm");
    document.getElementById("leave-return").href = currentLobbyUrl;
    pendingJoinButton = mode === "join" ? joinButton : null;
    if (mode === "join") {
      document.getElementById("leave-lobby-text").textContent =
        "Joining this lobby takes you out of " + currentLobbyName + ".";
      confirmButton.textContent = "Join anyway";
      confirmButton.value = "join";
    } else {
      document.getElementById("leave-lobby-text").textContent =
        "Creating this lobby takes you out of " + currentLobbyName + ".";
      confirmButton.textContent = "Create anyway";
      confirmButton.value = "create";
    }
    leaveDialog.showModal();
  }

  async function joinLobby(id, button, confirmed) {
    if (button.disabled) return;
    if (currentLobbyId && !sameId(id, currentLobbyId) && !confirmed) {
      openLeaveDialog("join", button);
      return;
    }
    button.disabled = true;
    button.textContent = "Joining…";
    try {
      await api("POST", API + id + "/join/", {});
      window.location.href = "/fools/lobbies/" + id + "/";
    } catch (error) {
      button.disabled = false;
      button.textContent = "Join";
      errorText.textContent = error.message || "Could not join this lobby.";
      errorEl.hidden = false;
    }
  }

  listEl.addEventListener("click", function (event) {
    var button = event.target.closest("[data-join]");
    if (!button) return;
    event.preventDefault();
    joinLobby(button.getAttribute("data-join"), button);
  });

  refreshBtn.addEventListener("click", function () {
    refresh(true);
  });
  document.getElementById("lobby-retry").addEventListener("click", function () {
    refresh(true);
  });
  document.getElementById("lobby-empty-create").addEventListener("click", openForm);
  openBtn.addEventListener("click", openForm);
  cancelBtn.addEventListener("click", closeForm);
  privateBox.addEventListener("change", syncPassword);

  function upsertLobby(lobby) {
    if (!lobby || !lobby.id || lobby.is_private || lobby.status !== "waiting") {
      if (lobby && lobby.id) removeLobby(lobby.id);
      return;
    }
    var active = lobby.active_player_count || 0;
    if (active < 1) {
      removeLobby(lobby.id);
      return;
    }
    var existing = rowFor(lobby.id);
    if (existing) {
      fillRow(existing, lobby);
    } else {
      var y = window.scrollY;
      var li = buildRow();
      listEl.hidden = false;
      emptyEl.hidden = true;
      loadingEl.hidden = true;
      listEl.insertBefore(li, listEl.firstChild);
      fillRow(li, lobby);
      if (y > 0) window.scrollTo(0, y + li.offsetHeight);
    }
    listEl.hidden = false;
    emptyEl.hidden = true;
  }

  function removeLobby(id) {
    var li = rowFor(id);
    if (li) li.remove();
    if (!listEl.children.length) {
      listEl.hidden = true;
      emptyEl.hidden = false;
    }
  }

  function connectList() {
    if (listSocket && (listSocket.readyState === WebSocket.OPEN || listSocket.readyState === WebSocket.CONNECTING)) {
      return;
    }
    var proto = location.protocol === "https:" ? "wss:" : "ws:";
    var socket = new WebSocket(proto + "//" + location.host + "/ws/lobbies/");
    listSocket = socket;
    socket.onmessage = function (event) {
      var message;
      try {
        message = JSON.parse(event.data);
      } catch (ignore) {
        return;
      }
      if (!message || !message.payload) return;
      if (message.event === "lobby_upsert") upsertLobby(message.payload);
      if (message.event === "lobby_removed") removeLobby(message.payload.id);
    };
    socket.onclose = function () {
      if (listSocket === socket) listSocket = null;
      window.clearTimeout(reconnectTimer);
      reconnectTimer = window.setTimeout(connectList, 2000);
    };
  }

  leaveDialog.addEventListener("close", function () {
    var choice = leaveDialog.returnValue;
    if (choice === "create") {
      createConfirmed = true;
      if (form.requestSubmit) form.requestSubmit();
      else form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
      return;
    }
    if (choice === "join" && pendingJoinButton) {
      var button = pendingJoinButton;
      var id = button.getAttribute("data-join");
      pendingJoinButton = null;
      joinLobby(id, button, true);
      return;
    }
    pendingJoinButton = null;
  });

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    if (creating) return;
    if (currentLobbyId && !createConfirmed) {
      openLeaveDialog("create");
      return;
    }
    createConfirmed = false;
    creating = true;
    clearErrors();
    submitBtn.disabled = true;
    submitBtn.setAttribute("aria-busy", "true");
    submitLabel.textContent = "Creating…";
    var body = {
      name: document.getElementById("id_name").value.trim(),
      is_private: privateBox.checked,
      max_players: Number(document.getElementById("id_max_players").value),
      card_count: Number(document.getElementById("id_card_count").value),
      neighbor_throw_only: document.getElementById("id_neighbor_throw_only").checked,
    };
    if (privateBox.checked) body.password = passwordInput.value;
    try {
      var lobby = await api("POST", API, body);
      window.location.href = "/fools/lobbies/" + lobby.id + "/";
    } catch (error) {
      applyErrors(error.data || { detail: error.message });
      creating = false;
      submitBtn.disabled = false;
      submitBtn.removeAttribute("aria-busy");
      submitLabel.textContent = "Create lobby";
    }
  });

  syncPassword();
  refresh(false);
  connectList();
  window.addEventListener("pagehide", function () {
    window.clearTimeout(reconnectTimer);
    if (listSocket) listSocket.close();
  });
})();
