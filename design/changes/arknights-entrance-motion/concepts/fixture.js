/* 概念预览夹具（只用于关键帧渲染，不进产品）
   目的：把 /api/* 换成固定数据，让关键帧显示真实渲染的真实页面（同一份 static/index.html），
   而不是画一张 mood board。产品代码一行不改。 */
(function () {
  const STATUS = {
    capture_running: true,
    proxy: { enabled: true, server: '127.0.0.1:8899' },
    cert: { installed: true, exists: true },
    ffmpeg_ok: true,
    counts: { total: 8, done: 4, error: 1 },
    active_downloads: 1,
    settings: { out_dir: 'D:\\wxc-downloads', concurrency: 2 }
  };
  const mk = (id, kind, title, state, extra) => Object.assign({
    id, kind, title, url: 'https://vod.example.edu/' + id + '/' + (kind === 'hls' ? 'index.m3u8' : 'v.mp4'),
    host: kind === 'hls' ? 'vod-cdn-a.example.edu' : 'vod.example.edu',
    size: 0, state, progress: null, duration: 0, out_time: 0, bytes: 0, total: 0,
    quality: '', file_exists: false, file_name: title + '.mp4', ignored: false, error: '', related_id: null
  }, extra || {});
  const ITEMS = [
    mk(1, 'hls', '第 03 讲 · 有限元法基础（上）', 'running',
       { progress: 0.42, duration: 4532, out_time: 1904, bytes: 322122547, total: 766958446, quality: '1280x720' }),
    mk(2, 'hls', '第 03 讲 · 有限元法基础（下）', 'running',
       { progress: 0.08, duration: 4210, out_time: 337, bytes: 58720256, total: 734003200, quality: '1280x720' }),
    mk(3, 'mp4', '第 02 讲 · 变分原理与弱形式', 'done',
       { size: 612368384, duration: 3908, file_exists: true, quality: '1280x720' }),
    mk(4, 'mp4', '第 01 讲 · 课程导论', 'done',
       { size: 480247808, duration: 3312, file_exists: true, quality: '1280x720' }),
    mk(5, 'hls', '第 04 讲 · 单元刚度矩阵', 'error',
       { progress: 0.31, duration: 4021, out_time: 1246, bytes: 209715200, total: 671088640, quality: '1280x720',
         error: '链接带时效签名已失效：回微信重新播放该课时，刷新后重下。' }),
    mk(6, 'ts', '第 03 讲 · 有限元法基础（上）', 'idle', { quality: '1280x720', related_id: 1, size: 1048576 }),
    mk(7, 'hls', '第 05 讲 · 装配与边界条件', 'queued', { quality: '960x540', size: 0 }),
    mk(8, 'dash', '第 06 讲 · 后处理与误差估计', 'idle', { quality: '1280x720' })
  ];
  const json = (o) => Promise.resolve(new Response(JSON.stringify(o), {
    status: 200, headers: { 'Content-Type': 'application/json' }
  }));
  window.fetch = function (url) {
    const u = String(url && url.url ? url.url : url);
    if (u.indexOf('/api/status') >= 0) return json(STATUS);
    if (u.indexOf('/api/items') >= 0) return json({ items: ITEMS });
    return json({ ok: true });
  };
})();
