/* Tab-scoped recovery. Restoring never resends a message or payment. */
window.createTripStorage = () => {
  const key = "odin.trip.v1", ttl = 60 * 60 * 1000;
  return {
    read() {
      try {
        const item = JSON.parse(sessionStorage.getItem(key) || "null");
        if (!item || item.version !== 1 || !item.session_id || Date.now() - item.savedAt > ttl) {
          sessionStorage.removeItem(key); return null;
        }
        return item;
      } catch (_) { return null; }
    },
    write(item) {
      try {
        sessionStorage.setItem(key, JSON.stringify({...item, version:1, savedAt:Date.now(), messages:item.messages.slice(-60)}));
        return true;
      } catch (_) { return false; }
    },
    clear() { try { sessionStorage.removeItem(key); } catch (_) {} }
  };
};
