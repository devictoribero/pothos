/* devflow explain: sidebar navigation. Loaded by every page as ../nav.js, which artifact.py regenerates
   with window.DEVFLOW_NAV (all pages of this repository, with parents) followed by this runtime. */
(function () {
  var pages = window.DEVFLOW_NAV || [];
  var es = (document.documentElement.lang || '').slice(0, 2) === 'es';
  var t = es ? { all: 'Explicaciones', here: 'En esta página', diagrams: 'Diagramas', menu: 'Índice', close: 'Cerrar índice' }
             : { all: 'Explanations', here: 'On this page', diagrams: 'Diagrams', menu: 'Contents', close: 'Close contents' };
  var parts = location.pathname.split('/');
  var current = decodeURIComponent(parts[parts.length - 2] || '');

  var css = document.createElement('style');
  css.textContent = [
    '.df-nav{position:fixed;top:0;left:0;bottom:0;width:272px;overflow-y:auto;background:var(--surface);border-right:1px solid var(--line);padding:20px 14px 40px;font:14px/1.45 var(--sans);z-index:20}',
    '.df-nav h2{font:600 .72rem/1.2 var(--mono);letter-spacing:.07em;text-transform:uppercase;color:var(--muted);margin:0 0 10px 6px}',
    '.df-nav ul{list-style:none;margin:0;padding:0}',
    '.df-nav ul ul{margin:2px 0 4px 12px;padding-left:8px;border-left:1px solid var(--line)}',
    '.df-nav li{margin:0}',
    '.df-nav a{display:block;padding:5px 8px;border-radius:6px;color:var(--fg);text-decoration:none}',
    '.df-nav a:hover{background:var(--soft)}',
    '.df-nav a:focus-visible{outline:2px solid var(--accent);outline-offset:1px}',
    '.df-nav a.df-current{background:var(--accent-soft);color:var(--accent);font-weight:600}',
    '.df-nav .df-date{display:block;font:500 .7rem var(--mono);color:var(--muted)}',
    '.df-nav .df-label{font:600 .68rem/1.2 var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--muted);padding:8px 8px 2px}',
    '.df-nav a.df-section{font-size:13px;color:var(--muted)}',
    '.df-nav a.df-section.df-active{color:var(--accent)}',
    '.df-menu{display:none;position:fixed;top:12px;left:12px;z-index:21;font:600 .8rem var(--sans);color:var(--fg);background:var(--surface);border:1px solid var(--line);border-radius:999px;padding:6px 12px;cursor:pointer}',
    '@media (min-width:1000px){body{padding-left:272px}}',
    '@media (max-width:999px){.df-nav{transform:translateX(-100%);transition:transform .2s;box-shadow:0 0 0 100vmax rgba(0,0,0,0)}.df-nav.df-open{transform:none;box-shadow:0 0 0 100vmax rgba(0,0,0,.35)}.df-menu{display:block}.wrap{padding-top:56px}}',
    '@media (prefers-reduced-motion:reduce){.df-nav{transition:none}}',
    /* layout safety for every page, including ones written before these rules existed */
    'html,body{overflow-x:hidden}.wrap>*{min-width:0;max-width:100%}code{overflow-wrap:anywhere}pre,.table,.diagram,table{max-width:100%}img,svg,video{max-width:100%;height:auto}'
  ].join('\n');
  document.head.appendChild(css);

  function slug(text) { return text.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'section'; }
  function el(tag, attrs, text) { var n = document.createElement(tag); for (var k in attrs) n.setAttribute(k, attrs[k]); if (text) n.textContent = text; return n; }

  function sectionsOfThisPage() {
    var list = el('ul', {}), used = {};
    var headings = document.querySelectorAll('.wrap h2');
    headings.forEach(function (h) {
      if (!h.id) { var id = slug(h.textContent), n = 2, base = id; while (used[id] || document.getElementById(id)) id = base + '-' + n++; h.id = id; }
      used[h.id] = true;
      var li = el('li', {}); li.appendChild(el('a', { href: '#' + h.id, 'class': 'df-section' }, h.textContent)); list.appendChild(li);
    });
    var frames = document.querySelectorAll('iframe[data-archify]');
    if (frames.length) {
      list.appendChild(el('li', { 'class': 'df-label' }, t.diagrams));
      frames.forEach(function (f) {
        var li = el('li', {}); li.appendChild(el('a', { href: f.getAttribute('src').split('?')[0], target: '_blank', 'class': 'df-section' }, f.getAttribute('title') || f.getAttribute('src'))); list.appendChild(li);
      });
    }
    return headings.length || frames.length ? list : null;
  }

  function branch(parent) {
    var children = pages.filter(function (p) { return (p.parent || null) === parent; });
    if (!children.length) return null;
    var list = el('ul', {});
    children.forEach(function (p) {
      var li = el('li', {});
      var link = el('a', { href: '../' + encodeURIComponent(p.folder) + '/index.html' }, p.title);
      link.appendChild(el('span', { 'class': 'df-date' }, p.created));
      if (p.folder === current) { link.className = 'df-current'; link.setAttribute('aria-current', 'page'); }
      li.appendChild(link);
      if (p.folder === current) { var here = sectionsOfThisPage(); if (here) li.appendChild(here); }
      var sub = branch(p.folder); if (sub) li.appendChild(sub);
      list.appendChild(li);
    });
    return list;
  }

  var known = {}; pages.forEach(function (p) { known[p.folder] = true; });
  pages.forEach(function (p) { if (p.parent && !known[p.parent]) p.parent = null; });

  var nav = el('nav', { 'class': 'df-nav', 'aria-label': t.all, id: 'df-nav' });
  nav.appendChild(el('h2', {}, t.all));
  var tree = branch(null); if (tree) nav.appendChild(tree);
  var menu = el('button', { 'class': 'df-menu', type: 'button', 'aria-controls': 'df-nav', 'aria-expanded': 'false' }, t.menu);
  menu.addEventListener('click', function () {
    var open = nav.classList.toggle('df-open');
    menu.setAttribute('aria-expanded', open ? 'true' : 'false'); menu.textContent = open ? t.close : t.menu;
  });
  nav.addEventListener('click', function (e) { if (e.target.closest('a') && nav.classList.contains('df-open')) menu.click(); });
  document.body.insertBefore(nav, document.body.firstChild);
  document.body.insertBefore(menu, nav);

  if ('IntersectionObserver' in window) {
    var links = nav.querySelectorAll('a.df-section[href^="#"]');
    var byId = {}; links.forEach(function (a) { byId[a.getAttribute('href').slice(1)] = a; });
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) { links.forEach(function (a) { a.classList.remove('df-active'); }); var a = byId[entry.target.id]; if (a) a.classList.add('df-active'); }
      });
    }, { rootMargin: '0px 0px -70% 0px' });
    document.querySelectorAll('.wrap h2[id]').forEach(function (h) { observer.observe(h); });
  }
})();
