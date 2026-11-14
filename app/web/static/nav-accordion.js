/* Sidebar accordion rules. The web panel and bot sections may be open together;
   the PasarGuard section is exclusive with both of them. */
(function (root) {
  "use strict";
  const EXCLUSIVE = "pg";

  /* Sections open on page load. `available` lists the section keys in DOM order. */
  function defaultOpenKeys(activeKey, available) {
    if (activeKey === EXCLUSIVE && available.includes(EXCLUSIVE)) return [EXCLUSIVE];
    const shared = available.filter((key) => key !== EXCLUSIVE);
    return shared.length ? shared : available.slice(0, 1);
  }

  /* Open sections after the toggle of `key` was clicked. */
  function afterToggle(openKeys, key, available) {
    if (!available.includes(key)) return available.filter((k) => openKeys.includes(k));
    const open = new Set(openKeys.filter((k) => available.includes(k)));
    if (open.has(key)) {
      open.delete(key);
    } else if (key === EXCLUSIVE) {
      open.clear();
      open.add(key);
    } else {
      open.delete(EXCLUSIVE);
      open.add(key);
    }
    return available.filter((k) => open.has(k));
  }

  const api = Object.freeze({defaultOpenKeys, afterToggle});
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PGClockNavAccordion = api;
})(typeof window === "object" ? window : globalThis);
