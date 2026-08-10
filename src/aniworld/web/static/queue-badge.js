/* The queue count in the navbar.
 *
 * Runs on every page, so it asks for the counts alone rather than the queue
 * itself. Pulling the whole list here is what used to make every page heavy
 * once someone had a few hundred finished downloads sitting around.
 */

(function () {
  const badge = document.getElementById("queueBadge");
  const INTERVAL = 10000;

  async function refreshBadge() {
    if (document.hidden) return;
    let counts;
    try {
      counts = (await apiFetch("/api/queue/counts", { timeoutMs: 8000 })).counts || {};
    } catch (error) {
      return; // a stale badge is not worth interrupting anyone over
    }

    const active = counts.active || 0;
    // themes hang off these, so they are set even when the badge is missing
    document.body.dataset.queue = active ? "active" : "idle";
    document.body.dataset.queueCount = String(active);
    if (!badge) return;
    badge.textContent = String(active);
    badge.hidden = active === 0;
  }

  // The queue page replaces this with its own refresh, which repaints the list
  // as well. Anything that queues a download calls it without caring which.
  window.refreshQueue = refreshBadge;

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refreshBadge();
  });

  refreshBadge();
  setInterval(refreshBadge, INTERVAL);
})();
