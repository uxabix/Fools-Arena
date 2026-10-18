/**
 * Lobby room: seats, readiness, game settings, invite link, and lobby chat.
 * State comes from the lobby REST API. Live updates arrive on the lobby socket.
 */
(function () {
  "use strict";

  var page = document.querySelector(".lobby-detail-page");
  if (!page) return;

  var lobbyId = page.getAttribute("data-lobby-id");
  var listUrl = (document.querySelector(".game-back") || {}).href || "/fools/";
  var API = "/api/fools/lobbies/" + lobbyId + "/";
  var PROFILE = "/api/accounts/auth/profile/";

  var titleEl = document.getElementById("lobby-title");
  var connection = document.getElementById("lobby-connection");
  var connectionText = document.getElementById("lobby-connection-text");
  var connectionActions = document.getElementById("lobby-connection-actions");
  var retryBtn = document.getElementById("lobby-retry");
  var connectionBack = document.getElementById("lobby-connection-back");
  var settingsNotice = document.getElementById("settings-notice");
  var settingsEl = document.getElementById("lobby-settings");
  var roster = document.getElementById("lobby-roster");
  var playersEl = document.getElementById("players");
  var playersEmpty = document.getElementById("players-empty");
  var playersCount = document.getElementById("players-count");
  var readyCount = document.getElementById("ready-count");
  var readyLive = document.getElementById("ready-live");
  var actionsEl = document.getElementById("actions");
  var joinPrompt = document.getElementById("join-prompt");
  var memberNote = document.getElementById("member-note");
  var startHint = document.getElementById("start-hint");
  var joinBtn = document.getElementById("btn-join");
  var joinLabel = document.getElementById("btn-join-label");
  var joinError = document.getElementById("join-error");
  var settingsBtn = document.getElementById("btn-settings");
  var settingsLabel = document.getElementById("btn-settings-label");
  var settingsDialog = document.getElementById("settings-dialog");
  var settingsForm = document.getElementById("settings-form");
  var settingsPlayers = document.getElementById("settings-max-players");
  var settingsDeck = document.getElementById("settings-card-count");
  var settingsNeighbors = document.getElementById("settings-neighbors");
  var settingsTransfer = document.getElementById("settings-transfer");
  var settingsBots = document.getElementById("settings-bots");
  var settingsSignals = document.getElementById("settings-signals");
  var settingsFormError = document.getElementById("settings-form-error");
  var settingsCancel = document.getElementById("settings-cancel");
  var settingsSave = document.getElementById("settings-save");
  var settingsSaveLabel = document.getElementById("settings-save-label");
  var readyBtn = document.getElementById("btn-ready");
  var readyLabel = document.getElementById("btn-ready-label");
  var readyError = document.getElementById("ready-error");
  var startBtn = document.getElementById("btn-start");
  var startLabel = document.getElementById("btn-start-label");
  var startError = document.getElementById("start-error");
  var leaveBtn = document.getElementById("btn-leave");
  var leaveLabel = document.getElementById("btn-leave-label");
  var leaveError = document.getElementById("leave-error");
  var invite = document.getElementById("lobby-invite");
  var invitePassword = document.getElementById("lobby-invite-password");
  var inviteLead = document.getElementById("lobby-invite-lead");
  var inviteUrl = document.getElementById("lobby-invite-url");
  var inviteCopy = document.getElementById("lobby-invite-copy");
  var inviteStatus = document.getElementById("lobby-invite-status");
  var privateForm = document.getElementById("private-join");
  var privatePassword = document.getElementById("private-join-password");
  var privateError = document.getElementById("private-join-error");
  var privateSubmit = document.getElementById("private-join-submit");
  var privateLabel = document.getElementById("private-join-label");
  var chatSection = document.getElementById("lobby-chat");
  var chatEmpty = document.getElementById("chat-empty");
  var chatLog = document.getElementById("chat-log");
  var chatForm = document.getElementById("chat-form");
  var chatInput = document.getElementById("chat-input");
  var chatSend = document.getElementById("chat-send");
  var chatSendLabel = document.getElementById("chat-send-label");
  var chatError = document.getElementById("chat-error");
  var leaveDialog = document.getElementById("leave-dialog");
  var leaveText = document.getElementById("leave-dialog-text");

  var profile = null;
  var profileReady = false;
  var lastState = null;
  var previousStatuses = {};
  var lastReadyCount = null;
  var lastSettingsKey = null;
  var OPENING_HAND = 6;
  var pending = "";
  var chatLoaded = false;
  var navigatedToGame = false;
  var connectionMode = "connecting";
  var socketWanted = false;
  var lobbyWs = null;
  var reconnectTimer = 0;

  function uidStr() {
    return profile && profile.id != null ? String(profile.id) : "";
  }

  function idKey(value) {
    return String(value == null ? "" : value).toLowerCase().replace(/-/g, "");
  }

  function uuidEq(a, b) {
    if (a == null || b == null) return false;
    return idKey(a) === idKey(b);
  }

  function csrf() {
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function api(method, url, body) {
    var opts = { method: method, credentials: "same-origin", headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.headers["X-CSRFToken"] = csrf();
      opts.body = JSON.stringify(body);
    }
    return fetch(url, opts).then(function (response) {
      return response.text().then(function (text) {
        var data = null;
        try { data = text ? JSON.parse(text) : null; } catch (ignore) { data = text; }
        if (!response.ok) {
          var error = new Error((data && data.detail) || response.statusText || String(response.status));
          error.data = data;
          error.status = response.status;
          throw error;
        }
        return data;
      });
    });
  }

  function errorText(error) {
    if (error && error.data && error.data.detail) return String(error.data.detail);
    if (!error || error.message === "Failed to fetch") return "The server did not respond.";
    if (error.status === 403) return "You cannot do that right now.";
    return error.message || "Something went wrong.";
  }

  function showError(node, text) {
    node.hidden = false;
    node.textContent = text;
  }

  function clearError(node) {
    node.hidden = true;
    node.textContent = "";
  }

  function findMe(lobby) {
    if (!lobby || !uidStr()) return null;
    var players = lobby.players || [];
    for (var i = 0; i < players.length; i += 1) {
      if (uuidEq(players[i].user_id, uidStr())) return players[i];
    }
    return null;
  }

  function setConnection(mode) {
    connectionMode = mode;
    if (mode === "clear") {
      connection.hidden = true;
      return;
    }
    var text = "Connecting…";
    var bannerClass = "game-banner game-banner--wait";
    var showRetry = false;
    var showBack = false;
    if (mode === "lost") {
      text = "Connection lost. Player status and chat are not updating.";
      bannerClass = "game-banner game-banner--alert";
      showRetry = true;
      showBack = true;
    } else if (mode === "closed") {
      text = "This lobby is closed.";
      bannerClass = "game-banner game-banner--muted";
      showBack = true;
    }
    connection.hidden = false;
    connection.className = bannerClass;
    connectionText.textContent = text;
    retryBtn.hidden = !showRetry;
    connectionBack.hidden = !showBack;
    connectionActions.hidden = !showRetry && !showBack;
  }

  function showAction(button, error, visible) {
    button.classList.toggle("game-btn--hidden", !visible);
    button.closest(".lobby-action").hidden = !visible;
    if (!visible && error) clearError(error);
  }

  function showButton(button, visible) {
    button.classList.toggle("game-btn--hidden", !visible);
    button.closest(".lobby-action").hidden = !visible;
  }

  function badge(text, className) {
    var node = document.createElement("span");
    node.className = className;
    node.textContent = text;
    return node;
  }

  function statusLabel(status) {
    if (status === "waiting") return "Waiting";
    if (status === "ready") return "Ready";
    if (status === "playing") return "Playing";
    return "In lobby";
  }

  function addSetting(term, value, on) {
    var wrap = document.createElement("div");
    var dt = document.createElement("dt");
    var dd = document.createElement("dd");
    dt.textContent = term;
    dd.textContent = value;
    if (on === true) dd.className = "is-on";
    if (on === false) dd.className = "is-off";
    wrap.appendChild(dt);
    wrap.appendChild(dd);
    settingsEl.appendChild(wrap);
  }

  function secondsLabel(value) {
    var count = Number(value);
    return count + (count === 1 ? " second" : " seconds");
  }

  function fillSettings(lobby, seated) {
    var settings = lobby.settings || {};
    settingsEl.innerHTML = "";
    var max = settings.max_players || 0;
    addSetting("Players", max ? seated + " of " + max : String(seated), null);
    if (settings.card_count) addSetting("Deck", settings.card_count + " cards", null);
    addSetting("Transfer", settings.is_transferable ? "On" : "Off", !!settings.is_transferable);
    if (settings.neighbor_throw_only) addSetting("Neighbors only", "On", true);
    if (settings.allow_jokers) addSetting("Jokers", "On", true);
    if (settings.fill_with_bots) addSetting("Bots", "On", true);
    if (settings.turn_time_limit) addSetting("Turn timer", secondsLabel(settings.turn_time_limit), true);
    if (settings.share_hand_signals === false) addSetting("Hand signals", "Off", false);
    settingsEl.hidden = false;
  }

  function waitingHumans(lobby) {
    var waiting = 0;
    (lobby.players || []).forEach(function (player) {
      if (!player.is_bot && player.status !== "ready") waiting += 1;
    });
    return waiting;
  }

  function startHintText(lobby, isOwner) {
    if (!lobby) return "";
    if (lobby.status === "playing" || lobby.active_game_id) return "The game has started.";
    if (lobby.status !== "waiting") return "";
    var settings = lobby.settings || {};
    var ready = lobby.ready_count || 0;
    var bots = !!settings.fill_with_bots;
    if (bots) {
      if (lobby.can_start) {
        var lead = isOwner ? "Press Start game to deal." : "Waiting for the host to start.";
        return lead + " Bots fill empty seats.";
      }
      var waiting = waitingHumans(lobby);
      if (waiting === 1) return "One more player needs to be ready. Bots fill empty seats.";
      if (waiting > 1) return waiting + " more players need to be ready. Bots fill empty seats.";
      return "Every player needs to be ready. Bots fill empty seats.";
    }
    if (lobby.can_start) {
      return isOwner ? "Press Start game to deal." : "Waiting for the host to start.";
    }
    var missing = Math.max(0, 2 - ready);
    if (missing === 1) return "One more ready player is needed to start.";
    if (missing > 1) return missing + " more ready players are needed to start.";
    return "At least two ready players are needed to start.";
  }

  function membershipText(lobby, me, isOwner) {
    if (lobby.status === "playing" || me.status === "playing") {
      return isOwner
        ? "You are the host. The game is underway."
        : "You are in this lobby. The game is underway.";
    }
    if (isOwner && me.status === "ready") {
      return "You are the host and you are ready. You can start the game or cancel ready.";
    }
    if (isOwner) return "You are the host. Mark ready, then start when the table can begin.";
    if (me.status === "ready") return "You are ready. You can cancel ready or leave.";
    return "You are in this lobby. Mark ready when you can play, or leave.";
  }

  function nextHostName(lobby) {
    var humans = (lobby.players || []).filter(function (player) {
      return !player.is_bot && !uuidEq(player.user_id, lobby.owner_id);
    });
    humans.sort(function (a, b) {
      return String(a.joined_at || "").localeCompare(String(b.joined_at || ""));
    });
    if (!humans.length) return "";
    if (humans.length > 1 && humans[0].joined_at && humans[0].joined_at === humans[1].joined_at) {
      return "";
    }
    return humans[0].username || "";
  }

  function leaveWarning(lobby, me, isOwner) {
    var parts = [];
    if (isOwner) {
      if ((lobby.human_count || 0) <= 1) {
        parts.push("You are the host. Leaving closes this lobby.");
      } else {
        var name = nextHostName(lobby);
        parts.push(name
          ? "You are the host. " + name + " will become the host."
          : "You are the host. The player who has been here longest will become the host.");
      }
    }
    if (me && me.status === "ready") {
      parts.push("You are marked ready, so leaving can hold up the start.");
    }
    if (me && me.status === "playing") {
      parts.push("A game is in progress. Leaving forfeits your seat.");
    }
    return parts.join(" ");
  }

  function markUpdated(node) {
    node.classList.add("is-updated");
    window.setTimeout(function () {
      node.classList.remove("is-updated");
    }, 1200);
  }

  function renderPlayers(lobby, seated, ready, max, quiet) {
    var announcements = [];
    var nextStatuses = {};
    playersEl.innerHTML = "";
    (lobby.players || []).forEach(function (player) {
      var key = idKey(player.user_id);
      nextStatuses[key] = player.status;
      var li = document.createElement("li");
      li.className = "lobby-player";
      if (previousStatuses[key] && previousStatuses[key] !== player.status) {
        markUpdated(li);
        if (!quiet) {
          if (player.status === "ready") announcements.push(player.username + " is ready.");
          else if (player.status === "waiting") announcements.push(player.username + " is waiting.");
          else if (player.status === "playing") announcements.push(player.username + " is in the game.");
        }
      }
      var identity = document.createElement("div");
      identity.className = "lobby-player__identity";
      var name = document.createElement("span");
      name.className = "lobby-player__name";
      name.textContent = player.username;
      identity.appendChild(name);
      if (uuidEq(lobby.owner_id, player.user_id)) {
        identity.appendChild(badge("Host", "lobby-badge lobby-badge--host"));
      }
      if (uuidEq(player.user_id, uidStr())) identity.appendChild(badge("You", "lobby-badge"));
      if (player.is_bot) identity.appendChild(badge("Bot", "lobby-badge"));
      var status = document.createElement("span");
      status.className = "lobby-player__status lobby-player__status--" + (player.status || "waiting");
      status.textContent = statusLabel(player.status);
      li.appendChild(identity);
      li.appendChild(status);
      playersEl.appendChild(li);
    });
    previousStatuses = nextStatuses;
    playersEmpty.hidden = (lobby.players || []).length > 0;
    playersCount.textContent = max ? seated + " / " + max : String(seated);
    playersCount.setAttribute(
      "aria-label",
      max ? seated + " of " + max + " seats filled" : seated + " seated"
    );
    readyCount.textContent = ready === 1 ? "1 ready" : ready + " ready";
    readyCount.classList.toggle("is-some", ready > 0);
    if (lastReadyCount !== null && lastReadyCount !== ready) markUpdated(readyCount);
    lastReadyCount = ready;
    if (announcements.length) readyLive.textContent = announcements.join(" ");
  }

  function settingsKey(lobby) {
    var settings = lobby.settings || {};
    return [
      settings.max_players,
      settings.card_count,
      settings.is_transferable ? 1 : 0,
      settings.neighbor_throw_only ? 1 : 0,
      settings.allow_jokers ? 1 : 0,
      settings.fill_with_bots ? 1 : 0,
      settings.share_hand_signals === false ? 0 : 1,
      settings.turn_time_limit || 0,
    ].join("|");
  }

  function announceSettingsChange() {
    settingsNotice.hidden = false;
    settingsNotice.textContent = "";
    window.requestAnimationFrame(function () {
      settingsNotice.textContent = "Game settings changed. Readiness was cleared.";
    });
    markUpdated(settingsEl);
  }

  function render(lobby) {
    lastState = lobby;
    var me = findMe(lobby);
    var isOwner = !!(me && uuidEq(lobby.owner_id, uidStr()));
    var waiting = lobby.status === "waiting";
    var closed = lobby.status === "closed";
    var seated = lobby.active_player_count != null ? lobby.active_player_count : (lobby.players || []).length;
    var ready = lobby.ready_count || 0;
    var max = (lobby.settings && lobby.settings.max_players) || 0;
    var currentUserReady = !!(me && me.status === "ready");
    var nextKey = settingsKey(lobby);
    var settingsChanged = lastSettingsKey !== null && nextKey !== lastSettingsKey;
    lastSettingsKey = nextKey;

    titleEl.textContent = lobby.name || "Lobby";
    document.title = titleEl.textContent + " — Fools Arena";
    privateForm.hidden = true;
    fillSettings(lobby, seated);
    if (settingsChanged) announceSettingsChange();
    roster.hidden = false;
    renderPlayers(lobby, seated, ready, max, settingsChanged);
    if (settingsChanged) readyLive.textContent = "";

    joinPrompt.hidden = !!me || closed;
    memberNote.hidden = !me || closed;
    memberNote.textContent = me && !closed ? membershipText(lobby, me, isOwner) : "";

    var hint = startHintText(lobby, isOwner);
    startHint.hidden = !hint || closed;
    startHint.textContent = hint;

    var canEdit = isOwner && waiting && !lobby.active_game_id;
    showAction(joinBtn, joinError, !me && !closed);
    showAction(leaveBtn, leaveError, !!me && !closed);
    showButton(settingsBtn, canEdit);
    showAction(readyBtn, readyError, !!me && waiting);
    showAction(startBtn, startError, isOwner && waiting);
    if (settingsDialog.open && !canEdit) settingsDialog.close();

    if (pending !== "join") joinLabel.textContent = "Join this lobby";
    if (pending !== "settings") settingsLabel.textContent = "Edit settings";
    settingsBtn.disabled = pending === "settings";
    if (pending !== "ready") readyLabel.textContent = currentUserReady ? "Cancel ready" : "Ready";
    if (pending !== "start") startLabel.textContent = "Start game";
    if (pending !== "leave") leaveLabel.textContent = "Leave lobby";

    joinBtn.disabled = pending === "join";
    readyBtn.disabled = pending === "ready";
    readyBtn.classList.toggle("is-ready", currentUserReady);
    readyBtn.setAttribute("aria-pressed", currentUserReady ? "true" : "false");
    startBtn.disabled = pending === "start";
    startBtn.setAttribute("aria-disabled", lobby.can_start ? "false" : "true");
    leaveBtn.disabled = pending === "leave";
    if (hint && isOwner && waiting) startBtn.setAttribute("aria-describedby", "start-hint");
    else startBtn.removeAttribute("aria-describedby");

    var showInvite = !!(lobby.is_private && me && !closed);
    invite.hidden = !showInvite;
    if (showInvite) {
      inviteUrl.value = window.location.href;
      invitePassword.hidden = !isOwner;
      if (isOwner) {
        invitePassword.textContent = "The password cannot be shown again. Send guests the password you chose when you created this lobby.";
        inviteLead.textContent = "This lobby is hidden from the public list. Share the link below.";
      } else {
        inviteLead.textContent = "This lobby is hidden from the public list. Share the link. Guests also need the password from the host.";
      }
    }

    actionsEl.innerHTML = "";
    if (lobby.active_game_id && me) {
      var enter = document.createElement("a");
      enter.className = "game-btn game-btn--primary";
      enter.href = "/fools/play/" + lobby.active_game_id + "/";
      enter.textContent = "Enter active game";
      actionsEl.appendChild(enter);
    }
    actionsEl.hidden = !actionsEl.firstChild;
    chatSection.hidden = !me;

    if (closed) setConnection("closed");
    else if (connectionMode === "lost" && me && !liveSocketOpen()) setConnection("lost");
    else setConnection("clear");

    maybeRedirectToActiveGame(lobby);
    ensureLobbyWs();
  }

  function maybeRedirectToActiveGame(lobby) {
    if (navigatedToGame || !profileReady || !lobby.active_game_id) return;
    var me = findMe(lobby);
    if (!me || me.status !== "playing") return;
    if (uuidEq(lobby.owner_id, uidStr())) return;
    navigatedToGame = true;
    window.location.href = "/fools/play/" + lobby.active_game_id + "/";
  }

  function showPrivateJoin(data) {
    setConnection("clear");
    titleEl.textContent = (data && data.name) || "Private lobby";
    document.title = titleEl.textContent + " — Fools Arena";
    settingsNotice.hidden = true;
    settingsEl.hidden = true;
    roster.hidden = true;
    joinPrompt.hidden = true;
    memberNote.hidden = true;
    startHint.hidden = true;
    invite.hidden = true;
    chatSection.hidden = true;
    actionsEl.hidden = true;
    showAction(joinBtn, joinError, false);
    showAction(leaveBtn, leaveError, false);
    showButton(settingsBtn, false);
    showAction(readyBtn, readyError, false);
    showAction(startBtn, startError, false);
    privateForm.hidden = false;
    privatePassword.focus();
  }

  function liveSocketOpen() {
    return !!(lobbyWs && lobbyWs.readyState === WebSocket.OPEN);
  }

  function refresh(forceChat) {
    var reloadChat = !!forceChat || !chatLoaded || connectionMode === "lost";
    return api("GET", API).then(function (lobby) {
      render(lobby);
      if (findMe(lobby) && reloadChat) return loadChat(!chatLoaded);
      return null;
    }).catch(function (error) {
      if (error.data && error.data.code === "password_required") {
        showPrivateJoin(error.data);
        return null;
      }
      setConnection("lost");
      return null;
    });
  }

  function nearBottom(node) {
    return node.scrollHeight - node.scrollTop - node.clientHeight < 48;
  }

  function formatSentAt(value) {
    var date = new Date(value);
    if (isNaN(date.getTime())) return "";
    var time = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    if (date.toDateString() === new Date().toDateString()) return time;
    return date.toLocaleDateString([], { month: "short", day: "numeric" }) + " " + time;
  }

  function messageNode(message) {
    var system = message.kind === "system";
    var line = document.createElement("div");
    line.className = system ? "game-chat-line game-chat-line--system" : "game-chat-line";
    line.setAttribute("data-message-id", String(message.id));
    var meta = document.createElement("p");
    meta.className = "game-chat-line__meta";
    var name = document.createElement("span");
    name.className = "game-chat-line__name";
    name.textContent = system ? "System" : (message.username || "Player");
    meta.appendChild(name);
    var stamp = formatSentAt(message.sent_at);
    if (stamp) {
      var time = document.createElement("time");
      time.dateTime = message.sent_at;
      time.textContent = stamp;
      meta.appendChild(time);
    }
    var body = document.createElement("p");
    body.className = "game-chat-line__body";
    body.textContent = message.content || "";
    line.appendChild(meta);
    line.appendChild(body);
    return line;
  }

  function renderMessages(rows, forceScroll) {
    var stick = !!forceScroll || nearBottom(chatLog);
    var previousTop = chatLog.scrollTop;
    var existing = [];
    chatLog.querySelectorAll("[data-message-id]").forEach(function (node) {
      existing.push(node.getAttribute("data-message-id"));
    });
    var incoming = rows.map(function (row) { return String(row.id); });
    var samePrefix = existing.length > 0 && existing.length <= incoming.length;
    for (var i = 0; samePrefix && i < existing.length; i += 1) {
      if (existing[i] !== incoming[i]) samePrefix = false;
    }
    if (samePrefix) {
      for (var j = existing.length; j < rows.length; j += 1) chatLog.appendChild(messageNode(rows[j]));
    } else {
      chatLog.innerHTML = "";
      rows.forEach(function (row) { chatLog.appendChild(messageNode(row)); });
      if (!stick) chatLog.scrollTop = previousTop;
    }
    if (stick) chatLog.scrollTop = chatLog.scrollHeight;
    syncChatEmpty(rows.length > 0);
    chatLoaded = true;
  }

  function appendMessage(message, forceScroll) {
    if (!message || message.id == null) return;
    var id = String(message.id);
    if (chatLog.querySelector('[data-message-id="' + id + '"]')) return;
    var stick = !!forceScroll || nearBottom(chatLog);
    chatLog.appendChild(messageNode(message));
    syncChatEmpty(true);
    chatLoaded = true;
    if (stick) chatLog.scrollTop = chatLog.scrollHeight;
  }

  function syncChatEmpty(hasMessages) {
    chatEmpty.hidden = hasMessages;
    chatLog.hidden = !hasMessages;
  }

  function loadChat(forceScroll) {
    return api("GET", API + "messages/").then(function (rows) {
      renderMessages(rows || [], !!forceScroll);
      clearError(chatError);
    }).catch(function (error) {
      showError(chatError, errorText(error));
    });
  }

  function closeSocket() {
    window.clearTimeout(reconnectTimer);
    if (!lobbyWs) return;
    var socket = lobbyWs;
    lobbyWs = null;
    try { socket.close(); } catch (ignore) {}
  }

  function disconnectLobbyWs() {
    socketWanted = false;
    closeSocket();
  }

  function ensureLobbyWs() {
    if (!profileReady || !lastState) return;
    var me = findMe(lastState);
    if (!me || lastState.status === "closed") {
      disconnectLobbyWs();
      return;
    }
    socketWanted = true;
    if (lobbyWs && (lobbyWs.readyState === WebSocket.OPEN || lobbyWs.readyState === WebSocket.CONNECTING)) {
      return;
    }
    var proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    var socket = new WebSocket(proto + "//" + window.location.host + "/ws/lobbies/" + lobbyId + "/");
    lobbyWs = socket;
    socket.onopen = function () {
      if (lobbyWs !== socket) return;
      if (connectionMode === "lost") refresh();
      else if (lastState && lastState.status !== "closed") setConnection("clear");
    };
    socket.onmessage = function (event) {
      if (lobbyWs !== socket) return;
      var message = null;
      try { message = JSON.parse(event.data); } catch (ignore) { message = null; }
      if (message && message.event === "lobby_chat" && message.payload) {
        appendMessage(message.payload, false);
        return;
      }
      refresh();
    };
    socket.onclose = function () {
      if (lobbyWs !== socket) return;
      lobbyWs = null;
      if (!socketWanted) return;
      setConnection("lost");
      window.clearTimeout(reconnectTimer);
      reconnectTimer = window.setTimeout(function () {
        if (socketWanted) ensureLobbyWs();
      }, 2000);
    };
  }

  function begin(name) {
    if (pending) return false;
    pending = name;
    return true;
  }

  function doLeave() {
    if (!begin("leave")) return;
    clearError(leaveError);
    leaveBtn.disabled = true;
    leaveBtn.setAttribute("aria-busy", "true");
    leaveLabel.textContent = "Leaving…";
    disconnectLobbyWs();
    api("POST", API + "leave/", {}).then(function () {
      window.location.href = listUrl;
    }).catch(function (error) {
      pending = "";
      leaveBtn.disabled = false;
      leaveBtn.removeAttribute("aria-busy");
      leaveLabel.textContent = "Leave lobby";
      showError(leaveError, errorText(error));
      ensureLobbyWs();
    });
  }

  inviteUrl.addEventListener("focus", function () {
    inviteUrl.select();
  });

  inviteCopy.addEventListener("click", function () {
    var value = inviteUrl.value;
    var done = function () {
      inviteStatus.classList.remove("is-error");
      inviteStatus.textContent = "Link copied.";
      inviteCopy.focus();
    };
    var failed = function () {
      inviteStatus.classList.add("is-error");
      inviteStatus.textContent = "Could not copy automatically. The link is selected, so you can copy it from the keyboard.";
      inviteUrl.focus();
      inviteUrl.select();
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(value).then(done).catch(function () {
        inviteUrl.focus();
        inviteUrl.select();
        try {
          if (document.execCommand("copy")) done();
          else failed();
        } catch (ignore) {
          failed();
        }
      });
      return;
    }
    try {
      if (document.execCommand("copy")) done();
      else failed();
    } catch (ignore) {
      failed();
    }
  });

  privatePassword.addEventListener("input", function () {
    privatePassword.removeAttribute("aria-invalid");
    clearError(privateError);
  });

  privateForm.addEventListener("submit", function (event) {
    event.preventDefault();
    if (!begin("join")) return;
    clearError(privateError);
    privateSubmit.disabled = true;
    privateSubmit.setAttribute("aria-busy", "true");
    privateLabel.textContent = "Joining…";
    api("POST", API + "join/", { password: privatePassword.value }).then(function (lobby) {
      pending = "";
      privateSubmit.disabled = false;
      privateSubmit.removeAttribute("aria-busy");
      privateLabel.textContent = "Join lobby";
      privatePassword.value = "";
      render(lobby);
      return loadChat(true);
    }).catch(function (error) {
      pending = "";
      privateSubmit.disabled = false;
      privateSubmit.removeAttribute("aria-busy");
      privateLabel.textContent = "Join lobby";
      privatePassword.setAttribute("aria-invalid", "true");
      showError(privateError, errorText(error));
      privatePassword.focus();
    });
  });

  joinBtn.addEventListener("click", function () {
    if (!begin("join")) return;
    clearError(joinError);
    joinBtn.disabled = true;
    joinBtn.setAttribute("aria-busy", "true");
    joinLabel.textContent = "Joining…";
    api("POST", API + "join/", {}).then(function (lobby) {
      pending = "";
      joinBtn.removeAttribute("aria-busy");
      render(lobby);
      return loadChat(true);
    }).catch(function (error) {
      pending = "";
      joinBtn.disabled = false;
      joinBtn.removeAttribute("aria-busy");
      joinLabel.textContent = "Join this lobby";
      showError(joinError, errorText(error));
    });
  });

  leaveBtn.addEventListener("click", function () {
    clearError(leaveError);
    if (!lastState) return;
    var me = findMe(lastState);
    var isOwner = !!(me && uuidEq(lastState.owner_id, uidStr()));
    if (me && (me.status === "ready" || me.status === "playing" || isOwner)) {
      leaveText.textContent = leaveWarning(lastState, me, isOwner);
      if (typeof leaveDialog.showModal === "function") {
        leaveDialog.showModal();
        return;
      }
    }
    doLeave();
  });

  leaveDialog.addEventListener("close", function () {
    if (leaveDialog.returnValue === "leave") doLeave();
    else leaveBtn.focus();
  });

  readyBtn.addEventListener("click", function () {
    if (!lastState || !begin("ready")) return;
    clearError(readyError);
    var me = findMe(lastState);
    var nextReady = !(me && me.status === "ready");
    readyBtn.disabled = true;
    readyBtn.setAttribute("aria-busy", "true");
    readyLabel.textContent = "Updating…";
    api("POST", API + "ready/", { ready: nextReady }).then(function (lobby) {
      pending = "";
      readyBtn.removeAttribute("aria-busy");
      render(lobby);
    }).catch(function (error) {
      pending = "";
      readyBtn.removeAttribute("aria-busy");
      showError(readyError, errorText(error));
      if (lastState) render(lastState);
    });
  });

  startBtn.addEventListener("click", function () {
    if (startBtn.getAttribute("aria-disabled") === "true") return;
    if (!begin("start")) return;
    clearError(startError);
    startBtn.disabled = true;
    startBtn.setAttribute("aria-busy", "true");
    startLabel.textContent = "Starting…";
    api("POST", API + "start/", {}).then(function (game) {
      navigatedToGame = true;
      window.location.href = "/fools/play/" + game.id + "/";
    }).catch(function (error) {
      pending = "";
      startBtn.removeAttribute("aria-busy");
      showError(startError, errorText(error));
      if (lastState) render(lastState);
    });
  });

  chatInput.addEventListener("input", function () {
    chatInput.removeAttribute("aria-invalid");
  });

  chatForm.addEventListener("submit", function (event) {
    event.preventDefault();
    if (pending || chatSection.hidden) return;
    var draft = chatInput.value;
    var content = draft.trim();
    if (!content) return;
    pending = "chat";
    clearError(chatError);
    chatSend.disabled = true;
    chatSend.setAttribute("aria-busy", "true");
    chatSendLabel.textContent = "Sending…";
    api("POST", API + "messages/", { content: content }).then(function (created) {
      pending = "";
      chatSend.disabled = false;
      chatSend.removeAttribute("aria-busy");
      chatSendLabel.textContent = "Send";
      if (chatInput.value === draft) chatInput.value = "";
      appendMessage(created, true);
      chatInput.focus();
    }).catch(function (error) {
      pending = "";
      chatSend.disabled = false;
      chatSend.removeAttribute("aria-busy");
      chatSendLabel.textContent = "Send";
      chatInput.setAttribute("aria-invalid", "true");
      showError(chatError, errorText(error));
      chatInput.focus();
    });
  });

  function settingsBody() {
    return {
      max_players: Number(settingsPlayers.value),
      card_count: Number(settingsDeck.value),
      neighbor_throw_only: settingsNeighbors.checked,
      is_transferable: settingsTransfer.checked,
      fill_with_bots: settingsBots.checked,
      share_hand_signals: settingsSignals.checked,
    };
  }

  function sameSettings(lobby, body) {
    var settings = (lobby && lobby.settings) || {};
    return Number(settings.max_players) === body.max_players &&
      Number(settings.card_count) === body.card_count &&
      !!settings.neighbor_throw_only === body.neighbor_throw_only &&
      !!settings.is_transferable === body.is_transferable &&
      !!settings.fill_with_bots === body.fill_with_bots &&
      (settings.share_hand_signals !== false) === body.share_hand_signals;
  }

  function syncSettingsDeck() {
    var players = Number(settingsPlayers.value);
    var cards = Number(settingsDeck.value);
    var limit = Math.floor(cards / OPENING_HAND);
    var hint = document.getElementById("settings-max-players-hint");
    if (hint && limit >= 2) {
      hint.textContent = "2–" + Math.min(8, limit) + " for this deck. Each player is dealt 6 cards.";
    }
    if (limit >= 2) settingsPlayers.max = String(Math.min(8, limit));
    if (!players || !cards || players <= limit) {
      var slot = document.getElementById("settings-card-count-error");
      if (slot && slot.getAttribute("data-deck-fit") === "1") {
        setSettingsFieldError("card_count", "");
        slot.removeAttribute("data-deck-fit");
      }
      return true;
    }
    setSettingsFieldError(
      "card_count",
      "A " + cards + "-card deck deals 6 cards to each player, so it seats at most " + limit + "."
    );
    document.getElementById("settings-card-count-error").setAttribute("data-deck-fit", "1");
    return false;
  }

  function setSettingsFieldError(name, message) {
    var field = settingsForm.querySelector('[data-field="' + name + '"]');
    if (!field) {
      setSettingsFormError(message);
      return;
    }
    var input = field.querySelector("input, select");
    var slot = field.querySelector(".lobby-field__error");
    if (!slot) {
      setSettingsFormError(message);
      return;
    }
    if (!message) {
      field.classList.remove("is-invalid");
      if (input) input.removeAttribute("aria-invalid");
      if (slot) {
        slot.hidden = true;
        slot.textContent = "";
      }
      return;
    }
    field.classList.add("is-invalid");
    if (input) input.setAttribute("aria-invalid", "true");
    if (slot) {
      slot.hidden = false;
      slot.textContent = message;
    }
  }

  function setSettingsFormError(message) {
    settingsFormError.hidden = !message;
    settingsFormError.textContent = message || "";
  }

  function clearSettingsErrors() {
    settingsForm.querySelectorAll(".is-invalid").forEach(function (field) {
      field.classList.remove("is-invalid");
    });
    settingsForm.querySelectorAll("[aria-invalid]").forEach(function (input) {
      input.removeAttribute("aria-invalid");
    });
    settingsForm.querySelectorAll(".lobby-field__error").forEach(function (slot) {
      slot.hidden = true;
      slot.textContent = "";
    });
  }

  function settingsMessageOf(value) {
    if (Array.isArray(value)) return value.join(" ");
    if (value && typeof value === "object") return value.detail || "Could not save the settings.";
    return value ? String(value) : "Could not save the settings.";
  }

  function applySettingsErrors(data) {
    clearSettingsErrors();
    if (!data || typeof data !== "object") {
      setSettingsFormError(settingsMessageOf(data));
      return;
    }
    var placed = false;
    Object.keys(data).forEach(function (key) {
      if (key === "detail" || key === "code" || key === "non_field_errors") return;
      setSettingsFieldError(key, settingsMessageOf(data[key]));
      placed = true;
    });
    if (data.non_field_errors) {
      setSettingsFormError(settingsMessageOf(data.non_field_errors));
      placed = true;
    }
    if (!placed && data.detail) setSettingsFormError(settingsMessageOf(data.detail));
    var first = settingsForm.querySelector(".is-invalid input, .is-invalid select, #settings-form-error:not([hidden])");
    if (first && first.focus) first.focus();
  }

  function fillSettingsForm(lobby) {
    var settings = (lobby && lobby.settings) || {};
    settingsPlayers.value = settings.max_players || 4;
    settingsDeck.value = String(settings.card_count || 36);
    settingsNeighbors.checked = !!settings.neighbor_throw_only;
    settingsTransfer.checked = !!settings.is_transferable;
    settingsBots.checked = !!settings.fill_with_bots;
    settingsSignals.checked = settings.share_hand_signals !== false;
    syncSettingsDeck();
  }

  function openSettings() {
    if (!lastState || pending) return;
    clearSettingsErrors();
    fillSettingsForm(lastState);
    if (typeof settingsDialog.showModal === "function") settingsDialog.showModal();
    else settingsDialog.setAttribute("open", "");
    settingsPlayers.focus();
  }

  settingsBtn.addEventListener("click", openSettings);

  settingsCancel.addEventListener("click", function () {
    settingsDialog.close();
  });

  settingsDialog.addEventListener("close", function () {
    if (settingsBtn && !settingsBtn.hidden && !settingsBtn.closest(".lobby-action").hidden) {
      settingsBtn.focus();
    }
  });

  [settingsPlayers, settingsDeck].forEach(function (input) {
    input.addEventListener("input", syncSettingsDeck);
    input.addEventListener("change", syncSettingsDeck);
  });

  settingsForm.addEventListener("submit", function (event) {
    event.preventDefault();
    if (!lastState || !begin("settings")) return;
    clearSettingsErrors();
    if (!syncSettingsDeck()) {
      pending = "";
      settingsDeck.focus();
      return;
    }
    var body = settingsBody();
    if (sameSettings(lastState, body)) {
      pending = "";
      setSettingsFormError("Those settings are already in use.");
      settingsSave.focus();
      return;
    }
    settingsSave.disabled = true;
    settingsSave.setAttribute("aria-busy", "true");
    settingsSaveLabel.textContent = "Saving…";
    api("PATCH", API + "settings/", body).then(function (lobby) {
      pending = "";
      settingsSave.disabled = false;
      settingsSave.removeAttribute("aria-busy");
      settingsSaveLabel.textContent = "Save settings";
      settingsDialog.close("saved");
      render(lobby);
    }).catch(function (error) {
      pending = "";
      settingsSave.disabled = false;
      settingsSave.removeAttribute("aria-busy");
      settingsSaveLabel.textContent = "Save settings";
      applySettingsErrors(error.data || { detail: errorText(error) });
    });
  });

  retryBtn.addEventListener("click", function () {
    window.clearTimeout(reconnectTimer);
    closeSocket();
    setConnection("connecting");
    refresh(true);
  });

  window.addEventListener("pagehide", function () {
    disconnectLobbyWs();
  });

  setConnection("connecting");
  api("GET", PROFILE).then(function (user) {
    profile = user;
    profileReady = true;
    return refresh();
  }).catch(function () {
    setConnection("lost");
  });
})();
