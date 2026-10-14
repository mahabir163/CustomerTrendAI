// Small UI behaviours shared by every page: mobile sidebar and toast dismissal.
(function () {
  "use strict";

  var sidebar = document.getElementById("sidebar");
  var backdrop = document.getElementById("sidebar-backdrop");
  var toggle = document.getElementById("sidebar-toggle");

  function setSidebar(open) {
    if (!sidebar) return;
    sidebar.classList.toggle("-translate-x-full", !open);
    if (backdrop) backdrop.classList.toggle("hidden", !open);
    if (toggle) toggle.setAttribute("aria-expanded", String(open));
  }

  if (toggle) toggle.addEventListener("click", function () {
    setSidebar(sidebar.classList.contains("-translate-x-full"));
  });
  if (backdrop) backdrop.addEventListener("click", function () { setSidebar(false); });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") setSidebar(false);
  });

  // Toasts: close button, and auto-dismiss after 6 seconds.
  document.querySelectorAll("[data-toast]").forEach(function (toast) {
    var close = toast.querySelector("[data-toast-close]");
    if (close) close.addEventListener("click", function () { toast.remove(); });
    setTimeout(function () { toast.remove(); }, 6000);
  });
})();
