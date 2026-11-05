/* 前端运行时配置
 *
 * 部署到自己的环境后，改这里一行就能指向你的后端。
 * 优先级：URL 参数 ?api=  >  浏览器已保存的地址（「我的」页可改）  >  这里的 apiBase
 *
 * 注意：页面以 https 部署时，浏览器只允许直连 http 的 loopback 地址
 *      （localhost / 127.0.0.1）。指向别的 http 主机会被当作混合内容拦截，
 *      需要给后端套 https 隧道（cloudflared / ngrok / frp 等）。
 */
window.ZD_CONFIG = {
  apiBase: "http://127.0.0.1:8000"
};
