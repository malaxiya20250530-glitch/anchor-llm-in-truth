// ═══════════════════════════════════════════
//  灵绘 PWA Service Worker
//  离线缓存 + 后台同步 + 推送通知
// ═══════════════════════════════════════════
const CACHE_NAME = 'linghui-v2';
const OFFLINE_URL = 'index.html';

// 核心资源：安装时立即缓存
const CORE_ASSETS = [
  'index.html',
  'manifest.json',
  'nezha.glb'
];

// 运行时缓存策略：网络优先，失败时回退缓存
const RUNTIME_PATTERNS = [
  /\.(mp3|wav|ogg)$/,   // 音频
  /\.(png|jpg|svg)$/,   // 图片
  /\.(js|css)$/,         // 样式脚本
  /fonts\.googleapis/,   // 字体
  /unpkg\.com/          // CDN 依赖 (model-viewer)
];

// ── 安装：缓存核心资源 ──
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      console.log('[SW] 安装中，缓存核心资源...');
      return cache.addAll(CORE_ASSETS).catch(err => {
        console.warn('[SW] 部分资源缓存失败:', err);
      });
    }).then(() => self.skipWaiting())
  );
});

// ── 激活：清理旧缓存 ──
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(key => key !== CACHE_NAME)
          .map(key => caches.delete(key))
    )).then(() => self.clients.claim())
  );
});

// ── 请求拦截：网络优先 + 缓存回退 ──
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // API / WebSocket 请求：仅走网络
  if (url.pathname.startsWith('/ws') || url.pathname.startsWith('/api')) {
    return;
  }

  // 运行时资源：网络优先，缓存回退
  const isRuntime = RUNTIME_PATTERNS.some(p => p.test(url.pathname));
  if (isRuntime) {
    event.respondWith(networkFirst(event.request));
    return;
  }

  // 其他资源：缓存优先，网络回退
  event.respondWith(cacheFirst(event.request));
});

// ── 网络优先策略 ──
async function networkFirst(request) {
  try {
    const response = await fetch(request);
    const cache = await caches.open(CACHE_NAME);
    cache.put(request, response.clone());
    return response;
  } catch {
    const cached = await caches.match(request);
    return cached || caches.match(OFFLINE_URL);
  }
}

// ── 缓存优先策略 ──
async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    const cache = await caches.open(CACHE_NAME);
    cache.put(request, response.clone());
    return response;
  } catch {
    return caches.match(OFFLINE_URL);
  }
}

// ── 推送通知 ──
self.addEventListener('push', event => {
  const data = event.data ? event.data.json() : {};
  const options = {
    body: data.body || '灵绘有一条新消息',
    icon: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y="80" font-size="80">🔥</text></svg>',
    badge: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="50" fill="%23ff4400"/></svg>',
    vibrate: [200, 100, 200],
    tag: 'linghui-msg',
    renotify: true,
    data: { url: 'index.html' }
  };
  event.waitUntil(self.registration.showNotification(data.title || '灵绘', options));
});

// ── 通知点击 ──
self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: 'window' }).then(clientList => {
      for (const client of clientList) {
        if (client.url.includes('index.html') && 'focus' in client) {
          return client.focus();
        }
      }
      return clients.openWindow('index.html');
    })
  );
});

console.log('[SW] 灵绘 Service Worker v2 已就绪');
