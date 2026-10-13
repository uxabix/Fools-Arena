/**
 * Classic podkidnoy Durak table: SVG cards, opponents, felt, deck + trump.
 * Drag-and-drop is only for cards (attack / throw-in / defend); other actions use buttons.
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

  function isRedSuit(suit) {
    return suit === "Hearts" || suit === "Diamonds";
  }

  function suitNameEn(suit) {
    var m = { Hearts: "hearts", Diamonds: "diamonds", Clubs: "clubs", Spades: "spades" };
    return m[suit] || suit;
  }

  function phaseEn(phase) {
    var m = {
      between: "Break",
      build: "Table (attack & defense)",
      defend: "Table (legacy)",
      taking: "Taking",
    };
    return m[phase] || phase || "—";
  }

  /**
   * @param {{rank:string,suit:string}} card
   * @param {{mini?:boolean}} opts
   */
  function cardSvgOuterHTML(card, opts) {
    opts = opts || {};
    var mini = !!opts.mini;
    var ink = isRedSuit(card.suit) ? "#b71c1c" : "#212121";
    var sym = SUIT_SYMBOL[card.suit] || "?";
    var rnk = rankShort(card.rank);
    var vb = mini ? "0 0 58 80" : "0 0 76 104";
    var fsCorner = mini ? 10 : 11;
    var fsCenter = mini ? 28 : 36;
    var rw = mini ? 54 : 70;
    var rh = mini ? 76 : 98;
    var rx = mini ? 2 : 2;
    var ry = mini ? 2 : 2;
    var brRankX = mini ? 52 : 67;
    var brRankY = mini ? 72 : 93;
    var brSymX = mini ? 52 : 67;
    var brSymY = mini ? 59 : 77;
    var brSymFs = mini ? 10 : 11;

    return (
      '<svg class="play-card-svg" viewBox="' +
      vb +
      '" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" shape-rendering="geometricPrecision" text-rendering="geometricPrecision" overflow="hidden">' +
      '<rect x="' +
      rx +
      '" y="' +
      ry +
      '" width="' +
      rw +
      '" height="' +
      rh +
      '" rx="5" fill="#faf8f5" stroke="#2c2c2c" stroke-width="1.2"/>' +
      '<text x="' +
      (mini ? 7 : 8) +
      '" y="' +
      (mini ? 17 : 20) +
      '" font-size="' +
      fsCorner +
      '" font-weight="700" fill="' +
      ink +
      '" font-family="Georgia,serif">' +
      rnk +
      "</text>" +
      '<text x="' +
      (mini ? 7 : 8) +
      '" y="' +
      (mini ? 31 : 36) +
      '" font-size="' +
      (mini ? 11 : 13) +
      '" fill="' +
      ink +
      '">' +
      sym +
      "</text>" +
      '<text x="' +
      (mini ? 29 : 37) +
      '" y="' +
      (mini ? 49 : 64) +
      '" font-size="' +
      fsCenter +
      '" text-anchor="middle" fill="' +
      ink +
      '">' +
      sym +
      "</text>" +
      '<text x="' +
      brSymX +
      '" y="' +
      brSymY +
      '" font-size="' +
      brSymFs +
      '" text-anchor="end" fill="' +
      ink +
      '">' +
      sym +
      "</text>" +
      '<text x="' +
      brRankX +
      '" y="' +
      brRankY +
      '" font-size="' +
      fsCorner +
      '" font-weight="700" fill="' +
      ink +
      '" font-family="Georgia,serif" text-anchor="end">' +
      rnk +
      "</text>" +
      "</svg>"
    );
  }

  function cardBackSvgHTML(mini) {
    var vb = mini ? "0 0 58 80" : "0 0 76 104";
    var w = mini ? 54 : 70;
    var h = mini ? 76 : 98;
    var pid = "pb-" + Math.random().toString(36).slice(2, 11);
    return (
      '<svg class="play-card-svg play-card-svg--back" viewBox="' +
      vb +
      '" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" shape-rendering="geometricPrecision" overflow="hidden">' +
      '<defs><pattern id="' +
      pid +
      '" width="8" height="8" patternUnits="userSpaceOnUse">' +
      '<rect width="8" height="8" fill="#334b66"/>' +
      '<path d="M0 8 L8 0 M-2 2 L2 -2 M6 10 L10 6" stroke="#1a2538" stroke-width="1.05" fill="none"/></pattern></defs>' +
      '<rect x="2" y="2" width="' +
      w +
      '" height="' +
      h +
      '" rx="5" fill="url(#' +
      pid +
      ')" stroke="#c9a227" stroke-width="1.5"/>' +
      '<rect x="6" y="6" width="' +
      (w - 8) +
      '" height="' +
      (h - 8) +
      '" rx="3" fill="none" stroke="rgba(201,162,39,0.45)" stroke-width="1"/>' +
      "</svg>"
    );
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

  function otherPlayers(uid) {
    return state.players
      .slice()
      .sort(function (a, b) {
        return a.seat_position - b.seat_position;
      })
      .filter(function (p) {
        return String(p.user_id) !== uid;
      });
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
    var table = state.table || [];
    var open = table.filter(function (row) { return !row.defense; }).length;
    var actor = rt.attacker_id;
    if (rt.phase !== "between" && open > 0) actor = rt.defender_id;
    else if (rt.phase !== "between" && table.length) actor = rt.attacker_id;
    if (rt.phase === "between" && seatCards(actor) === 0) return null;
    return actor;
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

  function renderOpponents(uid, rt) {
    var el = document.getElementById("opponents");
    if (!el) return;
    el.innerHTML = "";
    var others = otherPlayers(uid);
    if (!others.length) return;
    others.forEach(function (p) {
      var roleKey = playerRoleKey(p.user_id, rt);
      var mustAct = mustConfirm(p.user_id, rt) || (
        expectedActorId(rt) != null && String(expectedActorId(rt)) === String(p.user_id)
      );
      var duty = roleKey === "out" ? "Out" : mustAct ? "Your turn" : "Waiting";
      var div = document.createElement("div");
      div.className = "play-opponent is-" + roleKey + (mustAct ? " is-acting" : " is-waiting");
      div.dataset.seat = String(p.user_id);
      var n = p.cards_remaining != null ? p.cards_remaining : 0;
      var backs = "";
      var show = Math.min(6, Math.max(0, n));
      for (var i = 0; i < show; i++) {
        backs +=
          '<span class="play-opponent__back" style="--i:' + i + '">' + cardBackSvgHTML(true) + "</span>";
      }
      div.innerHTML =
        '<div class="play-seat-mark" aria-hidden="true">' + roleIcon(roleKey) + "</div>" +
        '<div class="play-opponent__info">' +
        '<span class="play-role play-role--' + roleKey + '">' +
        roleIcon(roleKey) +
        "<span>" + roleLabel(roleKey) + "</span></span>" +
        '<span class="play-opponent__name">' +
        escapeHtml(p.username) +
        "</span>" +
        '<span class="play-opponent__meta">' +
        n +
        " cards · " +
        duty +
        "</span></div>" +
        '<div class="play-opponent__backs">' +
        backs +
        "</div>";
      el.appendChild(div);
    });
  }

  function escapeHtml(s) {
    var d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
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
    var partsArr = ["Podkidnoy Durak"];
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
      el.textContent = state.loser_id && String(state.loser_id) === uid
        ? "You lost (fool)."
        : "Round finished.";
      if (sign) sign.innerHTML = "";
      if (area) area.className = "play-my-area";
      return;
    }
    var key = playerRoleKey(uid, rt);
    var mustAct = mustConfirm(uid, rt) || (
      expectedActorId(rt) != null && String(expectedActorId(rt)) === String(uid)
    );
    el.innerHTML =
      '<span class="play-role play-role--' + key + '">' +
      roleIcon(key) +
      "<span>" + roleLabel(key) + "</span></span>";
    if (sign) {
      sign.innerHTML = key === "wait" ? "" : roleIcon(key);
      sign.className = "play-my-sign is-" + key;
    }
    if (area) {
      area.className = "play-my-area is-" + key + (mustAct ? " is-acting" : " is-waiting");
    }
  }

  function throwRanksIHold(me) {
    if (!me || !me.hand) return [];
    var onTable = tableRankNames();
    var seen = {};
    var labels = [];
    me.hand.forEach(function (card) {
      if (onTable[card.value] && !seen[card.value]) {
        seen[card.value] = true;
        labels.push(rankShort(card.rank));
      }
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
    return (next.cards_remaining || 0) >= ((state.table || []).length + extra);
  }

  function selectedPassIds(me) {
    var rank = singleAttackRank();
    if (rank == null || !me || !me.hand) return [];
    return me.hand.filter(function (card) {
      return selected.has(card.id) && card.value === rank;
    }).map(function (card) { return card.id; });
  }

  function postTransfer(ids) {
    if (!ids || !ids.length) return;
    setErr("");
    announceMine("transfer");
    api("POST", BASE + "transfer/", { card_ids: ids })
      .then(function (s) {
        return applyState(s, true);
      })
      .catch(function (e) {
        setErr(e.message);
      });
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
    if (taking && mustConfirm(uid, rt)) {
      return "The defender is taking the cards. Throw in more, or press Done.";
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
      return "Pass the attack with " + (passName || "a matching card") + ", beat the cards, or press Take cards.";
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
    var throwable = throwRanksIHold(me);
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
    if (!rt || state.status !== "in_progress" || !me) return false;
    var isAtt = String(rt.attacker_id) === uid;
    var isDef = String(rt.defender_id) === uid;
    var wave = rt.phase === "build" || rt.phase === "defend" || rt.phase === "taking";
    if (rt.phase === "between") return isAtt;
    if (rt.phase !== "taking" && isDef && openCount() > 0) {
      if (transferRoom(1) && card.value === singleAttackRank()) return true;
      return (state.table || []).some(function (row) {
        return !row.defense && canBeatCard(card, row.attack, trumpSuit);
      });
    }
    if (wave && !isDef) {
      return !!tableRankNames()[card.value];
    }
    return false;
  }

  function wireActionButtons() {
    var take = document.getElementById("btn-take");
    var bito = document.getElementById("btn-bito");
    var done = document.getElementById("btn-done");
    var pass = document.getElementById("btn-transfer");
    function once(btn, handler) {
      if (!btn || btn.dataset.wired === "1") return;
      btn.dataset.wired = "1";
      btn.addEventListener("click", handler);
    }
    once(pass, function () {
      var me = (state.players || []).find(function (row) {
        return String(row.user_id) === uidStr();
      });
      var ids = selectedPassIds(me);
      if (!ids.length || !transferRoom(ids.length)) {
        setErr("Select cards of the attack rank to pass.");
        return;
      }
      pass.disabled = true;
      postTransfer(ids);
    });
    once(take, function () {
      setErr("");
      announceMine("take");
      take.disabled = true;
      api("POST", BASE + "take/", {})
        .then(function (s) {
          return applyState(s, true);
        })
        .catch(function (e) {
          setErr(e.message);
        });
    });
    once(done, function () {
      setErr("");
      announceMine("pass");
      done.disabled = true;
      api("POST", BASE + "pass/", {})
        .then(function (s) {
          return applyState(s, true);
        })
        .catch(function (e) {
          setErr(e.message);
        });
    });
    once(bito, function () {
      setErr("");
      announceMine("bito");
      bito.disabled = true;
      api("POST", BASE + "bito/", {})
        .then(function (s) {
          return applyState(s, true);
        })
        .catch(function (e) {
          setErr(e.message);
        });
    });
  }

  function updateActionButtons(uid, rt) {
    rt = rt || {};
    var isAtt = rt.attacker_id != null && String(rt.attacker_id) === uid;
    var isDef = rt.defender_id != null && String(rt.defender_id) === uid;
    var takeBtn = document.getElementById("btn-take");
    var bitoBtn = document.getElementById("btn-bito");
    var doneBtn = document.getElementById("btn-done");
    var passBtn = document.getElementById("btn-transfer");
    var me = (state.players || []).find(function (row) {
      return String(row.user_id) === String(uid);
    });
    var passIds = selectedPassIds(me);
    var inProg = state.status === "in_progress";
    var wave = rt.phase === "build" || rt.phase === "defend";
    var tbl = state.table || [];
    var show = inProg && wave && tbl.length > 0;
    var allDefended =
      tbl.length > 0 && tbl.every(function (r) { return r.defense; });

    if (takeBtn) {
      takeBtn.hidden = !(show && isDef);
      takeBtn.disabled = false;
      takeBtn.setAttribute("aria-disabled", "false");
    }
    if (bitoBtn) {
      bitoBtn.hidden = !(show && isAtt && allDefended);
      bitoBtn.disabled = false;
      bitoBtn.setAttribute("aria-disabled", "false");
    }
    if (doneBtn) {
      doneBtn.hidden = !(inProg && mustConfirm(uid, rt));
      doneBtn.disabled = false;
      doneBtn.setAttribute("aria-disabled", "false");
    }
    if (passBtn) {
      var canPass = show && isDef && transferRoom(1);
      passBtn.hidden = !canPass;
      passBtn.disabled = !(canPass && passIds.length > 0 && transferRoom(passIds.length));
      passBtn.setAttribute("aria-disabled", passBtn.disabled ? "true" : "false");
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
    var socket = new WebSocket(proto + "//" + location.host + "/ws/lobbies/" + lobbyId + "/");
    socket.onmessage = function (ev) {
      var message = null;
      try {
        message = JSON.parse(ev.data);
      } catch (ignore) {
        message = null;
      }
      if (message && message.event === "lobby_chat") appendMessage(message.payload || {});
    };
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
    renderMyRole(uid, rt);
    renderOpponents(uid, rt);
    renderDeckTrumpCorner(tcTrump, state.deck_remaining || 0, !!state.trump_in_deck);
    renderDiscard();

    pruneSelection(me && me.hand);
    var handEl = document.getElementById("hand");
    if (handEl) {
      handEl.innerHTML = "";
      if (me && me.hand) {
        var inner = document.createElement("div");
        inner.className = "play-hand-fan__inner";
        var n = me.hand.length;
        var mid = (n - 1) / 2;
        var maxDist = Math.max(mid, n - 1 - mid) || 1;
        me.hand.forEach(function (c, idx) {
          var wrap = document.createElement("div");
          wrap.className = "play-card play-card--hand";
          wrap.dataset.cid = c.id;
          if (trumpSuit && c.suit === trumpSuit) wrap.classList.add("play-card--trump");
          if (selected.has(c.id)) wrap.classList.add("is-selected");
          if (cardIsLegal(c, uid, me, rt, trumpSuit)) wrap.classList.add("is-legal");
          else wrap.classList.add("is-dim");
          wrap.setAttribute("draggable", "true");
          wrap.setAttribute("aria-label", c.rank + " " + c.suit);
          wrap.innerHTML = cardSvgOuterHTML(c, {});
          var dist = Math.abs(idx - mid);
          var norm = dist / maxDist;
          var rot = (idx - mid) * 7.25;
          var y = norm * norm * 16 + norm * 3;
          var x = (idx - mid) * 0.85;
          wrap.style.setProperty("--fan-rot", rot + "deg");
          wrap.style.setProperty("--fan-y", y + "px");
          wrap.style.setProperty("--fan-x", x + "px");
          wrap.style.zIndex = String(30 - Math.abs(idx - mid));
          wrap.addEventListener("click", function (ev) {
            ev.preventDefault();
            if (selected.has(c.id)) selected.delete(c.id);
            else selected.add(c.id);
            wrap.classList.toggle("is-selected", selected.has(c.id));
            updateActionButtons(uid, rt);
          });
          wrap.addEventListener("dragstart", function (ev) {
            var ids = attackPayloadFromDrag(c.id);
            setDragCardIds(ev, ids);
            wrap.classList.add("is-dragging");
          });
          wrap.addEventListener("dragend", function () {
            wrap.classList.remove("is-dragging");
          });
          inner.appendChild(wrap);
        });
        handEl.appendChild(inner);
      }
    }

    var seenRows = {};
    previousTable.forEach(function (row) {
      seenRows[row.id] = row;
    });
    var tbl = document.getElementById("table-rows");
    if (tbl) {
      tbl.innerHTML = "";
      tbl.classList.toggle("is-two-rows", state.table.length > 3);
      var fromMe = activeBadge && String(activeBadge.userId) === uid;
      state.table.forEach(function (row) {
        var d = document.createElement("div");
        d.className = "play-table-pair";
        if (!seenRows[row.id]) {
          d.classList.add("is-arriving");
          if (fromMe) d.classList.add("is-from-me");
        }
        d.dataset.tableCardId = row.id;
        if (!row.defense) d.classList.add("play-table-pair--open");
        var chosen = null;
        if (me && me.hand && selected.size === 1) {
          chosen = me.hand.find(function (card) { return selected.has(card.id); });
        }
        if (
          chosen &&
          !row.defense &&
          String(rt.defender_id) === uid &&
          canBeatCard(chosen, row.attack, trumpSuit)
        ) {
          d.classList.add("is-legal-target");
        }

        var stack = document.createElement("div");
        stack.className = "play-table-stack";

        var peek = stackPeekFromRowId(row.id);

        var def = document.createElement("div");
        def.className =
          "play-card play-card--table play-card--stack-def" +
          (row.defense ? "" : " play-card--placeholder");
        var previous = seenRows[row.id];
        if (row.defense && (!previous || !previous.defense)) {
          def.classList.add("is-covering");
          if (String(rt.defender_id) === uid) def.classList.add("is-from-me");
        }
        def.innerHTML = row.defense ? cardSvgOuterHTML(row.defense, {}) : "";
        def.style.setProperty("--peek-def-x", peek.dxA);
        def.style.setProperty("--peek-def-y", peek.dyA);
        def.style.setProperty("--peek-def-rot", peek.rotA);

        var atk = document.createElement("div");
        atk.className = "play-card play-card--table play-card--stack-atk";
        atk.innerHTML = cardSvgOuterHTML(row.attack, {});
        atk.style.setProperty("--peek-atk-x", peek.dxD);
        atk.style.setProperty("--peek-atk-y", peek.dyD);
        atk.style.setProperty("--peek-atk-rot", peek.rotD);

        stack.appendChild(atk);
        stack.appendChild(def);
        d.appendChild(stack);

        tbl.appendChild(d);
      });
    }

    wireDropTargets(uid, me, rt);
    updateActionButtons(uid, rt);

    var hint = document.getElementById("play-hint");
    if (hint) hint.textContent = hintText(uid, me, rt);
    paintBadge();
  }

  var ACTION_LABEL = {
    take: "Took cards",
    bito: "Beaten",
    transfer: "Passed",
    pass: "Done",
  };
  var recentActions = [];

  function cardFace(card) {
    if (!card) return "";
    return rankShort(card.rank) + (SUIT_SYMBOL[card.suit] || "");
  }

  function actionPhrase(payload) {
    var cards = (payload.cards || []).map(cardFace).filter(Boolean).join(", ");
    if (payload.action === "attack") return "Threw " + cards;
    if (payload.action === "defend") return "Beat " + cards;
    if (payload.action === "transfer") return cards ? "Passed " + cards : "Passed the attack";
    return ACTION_LABEL[payload.action] || "Played";
  }

  function announceMine(action) {
    if (!profile || profile.id == null) return;
    showActionBadge({ action: action, user_id: profile.id }, false);
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
        recentActions = recentActions.slice(0, 5);
      }
      paintHistory();
    }
    paintBadge();
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
  }

  function paintBadge() {
    document.querySelectorAll(".play-action-badge").forEach(function (el) {
      el.remove();
    });
    if (!activeBadge || Date.now() > activeBadge.until) {
      activeBadge = null;
      return;
    }
    var seat = document.querySelector('[data-seat="' + activeBadge.userId + '"]');
    if (!seat) return;
    var badge = document.createElement("p");
    badge.className = "play-action-badge play-action-badge--" + (activeBadge.action || "take");
    badge.textContent = activeBadge.text || ACTION_LABEL[activeBadge.action] || "Played";
    seat.appendChild(badge);
  }

  function animateClear(kind) {
    var rows = document.querySelectorAll(".play-table-pair");
    if (!rows.length) return Promise.resolve();
    rows.forEach(function (row) {
      row.classList.add(kind === "take" ? "is-taking" : "is-discarding");
    });
    return new Promise(function (resolve) {
      window.setTimeout(resolve, 250);
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
    pendingClear = null;
    var wait = Promise.resolve();
    if (clearKind && prevLen > 0 && nextLen < prevLen) {
      wait = animateClear(clearKind);
    }
    return wait.then(function () {
      var previousTable = previous && previous.table ? previous.table : [];
      state = next;
      if (clearSelection) selected.clear();
      render(previousTable);
    });
  }

  function allowDrop(ev) {
    ev.preventDefault();
    ev.dataTransfer.dropEffect = "copy";
  }

  function wireDropTargets(uid, me, rt) {
    rt = rt || {};
    var isAtt = rt.attacker_id != null && String(rt.attacker_id) === uid;
    var isDef = rt.defender_id != null && String(rt.defender_id) === uid;
    var wave = rt.phase === "build" || rt.phase === "defend";
    var canThrow = wave || rt.phase === "taking";

    var mat = document.getElementById("table-mat");
    if (mat) {
      mat.ondragover = allowDrop;
      mat.ondrop = null;
      var allowMat =
        state.status === "in_progress" &&
        (rt.phase === "between" || canThrow) &&
        (rt.phase === "between" ? isAtt : !isDef);
      var allowPass = state.status === "in_progress" && isDef && transferRoom(1);
      if (allowMat || allowPass) {
        mat.ondrop = function (ev) {
          ev.preventDefault();
          var ids = getDragCardIds(ev);
          if (!ids || !ids.length) return;
          var rank = singleAttackRank();
          var passing = allowPass && me && me.hand && ids.every(function (id) {
            var card = me.hand.find(function (item) { return item.id === id; });
            return card && card.value === rank;
          });
          if (passing) {
            if (!transferRoom(ids.length)) {
              setErr("The next player cannot take that many cards.");
              return;
            }
            postTransfer(ids);
            return;
          }
          if (!allowMat) return;
          setErr("");
          api("POST", BASE + "attack/", { card_ids: ids })
            .then(function (s) {
              return applyState(s, true);
            })
            .catch(function (e) {
              setErr(e.message);
            });
        };
      }
    }

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
            setErr("");
            api("POST", BASE + "defend/", { table_card_id: tid, card_id: ids[0] })
              .then(function (s) {
                return applyState(s, true);
              })
              .catch(function (e) {
                setErr(e.message);
              });
            return;
          }
          var rank = singleAttackRank();
          if (rank != null && ids.every(function (id) {
            var held = me && me.hand && me.hand.find(function (item) { return item.id === id; });
            return held && held.value === rank;
          }) && transferRoom(ids.length)) {
            postTransfer(ids);
            return;
          }
          setErr("That card cannot beat this attack.");
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

  document.addEventListener("DOMContentLoaded", function () {
    wireActionButtons();
    wireLeave();
    var wsProto = location.protocol === "https:" ? "wss:" : "ws:";
    var ws = new WebSocket(wsProto + "//" + location.host + "/ws/games/" + gameId + "/");
    ws.onopen = function () {
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
      if (message && message.event === "play_announce") {
        showActionBadge(message.payload || {}, true);
        return;
      }
      refresh().catch(function (e) {
        setErr(e.message);
      });
    };

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
