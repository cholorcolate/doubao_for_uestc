(function(){
  "use strict";

  /* ===== 通用工具 ===== */

  /* 后端地址优先级：?api=<地址> > localStorage（「我的」页可改） > config.js > 兜底。
     GitHub Pages 是 https 站点、本地后端是 http，浏览器豁免 loopback
     （localhost / 127.0.0.1）的混合内容限制，故可直接直连；
     非 loopback 的 http 后端会被浏览器拦截，需自行配置 https 隧道。 */
  var DEFAULT_API_BASE = (window.ZD_CONFIG && window.ZD_CONFIG.apiBase) ||
    "http://127.0.0.1:8000";
  var API_BASE = (function(){
    var fallback = DEFAULT_API_BASE;
    var saved = "";
    try {
      var m = /[?&]api=([^&#]+)/.exec(location.search);
      if (m) {
        saved = decodeURIComponent(m[1]);
        localStorage.setItem("zd_api_base", saved);
      } else {
        saved = localStorage.getItem("zd_api_base") || "";
      }
    } catch(e){ saved = ""; }
    return (saved || fallback).replace(/\/+$/, "");
  })();

  function apiUrl(path){
    return API_BASE + path;
  }

  function $(id){ return document.getElementById(id); }
  function esc(s){
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* ===== 收藏 / 订阅（localStorage，无需登录） ===== */
  var FAV_KEY = "zd_favorites";
  var SUB_KEY = "zd_subscriptions";

  function loadFavs(){
    try { return JSON.parse(localStorage.getItem(FAV_KEY)) || []; }
    catch(e){ return []; }
  }
  function saveFavs(list){ localStorage.setItem(FAV_KEY, JSON.stringify(list)); }
  function loadSubs(){
    try { return JSON.parse(localStorage.getItem(SUB_KEY)) || []; }
    catch(e){ return []; }
  }
  function saveSubs(list){ localStorage.setItem(SUB_KEY, JSON.stringify(list)); }
  function favId(item){ return (item.url || "") + "|" + (item.title || ""); }
  function isFaved(item){
    var id = favId(item);
    return loadFavs().some(function(f){ return favId(f) === id; });
  }
  function toggleFav(item){
    var list = loadFavs(), id = favId(item), idx = -1;
    list.forEach(function(f, i){ if (favId(f) === id) idx = i; });
    if (idx >= 0){ list.splice(idx, 1); saveFavs(list); return false; }
    list.unshift({
      title: item.title, url: item.url,
      board: item.board || "", time: item.time || "", ts: Date.now()
    });
    saveFavs(list);
    return true;
  }
  function favBtnHtml(it, mini){
    var on = isFaved(it);
    return '<button class="fav-btn' + (on ? " on" : "") + (mini ? " mini" : "") +
      '" title="' + (on ? "取消收藏" : "收藏") + '" aria-label="' + (on ? "取消收藏" : "收藏") + '" aria-pressed="' + on + '"' +
      ' data-title="' + esc(it.title) + '" data-url="' + esc(it.url) + '"' +
      ' data-board="' + esc(it.board || "") + '" data-time="' + esc(it.time || "") + '">' +
      (on ? "★" : "☆") + "</button>";
  }

  // 收藏按钮全局委托：信息流/工具/订阅/问答来源/我的 共用
  document.addEventListener("click", function(e){
    var btn = e.target.closest(".fav-btn");
    if (!btn) return;
    var item = {
      title: btn.dataset.title, url: btn.dataset.url,
      board: btn.dataset.board, time: btn.dataset.time
    };
    var now = toggleFav(item);
    // 同一条目的所有星标按钮同步状态
    document.querySelectorAll(".fav-btn").forEach(function(b){
      if (b.dataset.title === item.title && b.dataset.url === item.url){
        b.classList.toggle("on", now);
        b.textContent = now ? "★" : "☆";
        b.title = now ? "取消收藏" : "收藏";
        b.setAttribute("aria-label", b.title);
        b.setAttribute("aria-pressed", String(now));
      }
    });
    if (currentView === "mine" && mineTab === "fav") renderFavs();
  });

  /* ===== 视图切换 ===== */
  var currentView = "chat";
  var mineTab = "fav";
  var feedLoaded = false;
  var toolsLoaded = false;

  function switchView(name){
    currentView = name;
    document.body.dataset.view = name;
    document.querySelectorAll(".nav-btn").forEach(function(b){
      b.classList.toggle("active", b.dataset.view === name);
      if (b.dataset.view === name) b.setAttribute("aria-current", "page");
      else b.removeAttribute("aria-current");
    });
    document.querySelectorAll(".view").forEach(function(v){
      v.classList.toggle("active", v.id === "view-" + name);
    });
    if (name === "feed" && !feedLoaded) loadFeedTabs();
    if (name === "tools" && !toolsLoaded) loadTools();
    if (name === "mine") renderMine();
  }
  $("nav").addEventListener("click", function(e){
    var b = e.target.closest(".nav-btn");
    if (b) switchView(b.dataset.view);
  });

  /* ===== 信息聚合 ===== */
  var feedState = { category: "", page: 1, size: 15, total: 0 };
  var feedRequest = 0;

  function feedItemHtml(it){
    return '<div class="feed-item"><div class="fi-main">' +
      '<a class="fi-title" href="' + esc(it.url) + '" target="_blank" rel="noopener">' +
      esc(it.title) + "</a>" +
      '<div class="fi-meta">' + esc(it.board || it.site || "") + " · " + esc(it.time) + "</div>" +
      '<div class="fi-snippet">' + esc(it.snippet) + "</div></div>" +
      favBtnHtml(it) + "</div>";
  }

  function loadFeedTabs(){
    feedLoaded = true;
    fetch(apiUrl("/api/feed/categories")).then(function(r){
      if (!r.ok) throw new Error("bad status");
      return r.json();
    }).then(function(res){
      var cats = res.categories || [];
      $("feedTabs").innerHTML = cats.map(function(c, i){
        return '<button class="ftab' + (i === 0 ? " active" : "") +
          '" data-cat="' + esc(c.id) + '">' + esc(c.name) + "</button>";
      }).join("");
      if (cats.length){
        feedState.category = cats[0].id;
        loadFeed();
      } else {
        $("feedList").innerHTML = '<div class="empty">暂无分类</div>';
      }
    }).catch(function(){
      feedLoaded = false;
      $("feedList").innerHTML = '<div class="empty">分类加载失败，请检查后端连接。<button class="empty-action" data-retry="categories">重新加载</button></div>';
    });
  }

  function loadFeed(){
    var request = ++feedRequest;
    document.querySelector(".pager").hidden = true;
    $("feedList").innerHTML = '<div class="empty">加载中…</div>';
    fetch(apiUrl("/api/feed?category=" + encodeURIComponent(feedState.category) +
      "&page=" + feedState.page + "&size=" + feedState.size
    )).then(function(r){
      if (!r.ok) throw new Error("bad status");
      return r.json();
    }).then(function(res){
      if (request !== feedRequest) return;
      feedState.total = res.total || 0;
      var items = res.items || [];
      if (!items.length){
        $("feedList").innerHTML = '<div class="empty">暂无内容，换个分类看看</div>';
      } else {
        $("feedList").innerHTML = items.map(feedItemHtml).join("");
      }
      var pages = Math.max(1, Math.ceil(feedState.total / feedState.size));
      $("pageInfo").textContent = feedState.page + " / " + pages + " · 共 " +
        feedState.total + " 条";
      $("prevPage").disabled = feedState.page <= 1;
      $("nextPage").disabled = feedState.page >= pages;
      document.querySelector(".pager").hidden = feedState.total === 0;
    }).catch(function(){
      if (request !== feedRequest) return;
      $("feedList").innerHTML = '<div class="empty">内容加载失败。<button class="empty-action" data-retry="feed">重新加载</button></div>';
    });
  }

  $("feedList").addEventListener("click", function(e){
    var retry = e.target.closest("[data-retry]");
    if (!retry) return;
    if (retry.dataset.retry === "categories") loadFeedTabs();
    else loadFeed();
  });

  $("feedTabs").addEventListener("click", function(e){
    var b = e.target.closest(".ftab");
    if (!b) return;
    document.querySelectorAll(".ftab").forEach(function(t){
      t.classList.remove("active");
    });
    b.classList.add("active");
    feedState.category = b.dataset.cat;
    feedState.page = 1;
    loadFeed();
  });
  $("prevPage").addEventListener("click", function(){
    if (feedState.page > 1){ feedState.page--; loadFeed(); }
  });
  $("nextPage").addEventListener("click", function(){
    feedState.page++; loadFeed();
  });

  /* ===== 校园工具 ===== */
  function loadTools(){
    toolsLoaded = true;
    $("toolGrid").innerHTML = '<div class="empty">加载中…</div>';
    fetch(apiUrl("/api/tools")).then(function(r){
      if (!r.ok) throw new Error("bad status");
      return r.json();
    }).then(function(res){
      var tools = res.tools || [];
      if (!tools.length){
        $("toolGrid").innerHTML = '<div class="empty">暂无工具</div>';
        return;
      }
      $("toolGrid").innerHTML = tools.map(function(t){
        return '<button class="tool-card" data-tool="' + esc(t.id) + '">' +
          '<div class="t-name">' + esc(t.name) + "</div>" +
          '<div class="t-desc">' + esc(t.desc) + "</div></button>";
      }).join("");
    }).catch(function(){
      toolsLoaded = false;
      $("toolGrid").innerHTML = '<div class="empty">工具加载失败，请检查后端连接。<button class="empty-action" data-retry="tools">重新加载</button></div>';
    });
  }

  $("toolGrid").addEventListener("click", function(e){
    if (e.target.closest('[data-retry="tools"]')) { loadTools(); return; }
    var card = e.target.closest(".tool-card");
    if (!card) return;
    document.querySelectorAll(".tool-card").forEach(function(c){
      c.classList.remove("active");
    });
    card.classList.add("active");
    var id = card.dataset.tool;
    $("toolResult").innerHTML = '<div class="empty">检索中…</div>';
    fetch(apiUrl("/api/tools/" + encodeURIComponent(id))).then(function(r){
      if (!r.ok) throw new Error("bad status");
      return r.json();
    }).then(function(res){
      if (res.error){
        $("toolResult").innerHTML = '<div class="empty">' + esc(res.error) + "</div>";
        return;
      }
      var items = res.items || [];
      var head = '<div class="tr-head"><span class="tr-title">' +
        esc(res.name) + " · 相关资料（" + items.length + "）</span>" +
        '<button class="quick ask-btn" data-ask="' + esc(res.ask || "") +
        '">去问答深挖 →</button></div>';
      if (!items.length){
        $("toolResult").innerHTML = head +
          '<div class="empty">知识库未找到相关资料，可点右侧按钮去问答页提问</div>';
        return;
      }
      $("toolResult").innerHTML = head +
        '<div class="feed-list">' + items.map(feedItemHtml).join("") + "</div>";
    }).catch(function(){
      $("toolResult").innerHTML = '<div class="empty">检索失败。<button class="empty-action" data-retry-tool="' + esc(id) + '">重新检索</button></div>';
    });
  });

  $("toolResult").addEventListener("click", function(e){
    var retry = e.target.closest("[data-retry-tool]");
    if (retry) {
      document.querySelectorAll(".tool-card").forEach(function(c){
        if (c.dataset.tool === retry.dataset.retryTool) c.click();
      });
      return;
    }
    var b = e.target.closest(".ask-btn");
    if (!b || !b.dataset.ask) return;
    switchView("chat");
    send(b.dataset.ask);
  });

  /* ===== 我的（收藏 / 订阅） ===== */
  function renderMine(){
    if (mineTab === "fav") renderFavs();
    else renderSubs();
  }

  function renderFavs(){
    var list = loadFavs();
    if (!list.length){
      $("mineFav").innerHTML =
        '<div class="empty">还没有收藏，点击条目右侧 ☆ 收藏</div>';
      return;
    }
    $("mineFav").innerHTML = '<div class="feed-list">' +
      list.map(feedItemHtml).join("") + "</div>";
  }

  function renderSubs(){
    var subs = loadSubs();
    var html = '<div class="sub-bar">' +
      '<select id="subSel"><option value="">选择板块订阅…</option></select>' +
      '<button class="quick" id="subAdd">添加订阅</button></div>';
    html += '<div class="chips">';
    if (subs.length){
      html += subs.map(function(b){
        return '<span class="chip">' + esc(b) +
          '<button class="x" type="button" data-board="' + esc(b) +
          '" aria-label="取消订阅' + esc(b) + '">×</button></span>';
      }).join("");
    } else {
      html += '<span style="font-size:12.5px;color:var(--text-3)">未订阅任何板块</span>';
    }
    html += "</div><div id=\"subUpdates\"></div>";
    $("mineSub").innerHTML = html;

    // 板块下拉（排除已订阅）
    fetch(apiUrl("/api/boards")).then(function(r){
      if (!r.ok) throw new Error("bad status");
      return r.json();
    }).then(function(res){
      var sel = $("subSel");
      if (!sel) return;
      (res.boards || []).forEach(function(b){
        if (subs.indexOf(b.name) >= 0) return;
        var opt = document.createElement("option");
        opt.value = b.name;
        opt.textContent = b.name + "（" + b.count + "）";
        sel.appendChild(opt);
      });
    }).catch(function(){});

    // 订阅板块最新内容
    if (!subs.length) return;
    $("subUpdates").innerHTML = '<div class="empty">加载订阅更新…</div>';
    Promise.all(subs.map(function(board){
      return fetch(apiUrl("/api/feed?board=" + encodeURIComponent(board) + "&size=5"))
        .then(function(r){ if (!r.ok) throw new Error("bad status"); return r.json(); })
        .then(function(res){ return { board: board, items: res.items || [] }; })
        .catch(function(){ return { board: board, items: [], failed: true }; })
    })).then(function(groups){
      $("subUpdates").innerHTML =
        '<div class="mine-section-title">订阅板块最新</div>' +
        groups.map(function(g){
          return '<div class="sub-group"><h3>' + esc(g.board) + "</h3>" +
            (g.items.length
              ? '<div class="feed-list">' + g.items.map(feedItemHtml).join("") + "</div>"
              : '<div class="empty" style="padding:10px 0">' +
                (g.failed ? "加载失败，请检查后端连接" : "暂无新内容") + "</div>") +
            "</div>";
        }).join("");
    });
  }

  $("mineSub").addEventListener("click", function(e){
    var add = e.target.closest("#subAdd");
    if (add){
      var sel = $("subSel");
      if (!sel || !sel.value) return;
      var subs = loadSubs();
      if (subs.indexOf(sel.value) < 0){
        subs.push(sel.value);
        saveSubs(subs);
        renderSubs();
      }
      return;
    }
    var x = e.target.closest(".chip .x");
    if (x){
      var board = x.dataset.board;
      saveSubs(loadSubs().filter(function(b){ return b !== board; }));
      renderSubs();
    }
  });

  document.querySelectorAll(".mtab").forEach(function(t){
    t.addEventListener("click", function(){
      mineTab = t.dataset.mine;
      document.querySelectorAll(".mtab").forEach(function(m){
        m.classList.toggle("active", m.dataset.mine === mineTab);
          m.setAttribute("aria-pressed", String(m.dataset.mine === mineTab));
      });
      // 两个页签互斥显示，缺这一步「订阅」内容会被 hidden 永久挡住
      $("mineFav").hidden = mineTab !== "fav";
      $("mineSub").hidden = mineTab !== "sub";
      renderMine();
    });
  });

  /* ===== 智能问答 ===== */
  var area = $("msgArea");
  var input = $("chatInput");
  var sendBtn = $("sendBtn");
  var boardSel = $("boardSel");
  var timeSel = $("timeSel");

  // 加载板块列表（失败时仅保留「全部板块」）
  fetch(apiUrl("/api/boards")).then(function(r){
    if (!r.ok) throw new Error("bad status");
    return r.json();
  }).then(function(res){
    (res.boards || []).forEach(function(b){
      var opt = document.createElement("option");
      opt.value = b.name;
      opt.textContent = b.name + "（" + b.count + "）";
      boardSel.appendChild(opt);
    });
  }).catch(function(){});

  function scrollBottom(){ area.scrollTop = area.scrollHeight; }

  function addMsg(role, html){
    var wrap = document.createElement("div");
    wrap.className = "msg " + role;
    var avatar = role === "user"
      ? '<span class="msg-avatar"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21c0-4 4-6 8-6s8 2 8 6"/></svg></span>'
      : '<span class="msg-avatar"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3c2.8 1.4 5 1.8 7 1.8v8.2c0 4.4-3.4 8-7 10-3.6-2-7-5.6-7-10V4.8c2 0 4.2-.4 7-1.8z"/><path d="M12 6v13M9.5 10h5"/></svg></span>';
    wrap.innerHTML = avatar + '<div class="bubble">' + html + "</div>";
    area.appendChild(wrap);
    scrollBottom();
  }

  function showTyping(){
    var wrap = document.createElement("div");
    wrap.className = "msg bot";
    wrap.setAttribute("aria-label", "正在查找答案");
    wrap.innerHTML = '<span class="msg-avatar"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3c2.8 1.4 5 1.8 7 1.8v8.2c0 4.4-3.4 8-7 10-3.6-2-7-5.6-7-10V4.8c2 0 4.2-.4 7-1.8z"/><path d="M12 6v13M9.5 10h5"/></svg></span>' +
      '<div class="bubble"><span class="typing"><i></i><i></i><i></i></span></div>';
    area.appendChild(wrap);
    scrollBottom();
    return wrap;
  }

  function removeTyping(wrap){
    if (wrap) wrap.remove();
  }

    function srcLine(src){
    var icon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 3h7v7M21 3l-9 9"/><path d="M19 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h6"/></svg>';
    return '<div class="src-line">' + icon + (src === "知识库未收录" ? "知识库未收录" : "来源：" + esc(src)) + "</div>";
  }

  // 直接展示问答引用的原文链接，方便回看与核对。
  function sourcesBlock(sources){
    if (!Array.isArray(sources) || !sources.length) return "";
    var links = sources.map(function(s, i){
      var url = String(s.source || "");
      if (!/^https?:\/\//i.test(url)) return "";
      var item = { title:s.title, url:url, board:s.board_name, time:(s.create_time || "").slice(0,10) };
      return '<div class="src-item"><a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">[' + (i+1) + '] ' + esc(s.title || url) + '</a>' +
        '<span class="src-meta">' + esc(s.board_name || "") + '</span>' + favBtnHtml(item,true) + '</div>';
    }).filter(Boolean);
    return links.length ? '<div class="source-list"><div class="source-heading">资料来源 · 原文链接</div>' + links.join("") + "</div>" : "";
  }

  function send(text){
    text = (text || "").trim();
    if (!text) return;
    if (currentView !== "chat") switchView("chat");
    addMsg("user", esc(text));
    input.value = "";
    var pending = showTyping();
    fetch(apiUrl("/api/chat"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: text,
        board: boardSel.value || null,
        time_range: timeSel.value || null
      })
    }).then(function(r){
      if (!r.ok) throw new Error("bad status");
      return r.json();
    }).then(function(res){
      removeTyping(pending);
      addMsg("bot", esc(res.answer || "服务没有返回回答，请重试。") +
        (res.sources && res.sources.length ? sourcesBlock(res.sources) : (res.source ? srcLine(res.source) : "")));
    }).catch(function(){
      removeTyping(pending);
      addMsg("bot", "暂时无法连接问答服务。请检查「我的 → 后端连接」，然后重试。" +
        '<button class="retry-chat" data-question="' + esc(text) + '">重试此问题</button>');
    });
  }

  area.addEventListener("click", function(e){
    var retry = e.target.closest(".retry-chat");
    if (retry) send(retry.dataset.question);
  });

    sendBtn.addEventListener("click", function(){ send(input.value); });
  input.addEventListener("keydown", function(e){
    // isComposing：中文输入法选词时按回车不应触发发送
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.keyCode !== 229){ e.preventDefault(); send(input.value); }
  });
  /* ===== 后端连接设置 ===== */
  function setApiBase(v){
    var next = (v || DEFAULT_API_BASE).trim().replace(/\/+$/, "");
    try {
      var parsed = new URL(next);
      if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return false;
    } catch(e){ return false; }
    API_BASE = next;
    feedLoaded = false;
    toolsLoaded = false;
    try { localStorage.setItem("zd_api_base", API_BASE); } catch(e){}
    var inp = $("apiBaseInput");
    if (inp) inp.value = API_BASE;
    return true;
  }

  function checkConn(){
    var st = $("connState"), tip = $("connTip");
    if (!st) return;
    st.className = "state";
    st.textContent = "检测中…";
    fetch(apiUrl("/api/health"), { cache:"no-store" })
      .then(function(r){ if (!r.ok) throw new Error("bad status"); return r.json(); })
      .then(function(j){
        st.className = "state ok";
        st.textContent = "已连接";
        var llmText = "LLM " + (j.llm ? "已配置" : "未配置");
        var err = j.llm_error || "";
        if (err) {
          var low = err.toLowerCase();
          llmText = "LLM 异常" + ((err.indexOf("402") >= 0 || low.indexOf("balance") >= 0 ||
            low.indexOf("insufficient") >= 0) ? "（余额不足）" : "（调用失败）");
        }
        if (tip) tip.textContent = "后端 " + API_BASE + " · 知识库条目 " +
          (j.count != null ? j.count : "?") + " · " + llmText;
      })
      .catch(function(){
        st.className = "state bad";
        st.textContent = "未连接";
        if (tip) tip.textContent = "无法连接 " + API_BASE +
          "。请确认后端已启动，或在上方修改地址。";
      });
  }

  $("connToggle").addEventListener("click", function(){
    var body = $("connBody");
    body.hidden = !body.hidden;
    $("connToggle").setAttribute("aria-expanded", String(!body.hidden));
  });
  function saveApiBase(){
    if (!setApiBase($("apiBaseInput").value)){
      $("connTip").textContent = "请输入以 http:// 或 https:// 开头的有效后端地址。";
      $("apiBaseInput").focus();
      return;
    }
    checkConn();
  }
  $("apiBaseSave").addEventListener("click", saveApiBase);
  $("apiBaseReset").addEventListener("click", function(){
    setApiBase(DEFAULT_API_BASE);
    checkConn();
  });
  $("apiBaseInput").addEventListener("keydown", function(e){
    if (e.key === "Enter"){ e.preventDefault(); saveApiBase(); }
  });
  $("apiBaseInput").value = API_BASE;
  checkConn();
})();
