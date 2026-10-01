// EB1A PWA Service Worker
// 策略：HTML 网络优先（保证排期数据最新），静态资源缓存优先；离线可用。
var CACHE_PREFIX = 'gctime-' + new URL(self.registration.scope).pathname + '-';
var CACHE = CACHE_PREFIX + '__BUILD_VERSION__';
var ASSETS = [
  './', './index.html', './manifest.json', './vendor/gsap.min.js',
  './assets/ui.js', './assets/ui.css',
  './icon-192.png', './icon-512.png', './icon-maskable-512.png', './apple-touch-icon.png'
];

self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(CACHE).then(function (c) { return c.addAll(ASSETS); }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) {
        return k !== CACHE && (k.indexOf(CACHE_PREFIX) === 0 || k === 'eb1a-v4');
      }).map(function (k) { return caches.delete(k); }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (e) {
  var req = e.request;
  if (req.method !== 'GET') return;
  if (new URL(req.url).origin !== self.location.origin) return;
  var accept = req.headers.get('accept') || '';
  // 导航 / HTML：网络优先，离线回退缓存。
  // cache:'no-cache' 强制向服务器 revalidate——GitHub Pages 响应带 max-age=600，
  // 裸 fetch(req) 会命中浏览器 HTTP 缓存，新排期上线后最长 10 分钟(PWA 场景更久)
  // 仍显示旧数据。用 req.url 重新发起(navigation Request 不能直接带 init 重构)。
  var isHTML = req.mode === 'navigate' || accept.indexOf('text/html') !== -1;
  if (isHTML || req.destination === 'script' || req.destination === 'style') {
    e.respondWith(
      fetch(req.url, { cache: 'no-cache', credentials: 'same-origin' }).then(function (r) {
        if (!r.ok) throw new Error('Resource unavailable: ' + r.status);
        var copy = r.clone();
        caches.open(CACHE).then(function (c) { c.put(isHTML ? './index.html' : req, copy); });
        return r;
      }).catch(function () {
        return caches.match(req).then(function (m) { return m || (isHTML ? caches.match('./index.html') : Response.error()); });
      })
    );
    return;
  }
  // 其它（图标 / manifest）：缓存优先
  e.respondWith(caches.match(req).then(function (m) { return m || fetch(req); }));
});
