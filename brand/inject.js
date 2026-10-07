(function () {
  var BRAND = "__PA_BRAND_NAME__";
  var LOGO = "__PA_LOGO_SRC__";

  function isNetbird(value) {
    return typeof value === "string" && /netbird/i.test(value);
  }

  function brandImage(img) {
    if (!img || img.dataset.paBranded === "1") return;
    var src = img.getAttribute("src") || "";
    var alt = img.getAttribute("alt") || "";
    if (!isNetbird(src) && !isNetbird(alt)) return;
    img.src = LOGO;
    img.alt = BRAND;
    img.dataset.paBranded = "1";
    img.style.maxHeight = "40px";
    img.style.width = "auto";
    img.style.height = "auto";
    img.style.background = "#fff";
    img.style.borderRadius = "8px";
    img.style.padding = "2px 8px";
    img.style.objectFit = "contain";
  }

  function brandTitle() {
    if (document.title && /netbird/i.test(document.title)) {
      document.title = document.title.replace(/netbird/gi, BRAND);
    }
  }

  function brandIcons() {
    var links = document.querySelectorAll('link[rel*="icon"]');
    if (!links.length && document.head) {
      var created = document.createElement("link");
      created.rel = "icon";
      created.href = LOGO;
      document.head.appendChild(created);
      return;
    }
    links.forEach(function (link) {
      var href = link.getAttribute("href") || "";
      if (isNetbird(href) || /favicon|apple-icon/i.test(href)) {
        link.href = LOGO;
      }
    });
  }

  function scan(root) {
    brandTitle();
    brandIcons();
    var scope = root && root.querySelectorAll ? root : document;
    if (scope.tagName === "IMG") brandImage(scope);
    scope.querySelectorAll("img").forEach(brandImage);
  }

  function start() {
    scan(document);
    var observer = new MutationObserver(function (records) {
      records.forEach(function (record) {
        record.addedNodes.forEach(function (node) {
          if (!node || node.nodeType !== 1) return;
          if (node.tagName === "IMG") brandImage(node);
          else if (node.querySelectorAll) scan(node);
        });
      });
      brandTitle();
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
