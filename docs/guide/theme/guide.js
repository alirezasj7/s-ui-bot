(function () {
  'use strict';

  var shell = document.getElementById('guide-shell') || document.body;
  var toggle = document.getElementById('guide-menu-toggle');
  var closeBtn = document.getElementById('guide-side-close');
  var scrim = document.getElementById('guide-scrim');
  var sidebar = document.getElementById('guide-sidebar');

  function setNav(open) {
    open = !!open;
    shell.classList.toggle('nav-open', open);
    if (scrim) {
      if (open) scrim.removeAttribute('hidden');
      else scrim.setAttribute('hidden', '');
    }
    if (toggle) toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    document.documentElement.style.overflow = open ? 'hidden' : '';
    document.body.style.overflow = open ? 'hidden' : '';
  }

  if (toggle) {
    toggle.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      setNav(!shell.classList.contains('nav-open'));
    });
  }
  if (closeBtn) {
    closeBtn.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      setNav(false);
    });
  }
  if (scrim) {
    scrim.addEventListener('click', function (e) {
      e.preventDefault();
      setNav(false);
    });
  }
  /* Clicks inside the drawer must not fall through to the scrim/main layer */
  if (sidebar) {
    sidebar.addEventListener('click', function (e) {
      e.stopPropagation();
    });
  }
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') setNav(false);
  });
  window.addEventListener('resize', function () {
    if (window.matchMedia('(min-width: 961px)').matches) setNav(false);
  });

  document.querySelectorAll('[data-panel-path]').forEach(function (el) {
    var path = el.getAttribute('data-panel-path') || '';
    if (!path) return;
    if (location.pathname.indexOf('/help') === 0 || location.pathname.indexOf('/static/guide') === 0) {
      el.setAttribute('href', path);
    } else {
      el.setAttribute('title', 'این مسیر را در وب‌پنل خودتان باز کنید');
      el.addEventListener('click', function (e) {
        e.preventDefault();
        try {
          navigator.clipboard.writeText(path);
          var old = el.textContent;
          el.textContent = 'کپی شد: ' + path;
          setTimeout(function () { el.textContent = old; }, 1600);
        } catch (err) {
          window.prompt('مسیر صفحه در وب‌پنل:', path);
        }
      });
    }
  });

  /* Resolve asset root from guide.js so search links work from nested pages */
  var guideRoot = '';
  (function () {
    var base = document.querySelector('script[src*="guide.js"]');
    if (base && base.getAttribute('src')) {
      guideRoot = base.getAttribute('src').replace(/guide\.js.*$/, '');
    }
  })();

  function resolveGuideHref(href) {
    href = String(href || '');
    if (!href) return guideRoot || './';
    if (/^(https?:|mailto:|tel:|#|\/)/i.test(href)) return href;
    return guideRoot + href.replace(/^\.\//, '');
  }

  /* Wrap bare tables like panel `.table-wrap` — whole table scrolls together */
  document.querySelectorAll('.guide-content table').forEach(function (table) {
    var parent = table.parentElement;
    if (
      parent &&
      (parent.classList.contains('guide-table-wrap') ||
        parent.classList.contains('guide-table-scroll'))
    ) {
      parent.classList.add('guide-table-wrap');
      parent.classList.remove('guide-table-scroll');
      return;
    }
    var wrap = document.createElement('div');
    wrap.className = 'guide-table-wrap';
    wrap.setAttribute('role', 'region');
    wrap.setAttribute('aria-label', 'جدول');
    wrap.tabIndex = 0;
    table.parentNode.insertBefore(wrap, table);
    wrap.appendChild(table);
  });

  var input = document.getElementById('guide-search-input');
  var panel = document.getElementById('guide-search-panel');
  if (!input || !panel) return;

  var indexPromise = null;
  function loadIndex() {
    if (!indexPromise) {
      indexPromise = fetch(guideRoot + 'search-index.json', { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .catch(function () { return []; });
    }
    return indexPromise;
  }

  function normalize(s) {
    return String(s || '')
      .toLowerCase()
      .replace(/ي/g, 'ی')
      .replace(/ك/g, 'ک')
      .replace(/[\u064B-\u065F]/g, '')
      .trim();
  }

  function scoreItem(q, item) {
    var nq = normalize(q);
    if (!nq) return 0;
    var title = normalize(item.title);
    var summary = normalize(item.summary);
    var body = normalize(item.body);
    var aliases = normalize((item.aliases || []).join(' '));
    var s = 0;
    if (title === nq) s += 100;
    if (title.indexOf(nq) === 0) s += 80;
    if (title.indexOf(nq) >= 0) s += 50;
    if (aliases.indexOf(nq) >= 0) s += 45;
    if (summary.indexOf(nq) >= 0) s += 25;
    nq.split(/\s+/).forEach(function (part) {
      if (part.length < 2) return;
      if (title.indexOf(part) >= 0) s += 12;
      if (aliases.indexOf(part) >= 0) s += 10;
      if (summary.indexOf(part) >= 0) s += 6;
      if (body.indexOf(part) >= 0) s += 3;
    });
    return s;
  }

  var active = -1;
  function render(hits) {
    panel.innerHTML = '';
    if (!hits.length) {
      panel.innerHTML = '<div class="guide-search-empty">نتیجه‌ای پیدا نشد. کلمه ساده‌تری مثل «رسید» یا «پلن» را امتحان کنید.</div>';
      panel.classList.add('is-open');
      return;
    }
    hits.slice(0, 8).forEach(function (h, i) {
      var a = document.createElement('a');
      a.className = 'guide-search-hit' + (i === active ? ' is-active' : '');
      a.href = resolveGuideHref(h.href);
      a.setAttribute('role', 'option');
      a.innerHTML = '<strong></strong><span></span>';
      a.querySelector('strong').textContent = h.title;
      a.querySelector('span').textContent = h.summary || '';
      panel.appendChild(a);
    });
    panel.classList.add('is-open');
  }

  function runSearch() {
    var q = input.value.trim();
    active = -1;
    if (!q) {
      panel.classList.remove('is-open');
      panel.innerHTML = '';
      return;
    }
    loadIndex().then(function (items) {
      var ranked = items
        .map(function (it) { return { it: it, s: scoreItem(q, it) }; })
        .filter(function (x) { return x.s > 0; })
        .sort(function (a, b) { return b.s - a.s; })
        .map(function (x) { return x.it; });
      render(ranked);
    });
  }

  var timer = null;
  input.addEventListener('input', function () {
    clearTimeout(timer);
    timer = setTimeout(runSearch, 120);
  });
  input.addEventListener('keydown', function (e) {
    var hits = panel.querySelectorAll('.guide-search-hit');
    if (e.key === 'Escape') {
      panel.classList.remove('is-open');
      input.blur();
      return;
    }
    if (!hits.length) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      active = Math.min(hits.length - 1, active + 1);
      hits.forEach(function (h, i) { h.classList.toggle('is-active', i === active); });
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      active = Math.max(0, active - 1);
      hits.forEach(function (h, i) { h.classList.toggle('is-active', i === active); });
    } else if (e.key === 'Enter' && active >= 0 && hits[active]) {
      e.preventDefault();
      location.href = hits[active].href;
    }
  });
  document.addEventListener('click', function (e) {
    if (!e.target.closest('.guide-search')) panel.classList.remove('is-open');
  });
})();
