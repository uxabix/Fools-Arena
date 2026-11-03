/**
 * Shared chat history: grouping, stick-to-bottom, older pages, and read marks.
 * Direct chats, the lobby, and the table all use this so those parts match.
 */
(function () {
  "use strict";

  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var GROUP_MS = 5 * 60 * 1000;
  var readTimer = 0;
  var readPending = null;

  function pad(value) {
    return value < 10 ? "0" + value : String(value);
  }

  function formatSentAt(value) {
    var date = new Date(value);
    if (isNaN(date.getTime())) return "";
    var time = pad(date.getHours()) + ":" + pad(date.getMinutes());
    var now = new Date();
    if (date.toDateString() === now.toDateString()) return time;
    var stamp = MONTHS[date.getMonth()] + " " + date.getDate();
    if (date.getFullYear() !== now.getFullYear()) stamp += ", " + date.getFullYear();
    return stamp + " " + time;
  }

  function csrf() {
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function profileHref(name) {
    if (!name || !/^[A-Za-z0-9_]{3,30}$/.test(name)) return "";
    return "/accounts/players/" + encodeURIComponent(name) + "/";
  }

  function normalize(message) {
    var kind = message.kind || "user";
    var name = kind === "system" ? "System" : (message.username || message.sender || "Player");
    return {
      id: message.id == null ? "" : String(message.id),
      senderId: message.sender_id == null ? "" : String(message.sender_id),
      name: name,
      kind: kind,
      sent: message.sent_at || "",
      content: message.content || "",
    };
  }

  function selfId(options) {
    if (typeof options.selfId === "function") return String(options.selfId() || "");
    return String(options.selfId || "");
  }

  function findLine(log, id) {
    var key = String(id);
    var rows = log.querySelectorAll("[data-message-id]");
    for (var i = 0; i < rows.length; i += 1) {
      if (rows[i].getAttribute("data-message-id") === key) return rows[i];
    }
    return null;
  }

  function createLine(message, options) {
    var row = normalize(message);
    var mine = row.kind !== "system" && row.senderId && row.senderId === selfId(options);
    var line = document.createElement("div");
    line.className = "game-chat-line";
    if (row.kind === "system") line.classList.add("game-chat-line--system");
    else if (mine) line.classList.add("is-mine");
    line.setAttribute("data-message-id", row.id);
    line.setAttribute("data-sender-id", row.senderId);
    line.setAttribute("data-sent-at", row.sent);
    line.setAttribute("data-kind", row.kind);
    var meta = document.createElement("p");
    meta.className = "game-chat-line__meta";
    var name;
    var href = row.kind === "system" ? "" : profileHref(row.name);
    if (href) {
      name = document.createElement("a");
      name.href = href;
    } else {
      name = document.createElement("span");
    }
    name.className = "game-chat-line__name";
    name.textContent = row.name;
    meta.appendChild(name);
    if (row.sent) {
      var time = document.createElement("time");
      time.dateTime = row.sent;
      time.textContent = formatSentAt(row.sent);
      meta.appendChild(time);
    }
    var body = document.createElement("p");
    body.className = "game-chat-line__body";
    body.textContent = row.content;
    line.appendChild(meta);
    line.appendChild(body);
    return line;
  }

  function paintGroups(log) {
    var previous = null;
    log.querySelectorAll("[data-message-id]").forEach(function (line) {
      var kind = line.getAttribute("data-kind") || "user";
      var name = line.querySelector(".game-chat-line__name");
      line.classList.remove("is-grouped");
      if (name) name.classList.remove("visually-hidden");
      var sent = new Date(line.getAttribute("data-sent-at") || "");
      var sender = line.getAttribute("data-sender-id") || "";
      var grouped = previous
        && kind !== "system"
        && previous.kind !== "system"
        && sender
        && sender === previous.sender
        && !isNaN(sent.getTime())
        && !isNaN(previous.sent.getTime())
        && sent.getTime() - previous.sent.getTime() < GROUP_MS
        && sent.getTime() >= previous.sent.getTime();
      if (grouped) {
        line.classList.add("is-grouped");
        if (name) name.classList.add("visually-hidden");
      }
      previous = { kind: kind, sender: sender, sent: sent };
    });
  }

  function nearBottom(log) {
    return log.scrollHeight - log.scrollTop - log.clientHeight < 48;
  }

  function following(options, log) {
    if (typeof options.isFollowing === "function" && !options.isFollowing()) return false;
    return nearBottom(log);
  }

  function lineCount(log) {
    return log.querySelectorAll("[data-message-id]").length;
  }

  function oldestId(log) {
    var first = log.querySelector("[data-message-id]");
    return first ? first.getAttribute("data-message-id") : "";
  }

  function newestLine(log) {
    var rows = log.querySelectorAll("[data-message-id]");
    return rows.length ? rows[rows.length - 1] : null;
  }

  function newestPayload(log) {
    var line = newestLine(log);
    if (!line) return null;
    return { id: line.getAttribute("data-message-id") };
  }

  /**
   * Attach scroll, grouping, and the new-messages control to one log.
   * @param {Object} options
   * @return {Object}
   */
  function bind(options) {
    var log = options.log;
    var jump = options.jump || null;
    var hasOlder = !!options.hasOlder;
    var loading = false;
    var unseen = 0;

    function notifyCount() {
      if (options.onCount) options.onCount(lineCount(log));
    }

    function paintJump() {
      if (!jump) return;
      if (!unseen) {
        jump.hidden = true;
        jump.textContent = "New messages";
        return;
      }
      jump.hidden = false;
      jump.textContent = "New messages";
      jump.setAttribute(
        "aria-label",
        unseen === 1 ? "1 new message" : unseen + " new messages"
      );
    }

    function clearUnseen() {
      unseen = 0;
      paintJump();
      if (options.onUnseen) options.onUnseen(0);
    }

    function bumpUnseen() {
      unseen += 1;
      paintJump();
      if (options.onUnseen) options.onUnseen(unseen);
    }

    function seenNewest() {
      var payload = newestPayload(log);
      if (payload && options.onSeen) options.onSeen(payload);
    }

    function scrollToEnd() {
      log.scrollTop = log.scrollHeight;
      clearUnseen();
      seenNewest();
    }

    function append(message, force) {
      var row = normalize(message);
      if (!row.id || findLine(log, row.id)) return false;
      var stick = !!force || following(options, log);
      log.appendChild(createLine(message, options));
      paintGroups(log);
      notifyCount();
      if (stick) {
        log.scrollTop = log.scrollHeight;
        clearUnseen();
        if (options.onSeen) options.onSeen(row);
      } else {
        bumpUnseen();
      }
      return true;
    }

    function prepend(messages) {
      var previousHeight = log.scrollHeight;
      var previousTop = log.scrollTop;
      var fragment = document.createDocumentFragment();
      (messages || []).forEach(function (message) {
        var row = normalize(message);
        if (!row.id || findLine(log, row.id)) return;
        fragment.appendChild(createLine(message, options));
      });
      var anchor = log.firstChild;
      if (anchor) log.insertBefore(fragment, anchor);
      else log.appendChild(fragment);
      paintGroups(log);
      log.scrollTop = log.scrollHeight - previousHeight + previousTop;
      notifyCount();
    }

    function replace(messages) {
      while (log.firstChild) log.removeChild(log.firstChild);
      (messages || []).forEach(function (message) {
        var row = normalize(message);
        if (!row.id) return;
        log.appendChild(createLine(message, options));
      });
      paintGroups(log);
      notifyCount();
    }

    function noteCatchUp(rows) {
      log.scrollTop = log.scrollHeight;
      if (!rows.length) return;
      unseen = rows.length;
      paintJump();
      if (options.onUnseen) options.onUnseen(unseen);
    }

    function syncLatest(messages, older, forceScroll) {
      var newest = newestLine(log);
      var rows = messages || [];
      var stick = !!forceScroll || following(options, log);
      if (!newest) {
        replace(rows);
        hasOlder = !!older;
        if (stick) scrollToEnd();
        else noteCatchUp(rows);
        return;
      }
      var known = -1;
      var current = newest.getAttribute("data-message-id");
      for (var i = 0; i < rows.length; i += 1) {
        if (String(rows[i].id) === current) known = i;
      }
      if (known === -1) {
        replace(rows);
        hasOlder = !!older;
        if (stick) scrollToEnd();
        else noteCatchUp(rows);
        return;
      }
      for (var j = known + 1; j < rows.length; j += 1) append(rows[j], !!forceScroll);
    }

    function loadOlder() {
      if (loading || !hasOlder || !options.fetchOlder) return;
      if (typeof options.isFollowing === "function" && !options.isFollowing()) return;
      if (log.scrollTop > 48) return;
      var before = oldestId(log);
      if (!before) return;
      loading = true;
      log.setAttribute("aria-busy", "true");
      options.fetchOlder(before).then(function (page) {
        loading = false;
        log.removeAttribute("aria-busy");
        if (!page) return;
        hasOlder = !!page.has_older;
        prepend(page.messages || []);
      }).catch(function () {
        loading = false;
        log.removeAttribute("aria-busy");
      });
    }

    log.addEventListener("scroll", function () {
      if (following(options, log)) {
        clearUnseen();
        seenNewest();
      }
      loadOlder();
    });

    if (jump) {
      jump.addEventListener("click", function () {
        scrollToEnd();
        if (options.input) options.input.focus();
      });
    }

    paintGroups(log);
    notifyCount();

    return {
      append: append,
      prepend: prepend,
      replace: replace,
      syncLatest: syncLatest,
      scrollToEnd: scrollToEnd,
      setHasOlder: function (value) { hasOlder = !!value; },
      unseen: function () { return unseen; },
      setChatId: function (id) { options.chatId = id; },
      chatId: function () { return options.chatId || ""; },
    };
  }

  function markRead(chatId, messageId) {
    if (!chatId || !messageId) return;
    readPending = { chatId: String(chatId), messageId: String(messageId) };
    window.clearTimeout(readTimer);
    readTimer = window.setTimeout(function () {
      var pending = readPending;
      readPending = null;
      if (!pending) return;
      fetch("/api/chat/chats/" + pending.chatId + "/read/", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrf(),
        },
        body: JSON.stringify({ message_id: pending.messageId }),
      }).catch(function () {});
    }, 400);
  }

  window.FoolsChat = {
    formatSentAt: formatSentAt,
    bind: bind,
    markRead: markRead,
    paintGroups: paintGroups,
  };
})();
