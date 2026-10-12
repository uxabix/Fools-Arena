/**
 * Login and registration forms: field checks, password rules, show/hide, submit state.
 * Server-side validation remains the source of truth. This script only
 * explains failures earlier and does not block paste or password managers.
 */
(function () {
  "use strict";

  document.querySelectorAll(".auth-field__reveal").forEach(function (button) {
    button.addEventListener("click", function () {
      var input = document.getElementById(button.getAttribute("aria-controls"));
      if (!input) return;
      var showing = input.type === "password";
      input.type = showing ? "text" : "password";
      button.setAttribute("aria-pressed", showing ? "true" : "false");
      button.setAttribute("aria-label", showing ? "Hide password" : "Show password");
      var showIcon = button.querySelector("[data-icon='show']");
      var hideIcon = button.querySelector("[data-icon='hide']");
      if (showIcon) showIcon.hidden = showing;
      if (hideIcon) hideIcon.hidden = !showing;
    });
  });

  document.querySelectorAll("form[data-busy-submit]").forEach(function (busyForm) {
    busyForm.addEventListener("submit", function () {
      var button = busyForm.querySelector("[type=submit]");
      if (!button) return;
      var label = button.querySelector(".auth-submit__label");
      var loadingText = button.getAttribute("data-loading-label");
      if (label && loadingText) label.textContent = loadingText;
      button.setAttribute("aria-busy", "true");
      button.classList.add("is-loading");
      window.setTimeout(function () {
        button.disabled = true;
      }, 0);
    });
  });

  var form = document.querySelector("[data-auth-form]");
  if (!form) return;

  var mode = form.getAttribute("data-auth-form");
  var passwordKey = (mode === "reset" || mode === "password") ? "new_password1" : "password1";
  var confirmKey = (mode === "reset" || mode === "password") ? "new_password2" : "password2";
  var minLength = parseInt(form.getAttribute("data-password-min") || "8", 10);
  var maxLength = parseInt(form.getAttribute("data-password-max") || "128", 10);
  var usernameMin = parseInt(form.getAttribute("data-username-min") || "3", 10);
  var usernameMax = parseInt(form.getAttribute("data-username-max") || "30", 10);
  var reservedNames = (form.getAttribute("data-reserved-usernames") || "")
    .split(",")
    .filter(Boolean);
  var revealed = {};
  var submitAttempted = false;
  var initial = {};
  var serverMessages = {};
  var submitting = false;

  var MARK = { idle: "\u25CB", pending: "\u25CB", met: "\u2713", unmet: "!" };
  var STATUS = {
    idle: "Not checked yet",
    pending: "Checked when you submit",
    met: "Met",
    unmet: "Not met",
  };

  function fieldWrap(name) {
    return form.querySelector('[data-field="' + name + '"]');
  }

  function inputOf(name) {
    var wrap = fieldWrap(name);
    return wrap ? wrap.querySelector("input") : null;
  }

  function feedbackOf(name) {
    var wrap = fieldWrap(name);
    return wrap ? wrap.querySelector(".auth-field__feedback") : null;
  }

  function setRule(rule, state) {
    var item = form.querySelector('.auth-rules__item[data-rule="' + rule + '"]');
    if (!item) return;
    item.setAttribute("data-state", state);
    var mark = item.querySelector(".auth-rules__mark");
    var status = item.querySelector(".auth-rules__status");
    var note = item.querySelector(".auth-rules__note");
    if (mark) mark.textContent = MARK[state] || MARK.idle;
    if (status) status.textContent = STATUS[state] || "";
    if (note) note.hidden = state === "met" || state === "unmet";
  }

  function showFeedback(name, messages, kind) {
    var wrap = fieldWrap(name);
    var feedback = feedbackOf(name);
    var input = inputOf(name);
    if (!wrap || !feedback) return;
    var signature = (kind || "error") + ":" + messages.join("\n");
    if (feedback.getAttribute("data-signature") === signature) return;
    feedback.setAttribute("data-signature", signature);
    feedback.textContent = "";
    if (!messages.length) {
      wrap.classList.remove("is-invalid");
      if (input) input.removeAttribute("aria-invalid");
      return;
    }
    if (kind === "ok") {
      wrap.classList.remove("is-invalid");
      if (input) input.removeAttribute("aria-invalid");
      feedback.appendChild(messageNode("auth-match", "status", "\u2713", messages[0]));
      return;
    }
    wrap.classList.add("is-invalid");
    if (input) input.setAttribute("aria-invalid", "true");
    messages.forEach(function (message) {
      feedback.appendChild(messageNode("field-error", "alert", "\u26A0", message));
    });
  }

  function messageNode(className, role, icon, message) {
    var row = document.createElement("p");
    row.className = className;
    row.setAttribute("role", role);
    var iconNode = document.createElement("span");
    iconNode.className = className === "field-error" ? "field-error__icon" : "auth-match__icon";
    iconNode.setAttribute("aria-hidden", "true");
    iconNode.textContent = icon;
    var text = document.createElement("span");
    text.textContent = message;
    row.appendChild(iconNode);
    row.appendChild(text);
    return row;
  }

  function clearFeedback(name) {
    showFeedback(name, [], "error");
  }

  function matchingChars(a, b) {
    if (!a || !b) return 0;
    var bestLen = 0;
    var bestI = 0;
    var bestJ = 0;
    var i;
    var j;
    var len;
    for (i = 0; i < a.length; i++) {
      for (j = 0; j < b.length; j++) {
        len = 0;
        while (i + len < a.length && j + len < b.length && a.charAt(i + len) === b.charAt(j + len)) {
          len += 1;
        }
        if (len > bestLen) {
          bestLen = len;
          bestI = i;
          bestJ = j;
        }
      }
    }
    if (!bestLen) return 0;
    return bestLen
      + matchingChars(a.slice(0, bestI), b.slice(0, bestJ))
      + matchingChars(a.slice(bestI + bestLen), b.slice(bestJ + bestLen));
  }

  function similarity(a, b) {
    if (!a || !b) return 0;
    if (a === b) return 1;
    // Long values skip the full match so typing stays responsive.
    // The server still runs Django's similarity validator on submit.
    if (a.length * b.length > 2500) {
      var shorter = a.length < b.length ? a : b;
      var longer = a.length < b.length ? b : a;
      if (longer.indexOf(shorter) !== -1) return shorter.length / longer.length;
      return 0;
    }
    return (2 * matchingChars(a, b)) / (a.length + b.length);
  }

  function identityParts() {
    var parts = [];
    function add(value) {
      if (!value) return;
      var lower = value.trim().toLowerCase();
      if (!lower) return;
      parts.push(lower);
      lower.split(/[^0-9a-z]+/).forEach(function (bit) {
        if (bit && parts.indexOf(bit) === -1) parts.push(bit);
      });
    }
    var username = inputOf("username");
    var email = inputOf("email");
    if (username) add(username.value);
    if (email) add(email.value);
    return parts;
  }

  function tooSimilar(password) {
    var parts = identityParts();
    var lower = password.toLowerCase();
    for (var i = 0; i < parts.length; i++) {
      if (similarity(lower, parts[i]) >= 0.7) return true;
    }
    return false;
  }

  function updateRules(showFailures) {
    if (mode !== "register" && mode !== "reset" && mode !== "password") return;
    var password = inputOf(passwordKey);
    var value = password ? password.value : "";
    if (!value) {
      setRule("length", "idle");
      setRule("numeric", "idle");
      setRule("similar", "idle");
    } else {
      setRule("length", value.length >= minLength ? "met" : (showFailures ? "unmet" : "idle"));
      setRule("numeric", /^[0-9]+$/.test(value) ? (showFailures ? "unmet" : "idle") : "met");
      if (tooSimilar(value)) setRule("similar", showFailures ? "unmet" : "idle");
      else if (identityParts().length) setRule("similar", "met");
      else setRule("similar", "idle");
    }
    var sameAsServer = password && password.value === initial[passwordKey] && serverMessages[passwordKey];
    if (sameAsServer) applyServerRules();
    else setRule("common", "pending");
  }

  function applyServerRules() {
    var messages = []
      .concat(serverMessages[passwordKey] || [])
      .concat(serverMessages[confirmKey] || []);
    var text = messages.join(" ").toLowerCase();
    if (!text) return;
    if (text.indexOf("too short") !== -1 || text.indexOf("at least") !== -1) setRule("length", "unmet");
    if (text.indexOf("entirely numeric") !== -1 || text.indexOf("only numbers") !== -1) setRule("numeric", "unmet");
    if (text.indexOf("too similar") !== -1 || text.indexOf("less similar") !== -1) setRule("similar", "unmet");
    if (text.indexOf("too common") !== -1 || text.indexOf("common password") !== -1) setRule("common", "unmet");
  }

  function passwordMessage(value, showFailures) {
    if (!value) return "Enter a password.";
    if (value.length > maxLength) return "Use " + maxLength + " characters or fewer.";
    if (!showFailures) return "";
    if (value.length < minLength) return "Use at least " + minLength + " characters.";
    if (/^[0-9]+$/.test(value)) return "Use a password that is not only numbers.";
    if (tooSimilar(value)) return "Choose a password less similar to your username or email.";
    return "";
  }

  function serverStillApplies(name) {
    var input = inputOf(name);
    if (!input || !serverMessages[name]) return false;
    return input.value === initial[name];
  }

  function validateUsername(showFailures) {
    var value = inputOf("username").value;
    if (!showFailures && !revealed.username) return true;
    if (serverStillApplies("username")) {
      showFeedback("username", serverMessages.username, "error");
      return false;
    }
    if (mode === "register") {
      var problem = usernameProblem(value);
      if (problem) {
        showFeedback("username", [problem], "error");
        return false;
      }
    } else if (!value) {
      showFeedback("username", ["Enter a username."], "error");
      return false;
    }
    clearFeedback("username");
    return true;
  }

  function usernameProblem(value) {
    var i;
    var code;
    var folded;
    var squashed;
    if (!value) return "Enter a username.";
    if (/\s/.test(value)) return "Usernames cannot contain spaces.";
    for (i = 0; i < value.length; i++) {
      code = value.charCodeAt(i);
      if (code < 32 || code === 127 || code === 0xfeff
          || (code >= 0x200b && code <= 0x200f)
          || (code >= 0x202a && code <= 0x202e)
          || code === 0x2060) {
        return "Usernames cannot contain invisible or control characters.";
      }
    }
    if (/[<>&"'`]/.test(value)) return "Usernames cannot contain HTML.";
    if (/https?:|www\.|[/\\@]|[a-z0-9-]+\.[a-z]{2,}/i.test(value)) {
      return "Usernames cannot contain a web address.";
    }
    if (!/^[A-Za-z0-9_]+$/.test(value)) {
      return "Use only letters, numbers, and underscore.";
    }
    if (value.length < usernameMin) {
      return "Use at least " + usernameMin + " characters.";
    }
    if (value.length > usernameMax) {
      return "Use " + usernameMax + " characters or fewer.";
    }
    folded = value.toLowerCase();
    squashed = folded.replace(/_/g, "");
    if (reservedNames.indexOf(folded) !== -1 || reservedNames.indexOf(squashed) !== -1) {
      return "This username is reserved.";
    }
    return "";
  }

  function validateEmail(showFailures) {
    var input = inputOf("email");
    if (!input) return true;
    var value = input.value.trim();
    if (!showFailures && !revealed.email) return true;
    if (serverStillApplies("email")) {
      showFeedback("email", serverMessages.email, "error");
      return false;
    }
    if (!value) {
      showFeedback("email", ["Enter your email."], "error");
      return false;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
      showFeedback("email", ["Enter a valid email address, such as name@example.com."], "error");
      return false;
    }
    clearFeedback("email");
    return true;
  }

  function validatePassword(showFailures) {
    var name = mode === "login" ? "password" : passwordKey;
    var value = inputOf(name).value;
    var show = showFailures || revealed[name];
    if (mode === "register" || mode === "reset" || mode === "password") updateRules(show);
    if (!show) return true;
    if (serverStillApplies(name)) {
      showFeedback(name, serverMessages[name], "error");
      if (mode === "register" || mode === "reset" || mode === "password") applyServerRules();
      return false;
    }
    if (mode === "login") {
      if (!value) {
        showFeedback(name, ["Enter your password."], "error");
        return false;
      }
      clearFeedback(name);
      return true;
    }
    var message = passwordMessage(value, true);
    if (message) {
      showFeedback(name, [message], "error");
      return false;
    }
    clearFeedback(name);
    return true;
  }

  function validateConfirm(showFailures) {
    var passwordInput = inputOf(passwordKey);
    var confirmInput = inputOf(confirmKey);
    if (!passwordInput || !confirmInput) return true;
    var password = passwordInput.value;
    var confirm = confirmInput.value;
    var show = showFailures || revealed[confirmKey];
    if (password && confirm && password === confirm) {
      showFeedback(confirmKey, ["Passwords match"], "ok");
      return true;
    }
    if (serverStillApplies(confirmKey) && passwordInput.value === initial[passwordKey]) {
      showFeedback(confirmKey, serverMessages[confirmKey], "error");
      return false;
    }
    if (!show) {
      if (confirm !== initial[confirmKey]) clearFeedback(confirmKey);
      return true;
    }
    if (!confirm) {
      showFeedback(confirmKey, ["Confirm your password."], "error");
      return false;
    }
    showFeedback(confirmKey, ["Passwords do not match."], "error");
    return false;
  }

  function validateField(name, showFailures) {
    if (name === "username") return validateUsername(showFailures);
    if (name === "email") return validateEmail(showFailures);
    if (name === "old_password") return validateOldPassword(showFailures);
    if (name === "password" || name === passwordKey) return validatePassword(showFailures);
    if (name === confirmKey) return validateConfirm(showFailures);
    return true;
  }

  function validateOldPassword(showFailures) {
    var input = inputOf("old_password");
    if (!input) return true;
    if (!showFailures && !revealed.old_password) return true;
    if (serverStillApplies("old_password")) {
      showFeedback("old_password", serverMessages.old_password, "error");
      return false;
    }
    if (!input.value) {
      showFeedback("old_password", ["Enter your current password."], "error");
      return false;
    }
    clearFeedback("old_password");
    return true;
  }

  function captureServerState() {
    form.querySelectorAll(".auth-field").forEach(function (wrap) {
      var name = wrap.getAttribute("data-field");
      var input = wrap.querySelector("input");
      var feedback = wrap.querySelector(".auth-field__feedback");
      if (!name || !input || !feedback) return;
      initial[name] = input.value;
      var messages = [];
      feedback.querySelectorAll(".field-error").forEach(function (node) {
        var text = node.querySelector("span:last-child");
        messages.push((text ? text.textContent : node.textContent).trim());
      });
      if (messages.length) {
        serverMessages[name] = messages;
        revealed[name] = true;
        feedback.setAttribute("data-signature", "error:" + messages.join("\n"));
      }
    });
    applyServerRules();
  }

  function validateAll() {
    submitAttempted = true;
    var names = mode === "register"
      ? ["username", "email", passwordKey, confirmKey]
      : mode === "reset"
        ? [passwordKey, confirmKey]
        : mode === "password"
          ? ["old_password", passwordKey, confirmKey]
          : ["username", "password"];
    var ok = true;
    names.forEach(function (name) {
      var input = inputOf(name);
      if (!input) return;
      if (name === "email" || (name === "username" && mode !== "register")) {
        input.value = input.value.trim();
      }
      revealed[name] = true;
      if (!validateField(name, true)) ok = false;
    });
    return ok;
  }

  form.querySelectorAll(".auth-field input").forEach(function (input) {
    var wrap = input.closest(".auth-field");
    var name = wrap ? wrap.getAttribute("data-field") : "";
    if (!name) return;
    input.addEventListener("input", function () {
      validateField(name, false);
      if (mode === "register" && (name === "username" || name === "email")) {
        updateRules(revealed[passwordKey] || submitAttempted);
        validateConfirm(false);
      }
      if (name === passwordKey) validateConfirm(false);
    });
    input.addEventListener("blur", function () {
      if (name === "email" || (name === "username" && mode !== "register")) {
        input.value = input.value.trim();
      }
      revealed[name] = true;
      validateField(name, true);
      if (name === passwordKey) validateConfirm(revealed[confirmKey] || false);
    });
  });

  form.addEventListener("submit", function (event) {
    if (submitting) {
      event.preventDefault();
      return;
    }
    if (!validateAll()) {
      event.preventDefault();
      var first = form.querySelector(".auth-field.is-invalid input");
      if (first) first.focus();
      return;
    }
    submitting = true;
    var button = form.querySelector(".auth-submit");
    if (!button) return;
    var label = button.querySelector(".auth-submit__label");
    var loadingText = button.getAttribute("data-loading-label");
    if (label && loadingText) label.textContent = loadingText;
    button.setAttribute("aria-busy", "true");
    button.classList.add("is-loading");
    window.setTimeout(function () {
      button.disabled = true;
    }, 0);
  });

  captureServerState();
})();
