/**
 * Durak table: SVG cards, opponents, felt, deck and trump.
 * Cards can be dragged, or selected and played with a button, the keyboard, or a table target.
 * dataTransfer is mirrored to text/plain for browsers with limited custom MIME support.
 */
(function () {
  "use strict";

  var parts = location.pathname.split("/").filter(Boolean);
  var gameId = parts[parts.length - 1];
  var BASE = "/api/fools/games/" + gameId + "/";

  var state = null;
  var profile = null;
  var activeBadge = null;
  var pendingClear = null;
  var refreshChain = Promise.resolve();
  /** @type {Set<string>} */
  var selected = new Set();

  var SUIT_SYMBOL = {
    Hearts: "\u2665",
    Diamonds: "\u2666",
    Clubs: "\u2663",
    Spades: "\u2660",
  };

  function rankShort(rank) {
    var m = {
      Ace: "A",
      King: "K",
      Queen: "Q",
      Jack: "J",
      Ten: "10",
      Nine: "9",
      Eight: "8",
      Seven: "7",
      Six: "6",
      Five: "5",
      Four: "4",
      Three: "3",
      Two: "2",
    };
    return m[rank] || rank;
  }

  function suitNameEn(suit) {
    var m = { Hearts: "hearts", Diamonds: "diamonds", Clubs: "clubs", Spades: "spades" };
    return m[suit] || suit;
  }

  function phaseEn(phase) {
    var m = {
      between: "Opening attack",
      build: "Attack and defense",
      defend: "Defense",
      taking: "Taking",
    };
    return m[phase] || phase || "—";
  }

  function modeLabel() {
    var name = state && state.transferable ? "Transfer" : "Throw-in";
    if (state && state.neighbor_throw_only) name += ", neighbors only";
    return name;
  }

  /** Catalog ranks are "6" and "10". Word names are accepted too. */
  var CARD_RANK_FILE = {
    Ace: "ace",
    King: "king",
    Queen: "queen",
    Jack: "jack",
    Ten: "10",
    "10": "10",
    Nine: "9",
    "9": "9",
    Eight: "8",
    "8": "8",
    Seven: "7",
    "7": "7",
    Six: "6",
    "6": "6",
    Five: "5",
    "5": "5",
    Four: "4",
    "4": "4",
    Three: "3",
    "3": "3",
    Two: "2",
    "2": "2",
  };

  function cardAsset(file) {
    var base = window.FOOLS_CARD_BASE || "/static/fools/cards/";
    return base + file;
  }

  function cardImageHTML(src, extraClass) {
    return '<img class="play-card-svg' + (extraClass ? " " + extraClass : "") +
      '" src="' + src + '" alt="" draggable="false">';
  }

  /**
   * Face art is a public-domain SVG. See README, Card artwork.
   * @param {{rank:string,suit:string}} card
   */
  function cardSvgOuterHTML(card) {
    var rank = CARD_RANK_FILE[card.rank];
    var suit = String(card.suit || "").toLowerCase();
    if (!rank || !suit) return cardBackSvgHTML();
    return cardImageHTML(cardAsset(rank + "-" + suit + ".svg"), "");
  }

  function cardBackSvgHTML() {
    return cardImageHTML(cardAsset("back.svg"), "play-card-svg--back");
  }

  function setDragCardIds(ev, ids) {
    var json = JSON.stringify(ids);
    try {
      ev.dataTransfer.setData("application/x-card-ids", json);
    } catch (_) {}
    ev.dataTransfer.setData("text/plain", json);
  }

  function getDragCardIds(ev) {
    var raw = "";
    try {
      raw = ev.dataTransfer.getData("application/x-card-ids");
    } catch (_) {}
    if (!raw) raw = ev.dataTransfer.getData("text/plain");
    if (!raw) return null;
    try {
      var ids = JSON.parse(raw);
      return Array.isArray(ids) ? ids : null;
    } catch (_) {
      return null;
    }
  }

  function csrf() {
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  function api(method, url, body) {
    var opts = { method: method, credentials: "same-origin", headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.headers["X-CSRFToken"] = csrf();
      opts.body = JSON.stringify(body);
    }
    return fetch(url, opts).then(function (r) {
      return r.text().then(function (t) {
        var data;
        try {
          data = t ? JSON.parse(t) : null;
        } catch (_) {
          data = t;
        }
        if (!r.ok) throw new Error((data && data.detail) || r.statusText || String(r.status));
        return data;
      });
    });
  }

  function setErr(msg) {
    var el = document.getElementById("err");
    if (el) el.textContent = msg || "";
  }

  function uidStr() {
    return profile && profile.id != null ? String(profile.id) : "";
  }

  function pruneSelection(hand) {
    if (!hand || !hand.length) {
      selected.clear();
      return;
    }
    var ok = new Set(hand.map(function (c) { return c.id; }));
    selected.forEach(function (id) {
      if (!ok.has(id)) selected.delete(id);
    });
  }

  function attackPayloadFromDrag(cardId) {
    if (selected.has(cardId) && selected.size > 0) {
      return Array.from(selected);
    }
    return [cardId];
  }

  /** Opponents in clockwise seat order, starting with the seat after the viewer. */
  function otherPlayers(uid) {
    var circle = state.players.slice().sort(function (a, b) {
      return a.seat_position - b.seat_position;
    });
    var index = circle.findIndex(function (p) {
      return String(p.user_id) === uid;
    });
    if (index < 0) {
      return circle.filter(function (p) {
        return String(p.user_id) !== uid;
      });
    }
    var ordered = [];
    for (var step = 1; step < circle.length; step++) {
      ordered.push(circle[(index + step) % circle.length]);
    }
    return ordered;
  }

  function playerCircle() {
    return (state.players || []).slice().sort(function (a, b) {
      return a.seat_position - b.seat_position;
    });
  }

  function throwNeighborIds(rt) {
    var ids = {};
    if (!state || !state.neighbor_throw_only || !rt || rt.defender_id == null) return ids;
    var circle = playerCircle();
    var index = circle.findIndex(function (row) {
      return String(row.user_id) === String(rt.defender_id);
    });
    if (index < 0 || circle.length < 2) return ids;
    ids[String(circle[(index + 1) % circle.length].user_id)] = true;
    ids[String(circle[(index - 1 + circle.length) % circle.length].user_id)] = true;
    return ids;
  }

  function playerRoleKey(playerId, rt) {
    if (!rt || state.status !== "in_progress") return "wait";
    var player = (state.players || []).find(function (row) {
      return String(row.user_id) === String(playerId);
    });
    if (isOutOfCards(player) && String(rt.defender_id) !== String(playerId) && String(rt.attacker_id) !== String(playerId)) {
      return "out";
    }
    if (isOutOfCards(player) && rt.phase === "between") return "out";
    if (String(rt.attacker_id) === String(playerId)) return "attack";
    if (String(rt.defender_id) === String(playerId)) return "defend";
    if (isOutOfCards(player)) return "out";
    return "throw";
  }

  function roleLabel(key) {
    if (key === "attack") return "Attacking";
    if (key === "defend") return "Defending";
    if (key === "throw") return "Throwing in";
    if (key === "out") return "Out";
    return "Waiting";
  }

  function roleIcon(key) {
    if (key === "attack") {
      return '<svg viewBox="0 0 24 24" aria-hidden="true"><polyline points="14.5 17.5 3 6 3 3 6 3 17.5 14.5"/><line x1="13" y1="19" x2="19" y2="13"/><line x1="16" y1="16" x2="20" y2="20"/><line x1="19" y1="21" x2="21" y2="19"/></svg>';
    }
    if (key === "defend") {
      return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 19 6v6.2c0 4.2-2.8 7.2-7 8.3-4.2-1.1-7-4.1-7-8.3V6z"/></svg>';
    }
    if (key === "throw") {
      return '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="2.5" y="5" width="9" height="14" rx="1.4"/><path d="M14 12h6"/><path d="M17.5 8.5 21.5 12 17.5 15.5"/></svg>';
    }
    return "";
  }

  function seatCards(playerId) {
    var player = (state.players || []).find(function (row) {
      return String(row.user_id) === String(playerId);
    });
    return player && player.cards_remaining != null ? player.cards_remaining : 0;
  }

  function isOutOfCards(player) {
    return (
      state &&
      state.status === "in_progress" &&
      player &&
      (player.cards_remaining || 0) === 0 &&
      (state.deck_remaining || 0) === 0
    );
  }

  function expectedActorId(rt) {
    if (!rt || state.status !== "in_progress") return null;
    if (rt.phase === "taking") return null;
    var table = state.table || [];
    var open = table.filter(function (row) { return !row.defense; }).length;
    var actor = rt.attacker_id;
    if (rt.phase !== "between" && open > 0) actor = rt.defender_id;
    else if (rt.phase !== "between" && table.length) actor = rt.attacker_id;
    if (rt.phase === "between" && seatCards(actor) === 0) return null;
    return actor;
  }

  function hasPassed(playerId, rt) {
    return !!rt && (rt.passed_ids || []).some(function (id) {
      return String(id) === String(playerId);
    });
  }

  function playerMustAct(playerId, rt) {
    if (!rt || !state || state.status !== "in_progress") return false;
    if (rt.phase === "taking") return mustConfirm(playerId, rt);
    var actor = expectedActorId(rt);
    return actor != null && String(actor) === String(playerId);
  }

  function dutyText(playerId, rt) {
    var roleKey = playerRoleKey(playerId, rt);
    if (roleKey === "out") return "Out";
    if (rt && rt.phase === "taking" && String(rt.defender_id) === String(playerId)) {
      return "Taking — waiting";
    }
    if (rt && hasPassed(playerId, rt)) return "Finished throwing";
    if (playerMustAct(playerId, rt)) return "Playing";
    return "Waiting";
  }

  function nameOf(playerId) {
    var player = (state.players || []).find(function (row) {
      return String(row.user_id) === String(playerId);
    });
    return player ? player.username : "the player";
  }

  function openCount() {
    return (state.table || []).filter(function (row) { return !row.defense; }).length;
  }

  function allBeaten() {
    var table = state.table || [];
    return table.length > 0 && openCount() === 0;
  }

  function canBeatCard(card, attack, trumpSuit) {
    if (!card || !attack || !trumpSuit) return false;
    var cardTrump = card.suit === trumpSuit;
    var attackTrump = attack.suit === trumpSuit;
    if (cardTrump && !attackTrump) return true;
    if (!cardTrump && attackTrump) return false;
    if (card.suit !== attack.suit) return false;
    return card.value > attack.value;
  }

  function tableRankNames() {
    var names = {};
    (state.table || []).forEach(function (row) {
      if (row.attack) names[row.attack.value] = rankShort(row.attack.rank);
      if (row.defense) names[row.defense.value] = rankShort(row.defense.rank);
    });
    return names;
  }

  function seatPlace(index, total, playerId, uid, rt) {
    var notes = [];
    var canSendTransfer = String(rt && rt.defender_id) === String(uid) && transferRoom(1);
    if (total === 1) notes.push("Across");
    else if (index === 0) notes.push(canSendTransfer ? "Transfer to" : "Next");
    else if (index === total - 1) notes.push("Previous");
    if (total === 1 && canSendTransfer) notes.push("Transfer to");
    if (throwNeighborIds(rt)[String(playerId)]) notes.push("Neighbor");
    return notes.join(" · ");
  }

  function findByAttr(parent, name, value) {
    if (!parent) return null;
    var want = String(value);
    var nodes = parent.children;
    for (var i = 0; i < nodes.length; i++) {
      if (nodes[i].getAttribute(name) === want) return nodes[i];
    }
    return null;
  }

  function opponentBacks(n) {
    var show = Math.min(6, Math.max(0, n));
    var backs = "";
    for (var i = 0; i < show; i++) {
      backs +=
        '<span class="play-opponent__back" style="--i:' + i + '">' + cardBackSvgHTML(true) + "</span>";
    }
    return backs;
  }

  function createOpponent(player) {
    var div = document.createElement("div");
    div.className = "play-opponent";
    div.dataset.seat = String(player.user_id);
    div.innerHTML =
      '<div class="play-seat-mark" aria-hidden="true"></div>' +
      '<div class="play-opponent__info">' +
      '<span class="play-role"><span></span></span>' +
      '<span class="play-opponent__name"></span>' +
      '<span class="play-opponent__meta"></span>' +
      '<span class="play-opponent__duty"></span>' +
      '<span class="play-opponent__badge"></span>' +
      "</div>" +
      '<div class="play-opponent__backs"></div>';
    return div;
  }

  function fillOpponent(div, player, index, total, uid, rt) {
    var roleKey = playerRoleKey(player.user_id, rt);
    var mustAct = playerMustAct(player.user_id, rt);
    var passed = hasPassed(player.user_id, rt);
    var duty = dutyText(player.user_id, rt);
    div.className = "play-opponent is-" + roleKey + (mustAct ? " is-acting" : " is-waiting");
    if (passed) div.classList.add("is-finished");
    if (div.dataset.role !== roleKey) {
      div.dataset.role = roleKey;
      var mark = div.querySelector(".play-seat-mark");
      var role = div.querySelector(".play-role");
      if (mark) mark.innerHTML = roleIcon(roleKey);
      if (role) {
        role.className = "play-role play-role--" + roleKey;
        role.innerHTML = roleIcon(roleKey) + "<span>" + roleLabel(roleKey) + "</span>";
      }
    }
    var name = div.querySelector(".play-opponent__name");
    if (name) name.textContent = player.username || "";
    var hidden = inboundOpp && inboundOpp[String(player.user_id)] ? inboundOpp[String(player.user_id)] : 0;
    var n = Math.max(0, (player.cards_remaining != null ? player.cards_remaining : 0) - hidden);
    var place = seatPlace(index, total, player.user_id, uid, rt);
    var meta = div.querySelector(".play-opponent__meta");
    if (meta) {
      meta.textContent = n + (n === 1 ? " card" : " cards") + (place ? " · " + place : "");
    }
    var dutyEl = div.querySelector(".play-opponent__duty");
    if (dutyEl) {
      dutyEl.textContent = duty;
      dutyEl.className = "play-opponent__duty" +
        (passed ? " is-finished" : "") +
        (mustAct ? " is-acting" : "");
    }
    var backs = div.querySelector(".play-opponent__backs");
    if (backs && backs.dataset.count !== String(n)) {
      backs.dataset.count = String(n);
      backs.innerHTML = opponentBacks(n);
    }
  }

  function findOpponent(id) {
    var nodes = document.querySelectorAll(".play-opponent");
    var want = String(id);
    for (var i = 0; i < nodes.length; i++) {
      if (nodes[i].getAttribute("data-seat") === want) return nodes[i];
    }
    return null;
  }

  function useSeatRing() {
    return window.matchMedia("(min-width: 900px)").matches;
  }

  function seatBinId(index, total) {
    var plans = {
      1: ["seat-north"],
      2: ["seat-west", "seat-east"],
      3: ["seat-west", "seat-north", "seat-east"],
      4: ["seat-west", "seat-north", "seat-north", "seat-east"],
      5: ["seat-west", "seat-north", "seat-north", "seat-north", "seat-east"],
      6: ["seat-west", "seat-west", "seat-north", "seat-north", "seat-east", "seat-east"],
      7: ["seat-west", "seat-west", "seat-north", "seat-north", "seat-north", "seat-east", "seat-east"],
    };
    var plan = plans[total] || plans[7];
    return plan[Math.min(index, plan.length - 1)];
  }

  function parkOpponents(nodes) {
    var home = document.querySelector(".play-opponents__row");
    if (home) {
      ["seat-west", "seat-north", "seat-east"].forEach(function (id) {
        var bin = document.getElementById(id);
        if (!bin) return;
        while (bin.firstChild) home.appendChild(bin.firstChild);
      });
    }
    if (!useSeatRing() || !home) {
      nodes.forEach(function (node) {
        if (home) home.appendChild(node);
      });
      return;
    }
    nodes.forEach(function (node, index) {
      var bin = document.getElementById(seatBinId(index, nodes.length));
      if (bin) bin.appendChild(node);
      else home.appendChild(node);
    });
  }

  function renderOpponents(uid, rt) {
    var el = document.getElementById("opponents");
    if (!el) return;
    var others = otherPlayers(uid);
    var ring = document.querySelector(".play-ring");
    if (ring) ring.dataset.seats = String(others.length);
    if (!others.length) {
      document.querySelectorAll(".play-opponent").forEach(function (node) { node.remove(); });
      return;
    }
    var row = el.querySelector(".play-opponents__row");
    if (!row) {
      el.innerHTML = "";
      var caption = document.createElement("p");
      caption.className = "play-opponents__order";
      caption.textContent = "Clockwise from you";
      row = document.createElement("div");
      row.className = "play-opponents__row";
      el.appendChild(caption);
      el.appendChild(row);
    }
    var keep = {};
    var seated = [];
    others.forEach(function (player, index) {
      var id = String(player.user_id);
      keep[id] = true;
      var div = findOpponent(id);
      if (!div) {
        div = createOpponent(player);
        row.appendChild(div);
      }
      fillOpponent(div, player, index, others.length, uid, rt);
      seated.push(div);
    });
    document.querySelectorAll(".play-opponent").forEach(function (div) {
      if (!keep[div.getAttribute("data-seat")]) div.remove();
    });
    parkOpponents(seated);
  }

  /** Stable pseudo-random peek offsets per table row so stacks stay readable when overlapping. */
  function stackPeekFromRowId(rowId) {
    var s = String(rowId);
    var h = 2166136261;
    for (var i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    var u = function (x) {
      return ((x >>> 0) % 10001) / 10000;
    };
    var a = h >>> 0;
    var b = Math.imul(h, 70460287) >>> 0;
    var c = Math.imul(h, 134775813) >>> 0;
    var dxD = -(6 + u(a) * 10);
    var dyD = 5 + u(b) * 12;
    var dxA = 5 + u(c) * 9;
    var dyA = -(6 + u(a + c) * 10);
    var rotAtk = -5 + u(b) * 7;
    var rotDef = -2 + u(a ^ c) * 7;
    return {
      dxD: dxD.toFixed(2) + "px",
      dyD: dyD.toFixed(2) + "px",
      rotD: rotAtk.toFixed(2) + "deg",
      dxA: dxA.toFixed(2) + "px",
      dyA: dyA.toFixed(2) + "px",
      rotA: rotDef.toFixed(2) + "deg",
    };
  }

  function mustConfirm(playerId, rt) {
    if (!rt || rt.phase !== "taking") return false;
    return (rt.pending_ids || []).some(function (id) {
      return String(id) === String(playerId);
    });
  }

  function renderDeckTrumpCorner(tcTrump, deckN, trumpInDeck) {
    var el = document.getElementById("deck-trump-corner");
    if (!el) return;
    var sig = String(deckN) + ":" + (trumpInDeck ? "1" : "0") + ":" + (tcTrump ? tcTrump.id : "");
    if (el.dataset.sig === sig) return;
    el.dataset.sig = sig;
    var parts = ['<p class="play-pile__label">Deck</p>', '<div class="play-deck-trump-pile">'];
    if (trumpInDeck && tcTrump) {
      parts.push(
        '<div class="play-trump-card play-trump-card--under-deck" title="Trump: ' +
          suitNameEn(tcTrump.suit) +
          '">' +
          cardSvgOuterHTML(tcTrump, {}) +
          "</div>"
      );
    }
    var faceDown = trumpInDeck ? Math.max(0, deckN - 1) : deckN;
    if (faceDown > 0) {
      parts.push('<div class="play-deck-stack" title="Cards in deck">');
      var layers = Math.min(4, Math.max(1, Math.ceil(faceDown / 10)));
      for (var j = 0; j < layers; j++) {
        parts.push(
          '<span class="play-deck-stack__layer" style="--layer:' +
            j +
            '">' +
            cardBackSvgHTML(false) +
            "</span>"
        );
      }
      parts.push('<span class="play-deck-stack__count">' + deckN + "</span></div>");
    } else if (!trumpInDeck) {
      parts.push('<div class="play-deck-stack play-deck-stack--empty">Deck empty</div>');
    }
    parts.push("</div>");
    el.innerHTML = parts.join("");
  }

  function renderDiscard() {
    var el = document.getElementById("discard-pile");
    if (!el) return;
    var count = state.discard_count || 0;
    if (el.dataset.sig === String(count)) return;
    el.dataset.sig = String(count);
    var parts = ['<p class="play-pile__label">Discard</p>'];
    if (count > 0) {
      parts.push('<div class="play-discard__stack">');
      var layers = Math.min(4, count);
      for (var i = 0; i < layers; i++) {
        parts.push(
          '<span class="play-discard__back" style="--layer:' + i + '">' + cardBackSvgHTML(false) + "</span>"
        );
      }
      parts.push('<span class="play-discard__count">' + count + "</span></div>");
    } else {
      parts.push('<p class="play-discard__empty">Empty</p>');
    }
    el.innerHTML = parts.join("");
  }

  function renderStatusbar(uid, me, rt) {
    var el = document.getElementById("play-statusbar");
    if (!el) return;
    if (state.status === "finished") {
      var loser = "";
      if (state.loser_id) {
        var lp = state.players.find(function (p) {
          return String(p.user_id) === String(state.loser_id);
        });
        loser = lp ? lp.username : state.loser_id;
      }
      el.textContent =
        "Game over" + (loser ? ". Fool: " + loser : "") + ".";
      return;
    }
    var partsArr = [modeLabel()];
    partsArr.push("Phase: " + phaseEn(rt && rt.phase));
    partsArr.push("Deck: " + (state.deck_remaining != null ? state.deck_remaining : 0));
    if (state.trump_card) {
      partsArr.push("Trump: " + suitNameEn(state.trump_card.suit));
    }
    partsArr.push("Table rows: " + (state.table ? state.table.length : 0));
    if (me) {
      partsArr.push("You: " + me.username);
    }
    el.textContent = partsArr.join(" · ");
  }

  function renderMyRole(uid, rt) {
    var el = document.getElementById("play-my-role");
    var sign = document.getElementById("play-my-sign");
    var area = document.getElementById("play-my-seat");
    if (!el) return;
    if (state.status === "finished") {
      el.textContent = "";
      el.hidden = true;
      if (sign) sign.innerHTML = "";
      if (area) area.className = "play-my-area";
      paintMyDuty(uid, rt);
      return;
    }
    el.hidden = false;
    var key = playerRoleKey(uid, rt);
    var mustAct = playerMustAct(uid, rt);
    el.innerHTML =
      '<span class="play-role play-role--' + key + '">' +
      roleIcon(key) +
      "<span>" + roleLabel(key) + "</span></span>";
    paintMyDuty(uid, rt);
    if (sign) {
      sign.innerHTML = key === "wait" ? "" : roleIcon(key);
      sign.className = "play-my-sign is-" + key;
    }
    if (area) {
      area.className = "play-my-area is-" + key + (mustAct ? " is-acting" : " is-waiting");
    }
  }

  function paintMyDuty(uid, rt) {
    var duty = document.getElementById("play-my-duty");
    if (!duty) return;
    if (!state || state.status !== "in_progress" || !rt) {
      duty.hidden = true;
      duty.textContent = "";
      return;
    }
    var text = dutyText(uid, rt);
    duty.hidden = !text;
    duty.textContent = text;
    duty.className = "play-my-duty" +
      (hasPassed(uid, rt) ? " is-finished" : "") +
      (playerMustAct(uid, rt) ? " is-acting" : "");
  }

  /** Mirrors fools.services.attack_cap: 6 after the first discard, otherwise 5. */
  function attackCap() {
    return state && (state.discard_count || 0) > 0 ? 6 : 5;
  }

  function throwSlots() {
    var rt = (state && state.runtime) || {};
    var cover = seatCards(rt.defender_id) - openCount();
    var capRoom = attackCap() - ((state.table || []).length);
    return Math.max(0, Math.min(cover, capRoom));
  }

  function canAddCards(uid, rt) {
    if (!rt || !state || state.status !== "in_progress") return false;
    var isAtt = String(rt.attacker_id) === String(uid);
    var isDef = String(rt.defender_id) === String(uid);
    if (rt.phase === "between") return isAtt;
    if (rt.phase !== "build" && rt.phase !== "defend" && rt.phase !== "taking") return false;
    if (isDef || !(state.table || []).length) return false;
    if (isAtt) return true;
    if (state.neighbor_throw_only && !throwNeighborIds(rt)[String(uid)]) return false;
    return true;
  }

  function attackSelection(me) {
    if (!me || !me.hand) return [];
    return me.hand.filter(function (card) { return selected.has(card.id); });
  }

  function attackSelectionFits(cards, uid, rt) {
    if (!cards.length || !canAddCards(uid, rt)) return false;
    if (cards.length > throwSlots()) return false;
    if (rt.phase === "between") {
      var rank = cards[0].value;
      return cards.every(function (card) { return card.value === rank; });
    }
    var names = tableRankNames();
    return cards.every(function (card) { return !!names[card.value]; });
  }

  function throwableLabels(me, uid, rt) {
    if (!canAddCards(uid, rt) || throwSlots() < 1 || !me || !me.hand) return [];
    var names = rt.phase === "between" ? null : tableRankNames();
    var seen = {};
    var labels = [];
    me.hand.forEach(function (card) {
      if (names && !names[card.value]) return;
      if (seen[card.value]) return;
      seen[card.value] = true;
      labels.push(rankShort(card.rank));
    });
    return labels;
  }

  function singleAttackRank() {
    var table = state.table || [];
    if (!table.length || table.some(function (row) { return row.defense; })) return null;
    var rank = table[0].attack && table[0].attack.value;
    if (rank == null) return null;
    if (table.some(function (row) { return !row.attack || row.attack.value !== rank; })) return null;
    return rank;
  }

  function nextSeat(playerId) {
    var circle = (state.players || []).slice().sort(function (a, b) {
      return a.seat_position - b.seat_position;
    });
    var index = circle.findIndex(function (row) {
      return String(row.user_id) === String(playerId);
    });
    if (index < 0 || circle.length < 2) return null;
    return circle[(index + 1) % circle.length];
  }

  function transferRoom(extra) {
    if (!state.transferable) return false;
    var rt = state.runtime || {};
    if (rt.phase !== "build" && rt.phase !== "defend") return false;
    if (singleAttackRank() == null) return false;
    var next = nextSeat(rt.defender_id);
    if (!next || String(next.user_id) === String(rt.defender_id)) return false;
    var needed = (state.table || []).length + extra;
    if (needed > attackCap()) return false;
    return (next.cards_remaining || 0) >= needed;
  }

  function selectedPassIds(me) {
    var rank = singleAttackRank();
    if (rank == null || !me || !me.hand) return [];
    return me.hand.filter(function (card) {
      return selected.has(card.id) && card.value === rank;
    }).map(function (card) { return card.id; });
  }

  function postTransfer(ids, button) {
    if (!ids || !ids.length) return;
    postAction(button || null, "transfer/", { card_ids: ids }, true);
  }

  function viewer(uid) {
    return (state.players || []).find(function (row) {
      return String(row.user_id) === String(uid);
    }) || null;
  }

  function beginSend(button) {
    sendCount += 1;
    var note = document.getElementById("play-sending");
    if (note) note.hidden = false;
    if (!button) return;
    busyButtons[button.id] = true;
    if (!button.dataset.idleLabel) button.dataset.idleLabel = button.textContent.trim();
    button.textContent = "Sending…";
    button.disabled = true;
    button.setAttribute("aria-disabled", "true");
  }

  function endSend(button) {
    sendCount = Math.max(0, sendCount - 1);
    var note = document.getElementById("play-sending");
    if (note) note.hidden = sendCount !== 0;
    if (button) delete busyButtons[button.id];
    updateActionButtons(uidStr(), (state && state.runtime) || {});
  }

  function postAction(button, path, body, clearSelection) {
    setErr("");
    beginSend(button);
    api("POST", BASE + path, body)
      .then(function (s) {
        return applyState(s, !!clearSelection);
      })
      .then(function () {
        endSend(button);
      })
      .catch(function (e) {
        setErr(e.message || "Could not play.");
        endSend(button);
      });
  }

  function setIdleLabel(btn, label) {
    if (!btn) return;
    btn.dataset.idleLabel = label;
    if (!busyButtons[btn.id]) btn.textContent = label;
  }

  function settleButton(btn, hidden, disabled) {
    if (!btn) return;
    btn.hidden = hidden;
    if (busyButtons[btn.id]) {
      btn.disabled = true;
      btn.setAttribute("aria-disabled", "true");
      return;
    }
    btn.disabled = !!disabled;
    btn.setAttribute("aria-disabled", disabled ? "true" : "false");
  }

  function hintText(uid, me, rt) {
    if (state.status === "finished") return "";
    if (!rt) return "";
    var isAtt = rt.attacker_id != null && String(rt.attacker_id) === uid;
    var isDef = rt.defender_id != null && String(rt.defender_id) === uid;
    var wave = rt.phase === "build" || rt.phase === "defend";
    var taking = rt.phase === "taking";
    var open = openCount();
    var beaten = allBeaten();
    var actor = expectedActorId(rt);

    if (me && isOutOfCards(me) && rt.phase === "between") {
      return "You are out of cards.";
    }
    if (rt.phase === "between" && isAtt) {
      return "Your turn — choose a card to attack.";
    }
    if (taking && confirmAgain && mustConfirm(uid, rt)) {
      return "Cards were added — confirm completion again. Throw in more, or press Done throwing.";
    }
    if (taking && confirmAgain && isDef) {
      return "Cards were added — confirm completion again. You are still taking the cards.";
    }
    if (taking && confirmAgain) {
      return "Cards were added — confirm completion again.";
    }
    if (taking && mustConfirm(uid, rt)) {
      return "The defender is taking the cards. Throw in more, or press Done throwing.";
    }
    if (taking && isDef) {
      return "You are taking the cards. Waiting for the others to finish.";
    }
    if (taking) {
      var waiting = (rt.pending_ids || [])[0];
      return waiting ? "Waiting for " + nameOf(waiting) + " to finish throwing." : "Waiting.";
    }
    if (wave && isDef && open > 0 && transferRoom(1)) {
      var passRank = singleAttackRank();
      var passName = "";
      (state.table || []).some(function (row) {
        if (row.attack && row.attack.value === passRank) {
          passName = rankShort(row.attack.rank);
          return true;
        }
        return false;
      });
      return "Transfer with " + (passName || "a matching card") + ", beat the cards, or press Take cards.";
    }
    if (wave && isDef && open > 0) {
      return "Beat " + open + (open === 1 ? " more card" : " more cards") + ", or press Take cards.";
    }
    if (wave && isDef && beaten) {
      return "All cards are beaten. Waiting for the attacker.";
    }
    if (wave && isAtt && beaten) {
      return "All cards are beaten — throw in more, or press Beaten.";
    }
    var throwable = throwableLabels(me, uid, rt);
    if (wave && !isDef && throwable.length) {
      return "You can throw in: " + throwable.join(" or ") + ".";
    }
    if (actor) {
      var who = nameOf(actor);
      if (rt.phase === "between") return "Waiting for " + who + " to attack.";
      if (open > 0) return "Waiting for " + who + " to defend.";
      return "Waiting for " + who + ".";
    }
    return "Waiting.";
  }

  function cardIsLegal(card, uid, me, rt, trumpSuit) {
    if (!rt || state.status !== "in_progress" || !me || !card) return false;
    var isDef = String(rt.defender_id) === String(uid);
    var wave = rt.phase === "build" || rt.phase === "defend";
    if (wave && isDef && openCount() > 0) {
      var beats = (state.table || []).some(function (row) {
        return !row.defense && canBeatCard(card, row.attack, trumpSuit);
      });
      if (beats) return true;
      return !!(transferRoom(1) && card.value === singleAttackRank());
    }
    if (!canAddCards(uid, rt) || throwSlots() < 1) return false;
    var others = attackSelection(me).filter(function (item) { return item.id !== card.id; });
    if (rt.phase === "between") {
      if (!others.length) return true;
      if (card.value !== others[0].value) return false;
      return others.length + 1 <= throwSlots();
    }
    if (!tableRankNames()[card.value]) return false;
    return others.length + 1 <= throwSlots();
  }

  function wireActionButtons() {
    var attack = document.getElementById("btn-attack");
    var take = document.getElementById("btn-take");
    var bito = document.getElementById("btn-bito");
    var done = document.getElementById("btn-done");
    var pass = document.getElementById("btn-transfer");
    function once(btn, handler) {
      if (!btn || btn.dataset.wired === "1") return;
      btn.dataset.wired = "1";
      btn.addEventListener("click", handler);
    }
    once(attack, function () {
      var uid = uidStr();
      var rt = (state && state.runtime) || {};
      var cards = attackSelection(viewer(uid));
      if (!attackSelectionFits(cards, uid, rt)) {
        setErr("Choose cards you can play together.");
        return;
      }
      postAction(attack, "attack/", {
        card_ids: cards.map(function (card) { return card.id; }),
      }, true);
    });
    once(pass, function () {
      var uid = uidStr();
      var ids = selectedPassIds(viewer(uid));
      if (!ids.length || !transferRoom(ids.length)) {
        setErr("Select cards of the attack rank to transfer.");
        return;
      }
      postTransfer(ids, pass);
    });
    once(take, function () {
      postAction(take, "take/", {}, true);
    });
    once(done, function () {
      postAction(done, "pass/", {}, true);
    });
    once(bito, function () {
      postAction(bito, "bito/", {}, true);
    });
  }

  function updateActionButtons(uid, rt) {
    rt = rt || {};
    var isAtt = rt.attacker_id != null && String(rt.attacker_id) === uid;
    var isDef = rt.defender_id != null && String(rt.defender_id) === uid;
    var attackBtn = document.getElementById("btn-attack");
    var takeBtn = document.getElementById("btn-take");
    var bitoBtn = document.getElementById("btn-bito");
    var doneBtn = document.getElementById("btn-done");
    var passBtn = document.getElementById("btn-transfer");
    var me = viewer(uid);
    var passIds = selectedPassIds(me);
    var chosen = attackSelection(me);
    var inProg = state && state.status === "in_progress";
    var wave = rt.phase === "build" || rt.phase === "defend";
    var tbl = (state && state.table) || [];
    var show = inProg && wave && tbl.length > 0;
    var allDefended = tbl.length > 0 && tbl.every(function (row) { return row.defense; });
    var canAttack = !!(inProg && canAddCards(uid, rt) && throwableLabels(me, uid, rt).length);

    if (attackBtn) {
      setIdleLabel(attackBtn, rt.phase === "between" ? "Attack" : "Throw in");
      settleButton(attackBtn, !canAttack, !(canAttack && attackSelectionFits(chosen, uid, rt)));
    }
    setIdleLabel(takeBtn, "Take cards");
    settleButton(takeBtn, !(show && isDef && !allDefended), false);
    setIdleLabel(bitoBtn, "Beaten");
    settleButton(bitoBtn, !(show && isAtt && allDefended), false);
    setIdleLabel(doneBtn, "Done throwing");
    settleButton(doneBtn, !(inProg && mustConfirm(uid, rt)), false);
    if (passBtn) {
      var canPass = show && isDef && !allDefended && transferRoom(1);
      setIdleLabel(passBtn, "Transfer");
      settleButton(
        passBtn,
        !canPass,
        !(canPass && passIds.length > 0 && transferRoom(passIds.length))
      );
    }
    var aside = document.querySelector(".play-side-actions");
    if (aside) {
      aside.hidden = [attackBtn, takeBtn, bitoBtn, doneBtn, passBtn].every(function (btn) {
        return !btn || btn.hidden;
      });
    }
  }

  var tableChatReady = false;

  function ensureTableChat(lobbyId) {
    if (tableChatReady || !lobbyId) return;
    tableChatReady = true;
    var section = document.getElementById("play-chat");
    var log = document.getElementById("play-chat-log");
    var form = document.getElementById("play-chat-form");
    var input = document.getElementById("play-chat-input");
    var error = document.getElementById("play-chat-error");
    if (!section || !log || !form || !input) return;
    section.hidden = false;
    var url = "/api/fools/lobbies/" + lobbyId + "/messages/";

    function appendMessage(message) {
      if (!message || !message.id) return;
      if (log.querySelector('[data-id="' + message.id + '"]')) return;
      var line = document.createElement("div");
      line.className = "game-chat-line";
      line.dataset.id = message.id;
      line.textContent = (message.username || "Player") + ": " + (message.content || "");
      log.appendChild(line);
      log.scrollTop = log.scrollHeight;
    }

    api("GET", url).then(function (rows) {
      (rows || []).forEach(appendMessage);
    }).catch(function (e) {
      if (error) error.textContent = e.message || "Could not load chat.";
    });

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var content = input.value.trim();
      if (!content) return;
      if (error) error.textContent = "";
      api("POST", url, { content: content }).then(function (message) {
        input.value = "";
        appendMessage(message);
      }).catch(function (e) {
        if (error) error.textContent = e.message || "Could not send.";
      });
    });

    var proto = location.protocol === "https:" ? "wss:" : "ws:";
    var chatRetries = 0;
    var chatToken = 0;

    function setChatLink(text) {
      var note = document.getElementById("play-chat-status");
      if (!note) return;
      if (!text) {
        note.hidden = true;
        note.textContent = "";
        return;
      }
      note.hidden = false;
      note.textContent = text;
    }

    function connectChat() {
      var token = ++chatToken;
      if (chatRetries > 0) setChatLink("Reconnecting to chat…");
      var socket = new WebSocket(proto + "//" + location.host + "/ws/lobbies/" + lobbyId + "/");
      socket.onopen = function () {
        if (token !== chatToken) return;
        chatRetries = 0;
        setChatLink("");
        api("GET", url).then(function (rows) {
          (rows || []).forEach(appendMessage);
        }).catch(function (e) {
          if (error) error.textContent = e.message || "Could not load chat.";
        });
      };
      socket.onmessage = function (ev) {
        var message = null;
        try {
          message = JSON.parse(ev.data);
        } catch (ignore) {
          message = null;
        }
        if (message && message.event === "lobby_chat") appendMessage(message.payload || {});
      };
      socket.onclose = function () {
        if (token !== chatToken) return;
        setChatLink("Chat disconnected.");
        var delay = Math.min(10000, 800 * Math.pow(2, Math.min(chatRetries, 4)));
        chatRetries += 1;
        window.setTimeout(function () {
          if (token !== chatToken) return;
          setChatLink("Reconnecting to chat…");
          connectChat();
        }, delay);
      };
    }

    connectChat();
  }

  function toggleCard(cardId) {
    var uid = uidStr();
    var rt = (state && state.runtime) || {};
    var me = viewer(uid);
    var trumpSuit = state && state.trump_card ? state.trump_card.suit : null;
    if (selected.has(cardId)) selected.delete(cardId);
    else {
      var card = me && me.hand && me.hand.find(function (item) { return item.id === cardId; });
      if (!card || !cardIsLegal(card, uid, me, rt, trumpSuit)) return;
      selected.add(cardId);
    }
    refreshHandMarks(uid, me, rt, trumpSuit);
  }

  function refreshHandMarks(uid, me, rt, trumpSuit) {
    var inner = document.querySelector(".play-hand-fan__inner");
    var cards = sortedHand(me && me.hand, trumpSuit);
    var n = cards.length;
    var mid = (n - 1) / 2;
    cards.forEach(function (card, idx) {
      if (!inner) return;
      var wrap = findByAttr(inner, "data-cid", card.id);
      if (!wrap) return;
      var legal = cardIsLegal(card, uid, me, rt, trumpSuit);
      wrap.classList.toggle("is-legal", legal);
      wrap.classList.toggle("is-dim", !legal);
      wrap.classList.toggle("is-selected", selected.has(card.id));
      wrap.setAttribute("aria-pressed", selected.has(card.id) ? "true" : "false");
      wrap.style.zIndex = selected.has(card.id) ? "40" : String(30 - Math.abs(idx - mid));
    });
    paintDefenseTargets(uid, rt, trumpSuit);
    updateActionButtons(uid, rt);
  }

  function placeHandCard(wrap, card, idx, n, uid, me, rt, trumpSuit) {
    var mid = (n - 1) / 2;
    var maxDist = Math.max(mid, n - 1 - mid) || 1;
    var dist = Math.abs(idx - mid);
    var norm = dist / maxDist;
    var legal = cardIsLegal(card, uid, me, rt, trumpSuit);
    wrap.classList.toggle("play-card--trump", !!(trumpSuit && card.suit === trumpSuit));
    wrap.classList.toggle("is-selected", selected.has(card.id));
    wrap.classList.toggle("is-legal", legal);
    wrap.classList.toggle("is-dim", !legal);
    wrap.setAttribute("aria-pressed", selected.has(card.id) ? "true" : "false");
    wrap.setAttribute("aria-label", card.rank + " of " + card.suit);
    wrap.style.setProperty("--fan-rot", (idx - mid) * 7.25 + "deg");
    wrap.style.setProperty("--fan-y", (norm * norm * 16 + norm * 3) + "px");
    wrap.style.setProperty("--fan-x", ((idx - mid) * 0.85) + "px");
    wrap.style.zIndex = selected.has(card.id) ? "40" : String(30 - Math.abs(idx - mid));
  }

  function createHandCard(card) {
    var wrap = document.createElement("div");
    wrap.className = "play-card play-card--hand";
    wrap.dataset.cid = card.id;
    wrap.tabIndex = 0;
    wrap.setAttribute("role", "button");
    wrap.setAttribute("draggable", "true");
    wrap.innerHTML = cardSvgOuterHTML(card, {});
    wrap.addEventListener("click", function (ev) {
      ev.preventDefault();
      toggleCard(card.id);
    });
    wrap.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        toggleCard(card.id);
        return;
      }
      if (ev.key !== "ArrowRight" && ev.key !== "ArrowLeft") return;
      var cards = Array.prototype.slice.call(wrap.parentNode.children);
      var index = cards.indexOf(wrap);
      var next = cards[index + (ev.key === "ArrowRight" ? 1 : -1)];
      if (!next) return;
      ev.preventDefault();
      next.focus();
    });
    wrap.addEventListener("dragstart", function (ev) {
      setDragCardIds(ev, attackPayloadFromDrag(card.id));
      wrap.classList.add("is-dragging");
      markDropTargets(attackPayloadFromDrag(card.id));
    });
    wrap.addEventListener("dragend", function () {
      wrap.classList.remove("is-dragging");
      clearDropTargets();
      if (!handDirty) return;
      handDirty = false;
      render(state.table || []);
    });
    return wrap;
  }

  var SUIT_ORDER = { Spades: 0, Hearts: 1, Diamonds: 2, Clubs: 3 };
  var HAND_SORTS = ["suit-left", "suit-right", "rank-ltr", "rank-rtl", "dealt", "dealt-rev"];
  var HAND_SORT_KEY = "fools-hand-sort";
  var handSort = "suit-left";
  var SORT_LABEL = {
    "suit-left": "Suit · trump left",
    "suit-right": "Suit · trump right",
    "rank-ltr": "Rank · low to high",
    "rank-rtl": "Rank · high to low",
    "dealt": "Dealt",
    "dealt-rev": "Dealt · reversed",
  };

  function rememberedSort(saved) {
    if (HAND_SORTS.indexOf(saved) >= 0) return saved;
    if (saved === "suit") return "suit-left";
    if (saved === "rank") return "rank-ltr";
    if (saved === "dealt") return "dealt";
    return "suit-left";
  }

  function suitKey(suit, trumpSuit, trumpOnRight) {
    var base = SUIT_ORDER[suit] != null ? SUIT_ORDER[suit] : 4;
    if (trumpSuit && suit === trumpSuit) return trumpOnRight ? 8 : -1;
    return base;
  }

  /** Display order only. Requests still use the hand order from the server. */
  function sortedHand(hand, trumpSuit) {
    var cards = (hand || []).slice();
    if (handSort === "dealt") return cards;
    if (handSort === "dealt-rev") {
      cards.reverse();
      return cards;
    }
    var bySuit = handSort === "suit-left" || handSort === "suit-right";
    var trumpOnRight = handSort === "suit-right";
    cards.sort(function (a, b) {
      if (bySuit) {
        var suitDiff = suitKey(a.suit, trumpSuit, trumpOnRight) - suitKey(b.suit, trumpSuit, trumpOnRight);
        if (suitDiff) return suitDiff;
      } else if (a.value !== b.value) {
        return a.value - b.value;
      }
      if (a.value !== b.value) return a.value - b.value;
      var within = suitKey(a.suit, trumpSuit, false) - suitKey(b.suit, trumpSuit, false);
      if (within) return within;
      if (String(a.id) < String(b.id)) return -1;
      if (String(a.id) > String(b.id)) return 1;
      return 0;
    });
    if (handSort === "rank-rtl") cards.reverse();
    return cards;
  }

  function nextHandSort(mode) {
    var index = HAND_SORTS.indexOf(mode);
    if (index < 0) index = 0;
    return HAND_SORTS[(index + 1) % HAND_SORTS.length];
  }

  function paintSortButton() {
    var btn = document.getElementById("btn-sort");
    if (!btn) return;
    btn.textContent = SORT_LABEL[handSort] || SORT_LABEL["suit-left"];
    btn.setAttribute(
      "aria-label",
      "Hand sort: " + btn.textContent + ". Switch to " + (SORT_LABEL[nextHandSort(handSort)] || "") + "."
    );
  }

  function loadHandSort() {
    try {
      handSort = rememberedSort(window.localStorage.getItem(HAND_SORT_KEY));
    } catch (ignore) {
      handSort = "suit-left";
    }
  }

  function cycleHandSort() {
    handSort = nextHandSort(handSort);
    try {
      window.localStorage.setItem(HAND_SORT_KEY, handSort);
    } catch (ignore) {}
    paintSortButton();
    var uid = uidStr();
    var rt = (state && state.runtime) || {};
    renderHand(uid, viewer(uid), rt, state && state.trump_card ? state.trump_card.suit : null);
  }

  function wireSort() {
    var btn = document.getElementById("btn-sort");
    if (!btn || btn.dataset.wired === "1") return;
    btn.dataset.wired = "1";
    btn.addEventListener("click", cycleHandSort);
  }

  function renderHand(uid, me, rt, trumpSuit) {
    var handEl = document.getElementById("hand");
    if (!handEl) return;
    if (handEl.querySelector(".is-dragging")) {
      handDirty = true;
      return;
    }
    var inner = handEl.querySelector(".play-hand-fan__inner");
    if (!inner) {
      inner = document.createElement("div");
      inner.className = "play-hand-fan__inner";
      handEl.appendChild(inner);
    }
    var cards = sortedHand(me && me.hand, trumpSuit).filter(function (card) {
      return !(inboundMine && inboundMine[card.id]);
    });
    var keep = {};
    cards.forEach(function (card, idx) {
      keep[card.id] = true;
      var wrap = findByAttr(inner, "data-cid", card.id);
      if (!wrap) {
        wrap = createHandCard(card);
        inner.appendChild(wrap);
      }
      placeHandCard(wrap, card, idx, cards.length, uid, me, rt, trumpSuit);
    });
    Array.prototype.slice.call(inner.children).forEach(function (wrap) {
      if (!keep[wrap.getAttribute("data-cid")]) wrap.remove();
    });
    cards.forEach(function (card) {
      var wrap = findByAttr(inner, "data-cid", card.id);
      if (wrap) inner.appendChild(wrap);
    });
  }

  function selectedBeater(me) {
    if (!me || !me.hand || selected.size !== 1) return null;
    var found = null;
    me.hand.forEach(function (card) {
      if (selected.has(card.id)) found = card;
    });
    return found;
  }

  function paintDefenseTargets(uid, rt, trumpSuit) {
    var me = viewer(uid);
    var chosen = selectedBeater(me);
    var defending = rt && (rt.phase === "build" || rt.phase === "defend") &&
      String(rt.defender_id) === String(uid);
    document.querySelectorAll(".play-table-pair").forEach(function (el) {
      var row = (state.table || []).find(function (item) {
        return item.id === el.dataset.tableCardId;
      });
      var legal = !!(
        defending && chosen && row && !row.defense && canBeatCard(chosen, row.attack, trumpSuit)
      );
      el.classList.toggle("is-legal-target", legal);
      if (legal) {
        el.tabIndex = 0;
        el.setAttribute("role", "button");
        el.setAttribute("aria-label", "Beat the " + row.attack.rank + " of " + row.attack.suit);
      } else {
        el.tabIndex = -1;
        el.removeAttribute("role");
        el.removeAttribute("aria-label");
      }
    });
  }

  function playDefenseOn(el) {
    var uid = uidStr();
    var rt = (state && state.runtime) || {};
    var trumpSuit = state && state.trump_card ? state.trump_card.suit : null;
    var row = (state.table || []).find(function (item) {
      return item.id === el.dataset.tableCardId;
    });
    if (selected.size !== 1) {
      setErr("Select one card to beat this attack.");
      return;
    }
    var card = selectedBeater(viewer(uid));
    if (!card || !row || !canBeatCard(card, row.attack, trumpSuit)) {
      setErr("That card cannot beat this attack. To transfer, select the attack rank and press Transfer.");
      return;
    }
    postAction(null, "defend/", { table_card_id: row.id, card_id: card.id }, true);
  }

  function bindPair(el) {
    if (el.dataset.bound === "1") return;
    el.dataset.bound = "1";
    el.addEventListener("click", function () {
      if (el.classList.contains("is-legal-target")) {
        playDefenseOn(el);
        return;
      }
      if (!el.classList.contains("play-table-pair--open")) return;
      var rt = (state && state.runtime) || {};
      if (String(rt.defender_id) !== uidStr()) return;
      if (rt.phase !== "build" && rt.phase !== "defend") return;
      setErr("That card cannot beat this attack. To transfer, select the attack rank and press Transfer.");
    });
    el.addEventListener("keydown", function (ev) {
      if (ev.key !== "Enter" && ev.key !== " ") return;
      if (!el.classList.contains("is-legal-target")) return;
      ev.preventDefault();
      playDefenseOn(el);
    });
    watchDropHover(el);
  }

  function stackNodes(row, previous, uid) {
    var peek = stackPeekFromRowId(row.id);
    var defenseId = row.defense ? row.defense.id : "";
    var def = document.createElement("div");
    def.className = "play-card play-card--table play-card--stack-def" +
      (row.defense ? "" : " play-card--placeholder");
    def.dataset.cardId = defenseId;
    def.innerHTML = row.defense ? cardSvgOuterHTML(row.defense, {}) : "";
    def.style.setProperty("--peek-def-x", peek.dxA);
    def.style.setProperty("--peek-def-y", peek.dyA);
    def.style.setProperty("--peek-def-rot", peek.rotA);
    if (row.defense && (!previous || !previous.defense)) {
      def.classList.add("is-covering");
      if (String((state.runtime || {}).defender_id) === String(uid)) def.classList.add("is-from-me");
      forgetArrival(def);
    }
    var atk = document.createElement("div");
    atk.className = "play-card play-card--table play-card--stack-atk";
    atk.innerHTML = cardSvgOuterHTML(row.attack, {});
    atk.style.setProperty("--peek-atk-x", peek.dxD);
    atk.style.setProperty("--peek-atk-y", peek.dyD);
    atk.style.setProperty("--peek-atk-rot", peek.rotD);
    var stack = document.createElement("div");
    stack.className = "play-table-stack";
    stack.appendChild(atk);
    stack.appendChild(def);
    return stack;
  }

  function updatePair(el, row, previous, uid) {
    el.classList.toggle("play-table-pair--open", !row.defense);
    var def = el.querySelector(".play-card--stack-def");
    var defenseId = row.defense ? row.defense.id : "";
    if (!def || def.dataset.cardId === defenseId) return;
    def.dataset.cardId = defenseId;
    def.classList.toggle("play-card--placeholder", !row.defense);
    def.innerHTML = row.defense ? cardSvgOuterHTML(row.defense, {}) : "";
    if (row.defense && (!previous || !previous.defense)) {
      def.classList.add("is-covering");
      if (String((state.runtime || {}).defender_id) === String(uid)) def.classList.add("is-from-me");
      forgetArrival(def);
    }
  }

  function forgetArrival(el) {
    function done(ev) {
      if (ev.target !== el) return;
      el.classList.remove("is-arriving", "is-from-me", "is-covering");
      el.removeEventListener("animationend", done);
    }
    el.addEventListener("animationend", done);
  }

  function renderTable(previousTable, uid, rt, trumpSuit) {
    var tbl = document.getElementById("table-rows");
    if (!tbl) return;
    var rows = state.table || [];
    tbl.classList.toggle("is-two-rows", rows.length > 3);
    var seen = {};
    (previousTable || []).forEach(function (row) { seen[row.id] = row; });
    var fromMe = activeBadge && String(activeBadge.userId) === String(uid);
    var keep = {};
    rows.forEach(function (row) {
      keep[row.id] = true;
      var el = findByAttr(tbl, "data-table-card-id", row.id);
      if (!el) {
        el = document.createElement("div");
        el.className = "play-table-pair";
        el.dataset.tableCardId = row.id;
        if (!seen[row.id]) {
          el.classList.add("is-arriving");
          if (fromMe) el.classList.add("is-from-me");
          forgetArrival(el);
        }
        if (!row.defense) el.classList.add("play-table-pair--open");
        el.appendChild(stackNodes(row, seen[row.id], uid));
        bindPair(el);
        tbl.appendChild(el);
      } else {
        updatePair(el, row, seen[row.id], uid);
      }
    });
    Array.prototype.slice.call(tbl.children).forEach(function (el) {
      if (!keep[el.dataset.tableCardId]) el.remove();
    });
    paintDefenseTargets(uid, rt, trumpSuit);
  }

  function render(previousTable) {
    if (!state) return;
    previousTable = previousTable || [];
    var uid = uidStr();
    var me = uid && state.players.find(function (p) { return String(p.user_id) === uid; });
    var rt = state.runtime || {};
    var tcTrump = state.trump_card;
    var trumpSuit = tcTrump ? tcTrump.suit : null;

    var mySeat = document.getElementById("play-my-seat");
    if (mySeat && uid) mySeat.dataset.seat = uid;

    var back = document.getElementById("back-lobby");
    if (back) back.href = "/fools/lobbies/" + state.lobby_id + "/";

    ensureTableChat(state.lobby_id);
    renderStatusbar(uid, me, rt);
    if (state.next_game_id && String(state.next_game_id) !== String(gameId)) {
      window.location.href = "/fools/play/" + state.next_game_id + "/";
      return;
    }
    renderMyRole(uid, rt);
    renderOpponents(uid, rt);
    if (dealView) renderDeckTrumpCorner(tcTrump, dealView.deck, dealView.trump);
    else renderDeckTrumpCorner(tcTrump, state.deck_remaining || 0, !!state.trump_in_deck);
    renderDiscard();

    pruneSelection(me && me.hand);
    renderHand(uid, me, rt, trumpSuit);
    renderTable(previousTable, uid, rt, trumpSuit);

    wireDropTargets(uid, me, rt);
    updateActionButtons(uid, rt);

    var hint = document.getElementById("play-hint");
    if (hint) {
      var hintLine = hintText(uid, me, rt);
      hint.textContent = hintLine;
      hint.hidden = !hintLine;
    }
    renderResult(uid);
    applyPublicEvents();
    paintBadge();
  }

  var ACTION_LABEL = {
    take: "Took cards",
    bito: "Beaten",
    transfer: "Transferred",
    pass: "Done throwing",
  };
  var recentActions = [];
  var badgeTimer = null;
  var resultFocused = false;
  var confirmAgain = false;
  var handDirty = false;
  var inboundMine = null;
  var inboundOpp = null;
  var dealView = null;
  var sendCount = 0;
  var busyButtons = {};
  var HISTORY_KEY = "fools-history:" + gameId;

  function cardFace(card) {
    if (!card) return "";
    return rankShort(card.rank) + (SUIT_SYMBOL[card.suit] || "");
  }

  function actionPhrase(payload) {
    var cards = (payload.cards || []).map(cardFace).filter(Boolean).join(", ");
    if (payload.action === "attack") return "Threw " + cards;
    if (payload.action === "defend") return "Beat " + cards;
    if (payload.action === "transfer") return cards ? "Transferred " + cards : "Transferred the attack";
    return ACTION_LABEL[payload.action] || "Played";
  }

  function showActionBadge(payload, record) {
    if (!payload || !payload.user_id) return;
    var phrase = actionPhrase(payload);
    activeBadge = {
      userId: String(payload.user_id),
      action: payload.action,
      text: phrase,
      until: Date.now() + 1700,
    };
    if (payload.action === "bito") {
      pendingClear = payload.action;
    }
    if (record) {
      var line = (payload.username || nameOf(payload.user_id)) + " — " + phrase;
      if (recentActions[0] !== line) {
        recentActions.unshift(line);
        recentActions = recentActions.slice(0, 8);
      }
      paintHistory();
    }
    paintBadge();
    armBadgeTimer();
  }

  function loadHistory() {
    try {
      var raw = window.sessionStorage.getItem(HISTORY_KEY);
      var parsed = raw ? JSON.parse(raw) : [];
      if (!Array.isArray(parsed)) return;
      recentActions = parsed.filter(function (line) {
        return typeof line === "string" && line;
      }).slice(0, 8);
    } catch (ignore) {
      recentActions = [];
    }
  }

  function applyPublicEvents() {
    var events = state && state.public_events;
    if (!events || !events.length) return;
    var lines = [];
    events.forEach(function (event) {
      var who = event.username || nameOf(event.user_id);
      lines.push(who + " — " + actionPhrase(event));
    });
    recentActions = lines.slice(-8).reverse();
    paintHistory();
  }

  function paintHistory() {
    var list = document.getElementById("play-history");
    if (!list) return;
    list.innerHTML = "";
    recentActions.forEach(function (line) {
      var item = document.createElement("li");
      item.textContent = line;
      list.appendChild(item);
    });
    try {
      window.sessionStorage.setItem(HISTORY_KEY, JSON.stringify(recentActions));
    } catch (ignore) {}
  }

  function armBadgeTimer() {
    if (badgeTimer) window.clearTimeout(badgeTimer);
    badgeTimer = null;
    if (!activeBadge) return;
    var wait = Math.max(0, activeBadge.until - Date.now());
    badgeTimer = window.setTimeout(function () {
      badgeTimer = null;
      activeBadge = null;
      paintBadge();
    }, wait);
  }

  function paintBadge() {
    document.querySelectorAll(".play-action-badge").forEach(function (el) {
      el.remove();
    });
    if (!activeBadge || Date.now() > activeBadge.until) {
      activeBadge = null;
      return;
    }
    var host = null;
    if (String(activeBadge.userId) === uidStr()) host = document.getElementById("play-my-badge");
    else {
      var seat = document.querySelector('.play-opponent[data-seat="' + activeBadge.userId + '"]');
      host = seat ? seat.querySelector(".play-opponent__badge") : null;
    }
    if (!host) return;
    var badge = document.createElement("p");
    badge.className = "play-action-badge play-action-badge--" + (activeBadge.action || "take");
    badge.textContent = activeBadge.text || ACTION_LABEL[activeBadge.action] || "Played";
    host.appendChild(badge);
  }

  function clearTarget(kind, takerId) {
    if (kind === "take" && takerId != null) {
      var seat = document.querySelector('.play-opponent[data-seat="' + String(takerId) + '"]');
      if (seat) return seat;
      var mine = document.getElementById("play-my-seat");
      if (mine && mine.dataset.seat === String(takerId)) return mine;
    }
    return document.getElementById("discard-pile");
  }

  function animateClear(kind, takerId) {
    var rows = document.querySelectorAll(".play-table-pair");
    if (!rows.length) return Promise.resolve();
    var target = clearTarget(kind, takerId);
    var fallbackX = kind === "take" ? 0 : 120;
    var fallbackY = kind === "take" ? 64 : -28;
    rows.forEach(function (row) {
      var dx = fallbackX;
      var dy = fallbackY;
      if (target) {
        var from = row.getBoundingClientRect();
        var to = target.getBoundingClientRect();
        if (from.width || from.height) {
          dx = (to.left + to.width / 2) - (from.left + from.width / 2);
          dy = (to.top + to.height / 2) - (from.top + from.height / 2);
        }
      }
      row.style.setProperty("--clear-x", dx.toFixed(1) + "px");
      row.style.setProperty("--clear-y", dy.toFixed(1) + "px");
      row.classList.add(kind === "take" ? "is-taking" : "is-discarding");
    });
    return new Promise(function (resolve) {
      window.setTimeout(resolve, 450);
    });
  }

  function renderResult(uid) {
    var panel = document.getElementById("play-result");
    if (!panel) return;
    if (!state || state.status !== "finished") {
      panel.hidden = true;
      return;
    }
    var title = document.getElementById("play-result-title");
    var text = document.getElementById("play-result-text");
    var lobby = document.getElementById("play-result-lobby");
    var loser = null;
    if (state.loser_id) {
      loser = (state.players || []).find(function (p) {
        return String(p.user_id) === String(state.loser_id);
      });
    }
    var mine = state.loser_id && String(state.loser_id) === String(uid);
    if (title) title.textContent = mine ? "You are the fool" : "Game over";
    if (text) {
      if (mine) text.textContent = "You lost this game. Everyone else is out.";
      else if (loser) text.textContent = loser.username + " is the fool.";
      else text.textContent = "This game has finished.";
      if (!state.can_rematch) {
        text.textContent += " The host can deal another game for everyone still in the lobby.";
      }
    }
    if (lobby) {
      lobby.href = state.lobby_id ? "/fools/lobbies/" + state.lobby_id + "/" : "/fools/";
    }
    var again = document.getElementById("play-result-again");
    if (again) again.hidden = !state.can_rematch;
    panel.hidden = false;
    if (!resultFocused && title) {
      resultFocused = true;
      title.focus();
    }
  }

  function wireRematch() {
    var btn = document.getElementById("play-result-again");
    if (!btn || btn.dataset.wired === "1") return;
    btn.dataset.wired = "1";
    btn.addEventListener("click", function () {
      var error = document.getElementById("play-result-error");
      if (error) {
        error.hidden = true;
        error.textContent = "";
      }
      btn.disabled = true;
      var label = btn.textContent;
      btn.textContent = "Starting…";
      api("POST", BASE + "again/", {}).then(function (next) {
        if (next && next.id) window.location.href = "/fools/play/" + next.id + "/";
      }).catch(function (e) {
        btn.disabled = false;
        btn.textContent = label;
        if (error) {
          error.hidden = false;
          error.textContent = e.message || "Could not start another game.";
        }
      });
    });
  }

  function applyState(next, clearSelection) {
    var nextVersion = next && next.runtime ? next.runtime.version : null;
    var currentVersion = state && state.runtime ? state.runtime.version : null;
    if (nextVersion != null && currentVersion != null && nextVersion < currentVersion) {
      return Promise.resolve();
    }
    var clearKind = pendingClear;
    var previous = state;
    var prevLen = previous && previous.table ? previous.table.length : 0;
    var nextLen = next && next.table ? next.table.length : 0;
    var prevPhase = previous && previous.runtime ? previous.runtime.phase : "";
    var nextPhase = next && next.runtime ? next.runtime.phase : "";
    if (!clearKind && prevPhase === "taking" && nextPhase === "between" && nextLen < prevLen) {
      clearKind = "take";
    }
    var prevPassed = previous && previous.runtime ? (previous.runtime.passed_ids || []) : [];
    var nextPassed = next && next.runtime ? (next.runtime.passed_ids || []) : [];
    if (nextPhase !== "taking") confirmAgain = false;
    else if (prevPhase === "taking" && nextLen > prevLen && prevPassed.length && !nextPassed.length) {
      confirmAgain = true;
    } else if (nextPassed.length > prevPassed.length) {
      confirmAgain = false;
    }
    var takerId = previous && previous.runtime ? previous.runtime.defender_id : null;
    pendingClear = null;
    var wait = Promise.resolve();
    if (clearKind && prevLen > 0 && nextLen < prevLen) {
      wait = animateClear(clearKind, takerId);
    }
    return wait.then(function () {
      var previousTable = previous && previous.table ? previous.table : [];
      var plan = planDeal(previous, next, clearKind === "take");
      state = next;
      if (clearSelection) selected.clear();
      if (plan) {
        inboundMine = plan.mine;
        inboundOpp = plan.opp;
        dealView = { deck: plan.deck, trump: plan.trumpStart && plan.deck > 0 };
      }
      render(previousTable);
      if (!plan) return;
      return playDeal(plan);
    });
  }

  function motionOk() {
    return !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function seatOrder(players) {
    return (players || []).slice().sort(function (a, b) {
      return a.seat_position - b.seat_position;
    });
  }

  /** Attacker draws first. The beater or taker is moved to the end, matching the server. */
  function refillOrder(players, startId, lastId) {
    var circle = seatOrder(players);
    var index = circle.findIndex(function (row) {
      return String(row.user_id) === String(startId);
    });
    if (index < 0) index = 0;
    var sequence = [];
    for (var step = 0; step < circle.length; step++) {
      sequence.push(circle[(index + step) % circle.length]);
    }
    if (lastId != null && String(lastId) !== String(startId)) {
      var last = null;
      sequence = sequence.filter(function (row) {
        if (String(row.user_id) !== String(lastId)) return true;
        last = row;
        return false;
      });
      if (last) sequence.push(last);
    }
    return sequence;
  }

  function planDeal(previous, next, took) {
    if (!motionOk() || !next || next.status !== "in_progress") return null;
    var players = seatOrder(next.players);
    var uid = uidStr();
    var steps = [];
    var opening = false;
    if (!previous) {
      var rt0 = next.runtime || {};
      var fresh = rt0.phase === "between" && !(next.table || []).length && !(next.discard_count);
      if (!fresh) return null;
      try {
        if (window.sessionStorage.getItem("fools-opening-deal:" + gameId) === "1") return null;
      } catch (ignore) {}
      opening = true;
      var me0 = players.find(function (row) { return String(row.user_id) === uid; });
      var mine0 = me0 && me0.hand ? me0.hand.slice() : [];
      var at0 = 0;
      players.forEach(function (row) {
        var count = row.cards_remaining || 0;
        for (var i = 0; i < count; i++) {
          var card = null;
          if (String(row.user_id) === uid) card = mine0[at0++] || null;
          steps.push({ userId: String(row.user_id), card: card });
        }
      });
    } else {
      if ((next.deck_remaining || 0) >= (previous.deck_remaining || 0)) return null;
      var prevRt = previous.runtime || {};
      var tableN = 0;
      if (took) {
        (previous.table || []).forEach(function (row) {
          tableN += 1;
          if (row.defense) tableN += 1;
        });
      }
      var taker = took ? String(prevRt.defender_id) : "";
      var prevCount = {};
      (previous.players || []).forEach(function (row) {
        prevCount[String(row.user_id)] = row.cards_remaining || 0;
      });
      var drawnBy = {};
      players.forEach(function (row) {
        var id = String(row.user_id);
        var before = prevCount[id] || 0;
        if (id === taker) before += tableN;
        var got = (row.cards_remaining || 0) - before;
        drawnBy[id] = got > 0 ? got : 0;
      });
      var me1 = players.find(function (row) { return String(row.user_id) === uid; });
      var freshMine = [];
      if (me1 && me1.hand) {
        var seen = {};
        var prevMe = (previous.players || []).find(function (row) {
          return String(row.user_id) === uid;
        });
        ((prevMe && prevMe.hand) || []).forEach(function (card) { seen[card.id] = true; });
        var takenIds = {};
        if (took && uid === taker) {
          (previous.table || []).forEach(function (row) {
            if (row.attack) takenIds[row.attack.id] = true;
            if (row.defense) takenIds[row.defense.id] = true;
          });
        }
        me1.hand.forEach(function (card) {
          if (!seen[card.id] && !takenIds[card.id]) freshMine.push(card);
        });
      }
      var at1 = 0;
      refillOrder(players, prevRt.attacker_id, prevRt.defender_id).forEach(function (row) {
        var id = String(row.user_id);
        var n = drawnBy[id] || 0;
        for (var i = 0; i < n; i++) {
          var card = null;
          if (id === uid) card = freshMine[at1++] || null;
          steps.push({ userId: id, card: card });
        }
      });
    }
    if (!steps.length) return null;
    var mine = {};
    var opp = {};
    steps.forEach(function (step) {
      if (step.userId === uid && step.card) mine[step.card.id] = true;
      else if (step.userId !== uid) opp[step.userId] = (opp[step.userId] || 0) + 1;
    });
    return {
      steps: steps,
      mine: mine,
      opp: opp,
      deck: (next.deck_remaining || 0) + steps.length,
      trumpStart: previous ? !!previous.trump_in_deck : true,
      opening: opening,
    };
  }

  function deckRect() {
    var stack = document.querySelector(".play-deck-stack");
    var el = stack || document.getElementById("deck-trump-corner");
    if (!el) return { left: 24, top: 24, width: 68, height: 96 };
    var box = el.getBoundingClientRect();
    if (!box.width) return { left: 24, top: 24, width: 68, height: 96 };
    return box;
  }

  function dealTargetRect(userId, uid) {
    if (String(userId) === String(uid)) {
      var hand = document.getElementById("hand");
      var mine = hand ? hand.getBoundingClientRect() : { left: 80, top: 400, width: 240, height: 160 };
      return {
        left: mine.left + Math.max(0, mine.width / 2 - 48),
        top: mine.top + 16,
        width: 96,
        height: 134,
      };
    }
    var opp = findOpponent(userId);
    var backs = opp && opp.querySelector(".play-opponent__backs");
    var box = (backs || opp) ? (backs || opp).getBoundingClientRect() : { left: 80, top: 40, width: 80, height: 56 };
    return {
      left: box.left + Math.max(0, box.width / 2 - 21),
      top: box.top,
      width: 42,
      height: 58,
    };
  }

  function launchFlyer(from, to, html) {
    return new Promise(function (resolve) {
      var node = document.createElement("div");
      node.className = "play-deal-flyer";
      node.innerHTML = html;
      node.style.left = from.left + "px";
      node.style.top = from.top + "px";
      node.style.width = from.width + "px";
      document.body.appendChild(node);
      var dx = to.left - from.left;
      var dy = to.top - from.top;
      var scale = from.width ? to.width / from.width : 1;
      var anim = node.animate([
        { transform: "translate(0px, 0px) scale(1)" },
        { transform: "translate(" + dx.toFixed(1) + "px, " + dy.toFixed(1) + "px) scale(" + scale.toFixed(3) + ")" },
      ], { duration: 320, easing: "cubic-bezier(0.2, 0.7, 0.2, 1)", fill: "forwards" });
      function done() {
        node.remove();
        resolve();
      }
      anim.onfinish = done;
      anim.oncancel = done;
    });
  }

  function playDeal(plan) {
    if (plan.opening) {
      try { window.sessionStorage.setItem("fools-opening-deal:" + gameId, "1"); } catch (ignore) {}
    }
    var uid = uidStr();
    var trumpSuit = state && state.trump_card ? state.trump_card.suit : null;
    return new Promise(function (resolve) {
      var left = plan.steps.length;
      function finish() {
        inboundMine = null;
        inboundOpp = null;
        dealView = null;
        render(state.table || []);
        resolve();
      }
      if (!left) {
        finish();
        return;
      }
      plan.steps.forEach(function (step, index) {
        window.setTimeout(function () {
          var from = deckRect();
          var to = dealTargetRect(step.userId, uid);
          var html = step.card ? cardSvgOuterHTML(step.card, {}) : cardBackSvgHTML(step.userId !== uid);
          if (dealView) {
            dealView.deck = Math.max(0, dealView.deck - 1);
            dealView.trump = plan.trumpStart && dealView.deck > 0;
            renderDeckTrumpCorner(state.trump_card, dealView.deck, dealView.trump);
          }
          launchFlyer(from, to, html).then(function () {
            if (step.card && inboundMine) delete inboundMine[step.card.id];
            else if (inboundOpp && inboundOpp[step.userId]) inboundOpp[step.userId] -= 1;
            renderHand(uid, viewer(uid), (state && state.runtime) || {}, trumpSuit);
            renderOpponents(uid, (state && state.runtime) || {});
            if (step.card) {
              var inner = document.querySelector(".play-hand-fan__inner");
              var wrap = findByAttr(inner, "data-cid", step.card.id);
              if (wrap) wrap.classList.add("is-just-dealt");
            } else {
              var opp = findOpponent(step.userId);
              var backs = opp && opp.querySelector(".play-opponent__backs");
              var last = backs && backs.lastElementChild;
              if (last) last.classList.add("is-just-dealt");
            }
            left -= 1;
            if (!left) finish();
          });
        }, index * 110);
      });
    });
  }

  function clearDropTargets() {
    document.querySelectorAll(".is-drop-target, .is-drop-hover").forEach(function (el) {
      el.classList.remove("is-drop-target", "is-drop-hover");
    });
  }

  function markDropTargets(ids) {
    clearDropTargets();
    if (!ids || !ids.length || !state || state.status !== "in_progress") return;
    var uid = uidStr();
    var rt = state.runtime || {};
    var me = viewer(uid);
    var trumpSuit = state.trump_card ? state.trump_card.suit : null;
    var cards = [];
    ids.forEach(function (id) {
      var card = me && me.hand && me.hand.find(function (item) { return item.id === id; });
      if (card) cards.push(card);
    });
    if (cards.length !== ids.length) return;
    var mat = document.getElementById("table-mat");
    if (mat && attackSelectionFits(cards, uid, rt)) mat.classList.add("is-drop-target");
    var wave = rt.phase === "build" || rt.phase === "defend";
    var isDef = String(rt.defender_id) === String(uid);
    if (!(wave && isDef && cards.length === 1)) return;
    document.querySelectorAll(".play-table-pair--open").forEach(function (el) {
      var row = (state.table || []).find(function (item) { return item.id === el.dataset.tableCardId; });
      if (row && canBeatCard(cards[0], row.attack, trumpSuit)) el.classList.add("is-drop-target");
    });
  }

  function watchDropHover(el) {
    if (!el || el.dataset.dropHover === "1") return;
    el.dataset.dropHover = "1";
    el.addEventListener("dragenter", function () {
      if (el.classList.contains("is-drop-target")) el.classList.add("is-drop-hover");
    });
    el.addEventListener("dragleave", function (ev) {
      if (el.contains(ev.relatedTarget)) return;
      el.classList.remove("is-drop-hover");
    });
  }

  function allowDrop(ev) {
    ev.preventDefault();
    ev.dataTransfer.dropEffect = "copy";
  }

  function wireDropTargets(uid, me, rt) {
    rt = rt || {};
    var isDef = rt.defender_id != null && String(rt.defender_id) === String(uid);
    var wave = rt.phase === "build" || rt.phase === "defend";

    var mat = document.getElementById("table-mat");
    if (mat) {
      watchDropHover(mat);
      mat.ondragover = allowDrop;
      mat.ondrop = null;
      if (state.status === "in_progress" && canAddCards(uid, rt)) {
        mat.ondrop = function (ev) {
          ev.preventDefault();
          var ids = getDragCardIds(ev);
          if (!ids || !ids.length) return;
          var cards = [];
          ids.forEach(function (id) {
            var card = me && me.hand && me.hand.find(function (item) { return item.id === id; });
            if (card) cards.push(card);
          });
          if (cards.length !== ids.length || !attackSelectionFits(cards, uid, rt)) {
            setErr("Those cards cannot be played.");
            return;
          }
          postAction(null, "attack/", { card_ids: ids }, true);
        };
      }
    }

    document.querySelectorAll(".play-table-pair").forEach(function (rowEl) {
      rowEl.ondragover = null;
      rowEl.ondrop = null;
    });
    document.querySelectorAll(".play-table-pair--open").forEach(function (rowEl) {
      rowEl.ondragover = allowDrop;
      rowEl.ondrop = null;
      if (state.status === "in_progress" && wave && isDef) {
        rowEl.ondrop = function (ev) {
          ev.preventDefault();
          var ids = getDragCardIds(ev);
          if (!ids || !ids.length) return;
          var tid = rowEl.dataset.tableCardId;
          if (!tid) return;
          var trumpSuit = state.trump_card ? state.trump_card.suit : null;
          var card = me && me.hand && me.hand.find(function (item) { return item.id === ids[0]; });
          var row = (state.table || []).find(function (item) { return item.id === tid; });
          if (card && row && canBeatCard(card, row.attack, trumpSuit)) {
            postAction(null, "defend/", { table_card_id: tid, card_id: ids[0] }, true);
            return;
          }
          setErr("That card cannot beat this attack. To transfer, select the attack rank and press Transfer.");
        };
      }
    });
  }

  function refresh() {
    var run = refreshChain.then(function () {
      return api("GET", BASE).then(function (s) {
        return applyState(s, false);
      });
    }, function () {
      return api("GET", BASE).then(function (s) {
        return applyState(s, false);
      });
    });
    refreshChain = run.then(function () {}, function () {});
    return run;
  }

  function wireLeave() {
    var openBtn = document.getElementById("btn-leave");
    var dialog = document.getElementById("leave-game-dialog");
    var cancel = document.getElementById("leave-cancel");
    var confirmBtn = document.getElementById("leave-confirm");
    var error = document.getElementById("leave-game-error");
    if (!openBtn || openBtn.dataset.wired === "1") return;
    openBtn.dataset.wired = "1";
    if (dialog && dialog.parentNode !== document.body) {
      document.body.appendChild(dialog);
    }

    function askToLeave() {
      if (state && state.status !== "in_progress") {
        window.location.href = "/fools/";
        return;
      }
      if (error) {
        error.hidden = true;
        error.textContent = "";
      }
      if (confirmBtn) confirmBtn.disabled = false;
      if (dialog && typeof dialog.showModal === "function") {
        if (!dialog.open) dialog.showModal();
        return;
      }
      if (window.confirm("Leave this game? You forfeit, and you will be the fool.")) {
        sendLeave(null);
      }
    }

    function sendLeave(button) {
      if (button) button.disabled = true;
      api("POST", BASE + "leave/", {})
        .then(function () {
          window.location.href = "/fools/";
        })
        .catch(function (e) {
          if (button) button.disabled = false;
          if (error) {
            error.hidden = false;
            error.textContent = e.message || "Could not leave the game.";
          }
          setErr(e.message);
        });
    }

    openBtn.addEventListener("click", function (ev) {
      ev.preventDefault();
      askToLeave();
    });
    if (cancel && dialog) {
      cancel.addEventListener("click", function () {
        dialog.close();
      });
    }
    if (confirmBtn) {
      confirmBtn.addEventListener("click", function () {
        sendLeave(confirmBtn);
      });
    }
  }

  function setLink(text) {
    var el = document.getElementById("play-link");
    if (!el) return;
    if (!text) {
      el.hidden = true;
      el.textContent = "";
      return;
    }
    el.hidden = false;
    el.textContent = text;
  }

  var gameSocketRetries = 0;
  var gameSocketToken = 0;

  function connectGameSocket() {
    var token = ++gameSocketToken;
    var wsProto = location.protocol === "https:" ? "wss:" : "ws:";
    if (gameSocketRetries > 0) setLink("Reconnecting…");
    var ws = new WebSocket(wsProto + "//" + location.host + "/ws/games/" + gameId + "/");
    ws.onopen = function () {
      if (token !== gameSocketToken) return;
      gameSocketRetries = 0;
      setLink("");
      refresh().catch(function (e) {
        setErr(e.message);
      });
    };
    ws.onmessage = function (ev) {
      var message = null;
      try {
        message = JSON.parse(ev.data);
      } catch (ignore) {
        message = null;
      }
      if (message && message.event === "rematch_started") {
        var nextGame = message.payload && message.payload.game_id;
        if (nextGame) window.location.href = "/fools/play/" + nextGame + "/";
        return;
      }
      if (message && message.event === "play_announce") {
        showActionBadge(message.payload || {}, true);
        return;
      }
      refresh().catch(function (e) {
        setErr(e.message);
      });
    };
    ws.onclose = function () {
      if (token !== gameSocketToken) return;
      setLink("Connection lost.");
      var delay = Math.min(10000, 800 * Math.pow(2, Math.min(gameSocketRetries, 4)));
      gameSocketRetries += 1;
      window.setTimeout(function () {
        if (token !== gameSocketToken) return;
        setLink("Reconnecting…");
        connectGameSocket();
      }, delay);
    };
  }

  document.addEventListener("DOMContentLoaded", function () {
    loadHandSort();
    paintSortButton();
    wireSort();
    wireRematch();
    var seatLayout = window.matchMedia("(min-width: 900px)");
    seatLayout.addEventListener("change", function () {
      if (state) render(state.table || []);
    });
    loadHistory();
    paintHistory();
    wireActionButtons();
    wireLeave();
    connectGameSocket();

    api("GET", "/api/accounts/auth/profile/")
      .then(function (p) {
        profile = p;
        return refresh();
      })
      .catch(function (e) {
        setErr(e.message);
      });
  });
})();
