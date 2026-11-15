/**
 * Direct-chat room: one composer, live delivery, and older history on scroll.
 */
(function () {
  "use strict";

  var room = document.getElementById("chat-room");
  var log = document.getElementById("chat-log");
  var form = document.getElementById("chat-form");
  var input = document.getElementById("chat-input");
  var send = document.getElementById("chat-send");
  var error = document.getElementById("chat-error");
  var status = document.getElementById("chat-connection");
  if (!room || !log || !form || !input || !window.FoolsChat) return;

  var chatId = room.getAttribute("data-chat-id");
  var selfId = room.getAttribute("data-self-id") || "";
  var finding = room.getAttribute("data-find") || "";
  var messagesUrl = "/api/chat/chats/" + chatId + "/messages/";
  var thread = window.FoolsChat.bind({
    log: log,
    jump: document.getElementById("chat-jump"),
    input: input,
    selfId: selfId,
    hasOlder: room.getAttribute("data-has-older") === "1",
    chatId: chatId,
    onCount: function (count) {
      var hint = document.getElementById("chat-empty-hint");
      if (hint) hint.hidden = count > 0;
    },
    onSeen: function (message) {
      if (finding) return;
      window.FoolsChat.markRead(chatId, message && message.id);
    },
    fetchOlder: function (beforeId) {
      var query = "before=" + encodeURIComponent(beforeId) + "&limit=40&envelope=1";
      if (finding) query += "&q=" + encodeURIComponent(finding);
      return fetch(
        messagesUrl + "?" + query,
        { credentials: "same-origin" }
      ).then(function (response) {
        if (!response.ok) throw new Error("Could not load earlier messages.");
        return response.json();
      }).then(function (page) {
        return { messages: page.results || [], has_older: !!page.has_older };
      });
    },
  });

  function csrf() {
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function setStatus(text, live) {
    if (!status) return;
    status.textContent = text;
    status.hidden = !!live || !text;
    status.classList.toggle("is-live", !!live);
    status.classList.toggle("is-down", !live && !!text);
  }

  function showError(text) {
    if (!error) return;
    if (!text) {
      error.hidden = true;
      error.textContent = "";
      input.removeAttribute("aria-invalid");
      return;
    }
    error.hidden = false;
    error.textContent = text;
    input.setAttribute("aria-invalid", "true");
  }

  var socket = null;
  var wanted = true;
  var retries = 0;
  var token = 0;
  var reconnectTimer = 0;

  function connect() {
    var current = ++token;
    if (retries) setStatus("Reconnecting…", false);
    var proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    var next = new WebSocket(proto + "//" + window.location.host + "/ws/chat/" + chatId + "/");
    socket = next;
    next.onopen = function () {
      if (socket !== next) return;
      retries = 0;
      setStatus("", true);
    };
    next.onmessage = function (event) {
      if (socket !== next) return;
      var data = null;
      try { data = JSON.parse(event.data); } catch (ignore) { data = null; }
      if (!data) return;
      if (data.type === "last_messages" && Array.isArray(data.messages)) {
        data.messages.forEach(function (row) { thread.append(row, false); });
        return;
      }
      if (data.type === "error") {
        showError(data.detail || "Could not send.");
        return;
      }
      if (data.id && data.content !== undefined) {
        var mine = String(data.sender_id || "") === selfId;
        if (thread.append(data, mine)) touchOpenChat(data, mine);
      }
    };
    next.onclose = function () {
      if (socket !== next) return;
      socket = null;
      if (!wanted) return;
      setStatus("Reconnecting…", false);
      var delay = Math.min(10000, 800 * Math.pow(2, Math.min(retries, 4)));
      retries += 1;
      window.clearTimeout(reconnectTimer);
      reconnectTimer = window.setTimeout(function () {
        if (wanted && current === token) connect();
      }, delay);
    };
  }

  function sendHttp(text) {
    if (send) {
      send.disabled = true;
      send.setAttribute("aria-busy", "true");
    }
    return fetch(messagesUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf(),
      },
      body: JSON.stringify({ content: text }),
    }).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok) {
          var failure = new Error((data && data.detail) || "Could not send.");
          failure.data = data;
          throw failure;
        }
        return data;
      });
    }).then(function (message) {
      input.value = "";
      showError("");
      thread.append(message, true);
      touchOpenChat(message, true);
      input.focus();
    }).catch(function (failure) {
      showError(failure.message || "Could not send.");
      input.focus();
    }).then(function () {
      if (send) {
        send.disabled = false;
        send.removeAttribute("aria-busy");
      }
    });
  }

  function previewText(content) {
    var text = String(content || "").replace(/\s+/g, " ").trim();
    if (text.length <= 90) return text;
    return text.slice(0, 89).replace(/\s+$/, "") + "…";
  }

  function touchOpenChat(message, mine) {
    var list = document.querySelector(".chat-inbox-list");
    if (!list || finding) return;
    var link = list.querySelector('a[aria-current="page"]');
    if (!link) return;
    var preview = link.querySelector(".chat-inbox-list__preview");
    var meta = link.querySelector(".chat-inbox-list__meta");
    var kind = message.kind || "user";
    if (preview) {
      var text = previewText(message.content);
      preview.classList.toggle("is-system", kind === "system");
      if (kind === "system") preview.textContent = "System: " + text;
      else if (mine) preview.textContent = "You: " + text;
      else preview.textContent = text;
    }
    if (meta && message.sent_at && window.FoolsChat) {
      var time = meta.querySelector("time");
      if (!time) {
        time = document.createElement("time");
        meta.appendChild(time);
      }
      time.dateTime = message.sent_at;
      time.textContent = window.FoolsChat.formatSentAt(message.sent_at);
    }
    var item = link.parentNode;
    if (list.getAttribute("data-sort") === "activity" && item && item.parentNode === list) {
      list.insertBefore(item, list.firstChild);
    }
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var text = (input.value || "").trim();
    if (!text) return;
    showError("");
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ message: text }));
      input.value = "";
      input.focus();
      return;
    }
    sendHttp(text);
  });

  window.requestAnimationFrame(function () {
    if (finding) {
      log.scrollTop = 0;
      return;
    }
    thread.scrollToEnd();
    connect();
  });
})();
