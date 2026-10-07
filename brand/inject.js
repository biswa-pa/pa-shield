(function () {
  var BRAND = "__PA_BRAND_NAME__";
  var LOGO = "__PA_LOGO_SRC__";
  var ICON = "__PA_ICON_SRC__";

  // Matches "NetBird" and an already-applied "PA Shield" so the brand is never
  // prefixed twice. Replacing a match with BRAND is then idempotent.
  var NAME = /(?:\bPA\s+)?netbird/gi;

  function rebrand(text) {
    return text.replace(NAME, BRAND);
  }

  function isNetbird(value) {
    return typeof value === "string" && /netbird/i.test(value);
  }

  function brandImage(img) {
    if (!img || img.dataset.paBranded === "1") return;
    var src = img.getAttribute("src") || "";
    var alt = img.getAttribute("alt") || "";
    if (!isNetbird(src) && !isNetbird(alt)) return;
    img.src = LOGO;
    img.removeAttribute("srcset");
    img.alt = BRAND;
    img.dataset.paBranded = "1";
    img.style.maxHeight = "36px";
    img.style.width = "auto";
    img.style.height = "auto";
    img.style.objectFit = "contain";
  }

  function brandTitle() {
    var t = rebrand(document.title || "");
    if (t !== document.title) document.title = t;
  }

  function brandIcons() {
    var links = document.querySelectorAll('link[rel*="icon"]');
    if (!links.length && document.head) {
      var created = document.createElement("link");
      created.rel = "icon";
      created.href = ICON;
      document.head.appendChild(created);
      return;
    }
    links.forEach(function (link) {
      if (link.getAttribute("href") !== ICON) {
        link.type = "image/png";
        link.removeAttribute("sizes");
        link.href = ICON;
      }
    });
  }

  var SKIP = { SCRIPT: 1, STYLE: 1, TEXTAREA: 1, INPUT: 1, CODE: 1, PRE: 1 };

  // Visible text only. Skips code blocks and form values so commands such as
  // "netbird up" and setup keys stay correct.
  function brandText(root) {
    if (!root) return;
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        var p = n.parentNode;
        if (!p || SKIP[p.tagName] || (p.closest && p.closest("code,pre"))) {
          return NodeFilter.FILTER_REJECT;
        }
        return rebrand(n.nodeValue) !== n.nodeValue ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      },
    });
    var nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(function (n) {
      n.nodeValue = rebrand(n.nodeValue);
    });
  }

  // The upstream dashboard adds an "Update available" link when its own version
  // is behind GitHub. This image is the dashboard, so that link is removed.
  function hideUpdateButton() {
    document.querySelectorAll("a").forEach(function (a) {
      var href = a.getAttribute("href") || "";
      var text = (a.textContent || "").replace(/\s+/g, " ").trim();
      if (href.indexOf("selfhosted/maintenance/upgrade") !== -1 || text === "Update available") {
        a.remove();
      }
    });
  }

  function scan() {
    brandTitle();
    brandIcons();
    hideUpdateButton();
    document.querySelectorAll("img").forEach(brandImage);
    brandText(document.body);
  }

  function start() {
    scan();
    var queued = false;
    var observer = new MutationObserver(function () {
      if (queued) return;
      queued = true;
      requestAnimationFrame(function () {
        queued = false;
        scan();
      });
    });
    observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
