// Adds Settings > Email Provider to the dashboard (SMTP or Microsoft Graph).
// The dashboard is a compiled app, so the tab is added from the outside:
// a trigger cloned from the Groups tab, plus a panel in the content area.
// Talks to the reset service at /reset/api/email-settings (owners and admins only).
(function () {
  var TAB = "email-provider";
  var API = "/reset/api/email-settings";
  var MAIL_ICON =
    '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>';

  var CSS =
    ".pa-ep{padding:24px 32px;max-width:672px}" +
    ".pa-ep h1{margin:0 0 4px;font-size:20px;font-weight:500;color:#fff}" +
    ".pa-ep .pa-sub{margin:0 0 24px;color:#a7b1b9;font-size:14px}" +
    ".pa-ep label{display:block;margin:16px 0 6px;font-size:14px;font-weight:500;color:#e4e7e9}" +
    ".pa-ep .pa-hint{margin:4px 0 0;font-size:12px;color:#7c8994}" +
    ".pa-ep input,.pa-ep select{width:100%;height:40px;padding:0 12px;border-radius:8px;border:1px solid #4e345e;background:#2a1636;color:#e4e7e9;font-size:14px;outline:none}" +
    ".pa-ep input:focus,.pa-ep select:focus{border-color:#fd9904}" +
    ".pa-ep .pa-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}" +
    ".pa-ep .pa-actions{display:flex;gap:12px;margin-top:28px;flex-wrap:wrap}" +
    ".pa-ep button{height:40px;padding:0 18px;border-radius:8px;border:1px solid #4e345e;background:transparent;color:#e4e7e9;font-size:14px;font-weight:500;cursor:pointer}" +
    ".pa-ep button.pa-primary{background:#fd9904;border-color:#fd9904;color:#fff}" +
    ".pa-ep button:disabled{opacity:.55;cursor:not-allowed}" +
    ".pa-ep .pa-msg{margin-top:16px;padding:10px 14px;border-radius:8px;font-size:13px;line-height:1.5}" +
    ".pa-ep .pa-ok{background:rgba(5,96,58,.25);border:1px solid #067647;color:#a6f4c5}" +
    ".pa-ep .pa-err{background:rgba(180,35,24,.2);border:1px solid #b42318;color:#fecdca}" +
    ".pa-ep .pa-help{margin-top:20px;padding:12px 14px;border-radius:8px;background:#1a0a22;border:1px solid #321b3e;color:#a7b1b9;font-size:12.5px;line-height:1.6}" +
    ".pa-ep .pa-help b{color:#e4e7e9}";

  // Reuse the access token the dashboard itself sends to the NetBird API.
  // This script loads before the app, so patching fetch here sees every call.
  var seenToken = "";

  function toast(kind, text) {
    var el = document.createElement("div");
    el.textContent = text;
    el.setAttribute("role", "status");
    el.style.cssText =
      "position:fixed;right:24px;bottom:24px;z-index:99999;max-width:360px;padding:12px 16px;border-radius:10px;font:500 14px/1.45 Inter,system-ui,sans-serif;color:#fff;box-shadow:0 10px 30px rgba(0,0,0,.4);border:1px solid " +
      (kind === "ok" ? "#067647;background:#0b3d2a" : "#b42318;background:#471215");
    document.body.appendChild(el);
    setTimeout(function () { el.remove(); }, 7000);
  }

  // Email the invite link as soon as the dashboard creates or regenerates it.
  function sendInvite(inviteId, data) {
    if (!inviteId || !data || !data.invite_token) return;
    fetch("/reset/api/send-invite", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + seenToken },
      body: JSON.stringify({ invite_id: inviteId, invite_token: data.invite_token, expires_at: data.expires_at || data.invite_expires_at }),
    })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (res.ok) toast("ok", "Invitation email sent to " + res.j.sent_to);
        else toast("err", "Invite created, but the email was not sent: " + (res.j.error || "unknown error"));
      })
      .catch(function () { toast("err", "Invite created, but the email was not sent."); });
  }

  function watchInvites(method, path, promise) {
    var create = /\/api\/users\/invites\/?$/.test(path);
    var regen = /\/api\/users\/invites\/([^/]+)\/regenerate\/?$/.exec(path);
    if (method !== "POST" || (!create && !regen)) return;
    promise.then(function (resp) {
      if (!resp || !resp.ok) return;
      resp.clone().json().then(function (data) { sendInvite(create ? data.id : regen[1], data); }).catch(function () {});
    }).catch(function () {});
  }

  (function () {
    var orig = window.fetch;
    if (!orig) return;
    window.fetch = function (input, init) {
      var url = "";
      var method = "GET";
      try {
        var h = (init && init.headers) || (input && input.headers);
        var auth = "";
        if (h && typeof h.get === "function") auth = h.get("Authorization") || "";
        else if (Array.isArray(h)) { h.forEach(function (p) { if (/^authorization$/i.test(p[0])) auth = p[1]; }); }
        else if (h) auth = h.Authorization || h.authorization || "";
        var m = /^Bearer\s+(.+)$/i.exec(auth || "");
        url = typeof input === "string" ? input : (input && input.url) || "";
        method = String((init && init.method) || (input && input.method) || "GET").toUpperCase();
        if (m && url.indexOf("/reset/api/") === -1) seenToken = m[1];
      } catch (e) {}
      var promise = orig.apply(this, arguments);
      try { watchInvites(method, url.split("?")[0], promise); } catch (e) {}
      return promise;
    };
  })();

  var panel = null;
  var loaded = false;
  var state = null;

  // The dashboard's OIDC library keeps the session in sessionStorage as
  // oidc.<name> = {"tokens":{"accessToken":...}}. Older layouts used oidc.user:...
  function token() {
    if (seenToken) return seenToken;
    var stores = [window.sessionStorage, window.localStorage];
    for (var s = 0; s < stores.length; s++) {
      try {
        for (var i = 0; i < stores[s].length; i++) {
          var key = stores[s].key(i);
          if (!key || key.indexOf("oidc.") !== 0 || /\.(userInfo|nonce|state|jwk|tabId|code_verifier|login|dpop_nonce)\b/.test(key)) continue;
          var data = JSON.parse(stores[s].getItem(key));
          var t = (data && data.tokens && (data.tokens.accessToken || data.tokens.access_token)) || (data && data.access_token);
          if (t) return t;
        }
      } catch (e) {}
    }
    return "";
  }

  function call(method, path, body) {
        var headers = { "Content-Type": "application/json" };
    var t = token();
    if (t) headers.Authorization = "Bearer " + t;
    return fetch(API + (path || ""), {
      method: method,
      credentials: "include",
      headers: headers,
      body: body ? JSON.stringify(body) : undefined,
    }).then(function (r) {
      return r.json().then(function (j) {
        if (!r.ok) throw new Error(j.error || "Request failed (" + r.status + ")");
        return j;
      });
    });
  }

  function field(id, label, type, hint) {
    return (
      '<label for="pa-' + id + '">' + label + "</label>" +
      '<input id="pa-' + id + '" type="' + (type || "text") + '" autocomplete="off">' +
      (hint ? '<p class="pa-hint">' + hint + "</p>" : "")
    );
  }

  function build() {
    var el = document.createElement("div");
    el.className = "pa-ep";
    el.setAttribute("data-pa-email-panel", "1");
    el.style.display = "none";
    el.innerHTML =
      "<h1>Email Provider</h1>" +
      '<p class="pa-sub">Choose how this server sends email, such as password reset links.</p>' +
      '<label for="pa-provider">Provider</label>' +
      '<select id="pa-provider"><option value="none">Not configured</option>' +
      '<option value="graph">Microsoft Graph</option><option value="smtp">SMTP</option></select>' +
      '<div data-pa-section="graph" style="display:none">' +
      field("g-tenant", "Directory (tenant) ID", "text") +
      field("g-client", "Application (client) ID", "text") +
      field("g-secret", "Client secret", "password", "Stored on the server. Leave blank to keep the saved secret.") +
      field("g-sender", "Sender mailbox", "email", "The mailbox the email is sent from, for example noreply@yourcompany.com.") +
      '<div class="pa-help"><b>Microsoft Entra setup:</b> register an app, add the <b>Mail.Send</b> application permission under Microsoft Graph, ' +
      "grant admin consent, then create a client secret. The sender mailbox must exist in your tenant.</div></div>" +
      '<div data-pa-section="smtp" style="display:none">' +
      '<div class="pa-row"><div>' + field("s-host", "SMTP host") + "</div><div>" + field("s-port", "Port", "number") + "</div></div>" +
      '<label for="pa-s-security">Security</label><select id="pa-s-security"><option value="starttls">STARTTLS (587)</option><option value="ssl">SSL/TLS (465)</option><option value="none">None</option></select>' +
      field("s-user", "Username") +
      field("s-pass", "Password", "password", "Stored on the server. Leave blank to keep the saved password.") +
      field("s-from", "From address", "email") + "</div>" +
      '<div class="pa-actions"><button class="pa-primary" data-pa="save">Save changes</button>' +
      '<button data-pa="test">Send test email</button></div><div data-pa="msg"></div>';
    el.querySelector("#pa-provider").addEventListener("change", sections);
    el.addEventListener("click", function (e) {
      var act = e.target && e.target.getAttribute && e.target.getAttribute("data-pa");
      if (act === "save") save();
      if (act === "test") test();
    });
    return el;
  }

  function $(id) {
    return panel.querySelector("#pa-" + id);
  }

  function sections() {
    var p = $("provider").value;
    panel.querySelector('[data-pa-section="graph"]').style.display = p === "graph" ? "block" : "none";
    panel.querySelector('[data-pa-section="smtp"]').style.display = p === "smtp" ? "block" : "none";
  }

  function message(kind, text) {
    var box = panel.querySelector('[data-pa="msg"]');
    box.innerHTML = text ? '<div class="pa-msg ' + (kind === "ok" ? "pa-ok" : "pa-err") + '"></div>' : "";
    if (text) box.firstChild.textContent = text;
  }

  function fill(s) {
    state = s;
    $("provider").value = s.provider;
    $("g-tenant").value = s.graph.tenant_id || "";
    $("g-client").value = s.graph.client_id || "";
    $("g-sender").value = s.graph.sender || "";
    $("g-secret").value = "";
    $("g-secret").placeholder = s.graph.client_secret_set ? "Saved" : "";
    $("s-host").value = s.smtp.host || "";
    $("s-port").value = s.smtp.port || 587;
    $("s-security").value = s.smtp.security || "starttls";
    $("s-user").value = s.smtp.user || "";
    $("s-from").value = s.smtp.from || "";
    $("s-pass").value = "";
    $("s-pass").placeholder = s.smtp.password_set ? "Saved" : "";
    sections();
  }

  function collect() {
    return {
      provider: $("provider").value,
      graph: {
        tenant_id: $("g-tenant").value, client_id: $("g-client").value,
        client_secret: $("g-secret").value, sender: $("g-sender").value,
      },
      smtp: {
        host: $("s-host").value, port: $("s-port").value, security: $("s-security").value,
        user: $("s-user").value, password: $("s-pass").value, from: $("s-from").value,
      },
    };
  }

  function busy(on) {
    panel.querySelectorAll("button").forEach(function (b) { b.disabled = on; });
  }

  function save() {
    busy(true);
    message("", "");
    call("PUT", "", collect())
      .then(function (s) { fill(s); message("ok", "Email provider saved."); })
      .catch(function (e) { message("err", e.message); })
      .then(function () { busy(false); });
  }

  function test() {
    busy(true);
    message("", "");
    call("POST", "/test", collect())
      .then(function (r) { message("ok", "Test email sent to " + r.sent_to + "."); })
      .catch(function (e) { message("err", e.message); })
      .then(function () { busy(false); });
  }

  function load(tries) {
    tries = tries || 0;
    if (!token() && tries < 20) {
      // The dashboard makes API calls as the page loads; wait for the first one.
      return setTimeout(function () { load(tries + 1); }, 250);
    }
    call("GET")
      .then(fill)
      .catch(function (e) { message("err", e.message); });
  }

  function onTab() {
    return location.pathname.replace(/\/$/, "") === "/settings" &&
      new URLSearchParams(location.search).get("tab") === TAB;
  }

  function trigger(value) {
    return document.querySelector('[data-settings-tab="' + value + '"]');
  }

  function go() {
    history.pushState(null, "", "/settings?tab=" + TAB);
  }

  // Sits after Identity Providers, or Setup Keys when that one is hidden.
  function anchor() {
    return trigger("identity-providers") || trigger("setup-keys") || trigger("authentication");
  }

  function ensureTrigger() {
    var btn = document.querySelector("[data-pa-email-tab]");
    var after = anchor();
    if (!after) return btn;
    if (!btn) {
      var groups = trigger("groups");
      if (!groups) return null;
      btn = groups.cloneNode(true);
      ["data-testid", "id", "aria-controls", "data-settings-tab"].forEach(function (a) { btn.removeAttribute(a); });
      btn.setAttribute("data-pa-email-tab", "1");
      // The label row is an inner div; keep it and swap only its contents.
      var row = btn.firstElementChild || btn;
      row.innerHTML = MAIL_ICON + "Email Provider";
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        go();
        sync();
      });
    }
    if (after.nextElementSibling !== btn) after.insertAdjacentElement("afterend", btn);
    return btn;
  }

  function setActive(btn, active) {
    btn.setAttribute("data-state", active ? "active" : "inactive");
    btn.setAttribute("aria-selected", active ? "true" : "false");
    btn.classList.toggle("bg-nb-gray-920", active);
    btn.classList.toggle("text-nb-gray-500", !active);
    btn.classList.toggle("hover:bg-nb-gray-900/50", !active);
  }

  function sync() {
    var inSettings = location.pathname.replace(/\/$/, "") === "/settings";
    if (!inSettings) return;
    var btn = ensureTrigger();
    var host = document.querySelector("div.border-l.w-full");
    if (!btn || !host) return;
    if (!document.getElementById("pa-ep-style")) {
      var st = document.createElement("style");
      st.id = "pa-ep-style";
      st.textContent = CSS;
      document.head.appendChild(st);
    }
    if (!panel || !panel.isConnected) {
      panel = build();
      host.appendChild(panel);
      loaded = false;
    }
    var active = onTab();
    panel.style.display = active ? "block" : "none";
    setActive(btn, active);
    if (active && !loaded) { loaded = true; load(); }
  }

  var queued = false;
  function schedule() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(function () { queued = false; sync(); });
  }

  function start() {
    sync();
    new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true });
    window.addEventListener("popstate", schedule);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
