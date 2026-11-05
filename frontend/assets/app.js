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
      '" title="' + (on ? "取消收藏" : "收藏") + '"' +
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
    document.querySelectorAll(".nav-btn").forEach(function(b){
      b.classList.toggle("active", b.dataset.view === name);
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
      $("feedList").innerHTML = '<div class="empty">分类加载失败，请刷新重试</div>';
    });
  }

  function loadFeed(){
    $("feedList").innerHTML = '<div class="empty">加载中…</div>';
    fetch(apiUrl("/api/feed?category=" + encodeURIComponent(feedState.category) +
      "&page=" + feedState.page + "&size=" + feedState.size
    )).then(function(r){
      if (!r.ok) throw new Error("bad status");
      return r.json();
    }).then(function(res){
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
    }).catch(function(){
      $("feedList").innerHTML = '<div class="empty">加载失败，请重试</div>';
    });
  }

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
      $("toolGrid").innerHTML = '<div class="empty">工具加载失败，请刷新重试</div>';
    });
  }

  $("toolGrid").addEventListener("click", function(e){
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
      $("toolResult").innerHTML = '<div class="empty">检索失败，请重试</div>';
    });
  });

  $("toolResult").addEventListener("click", function(e){
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
          '<span class="x" data-board="' + esc(b) + '" title="取消订阅">×</span></span>';
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
        .then(function(r){ return r.json(); })
        .then(function(res){ return { board: board, items: res.items || [] }; })
        .catch(function(){ return { board: board, items: [] }; })
    })).then(function(groups){
      $("subUpdates").innerHTML =
        '<div class="mine-section-title">订阅板块最新</div>' +
        groups.map(function(g){
          return '<div class="sub-group"><h3>' + esc(g.board) + "</h3>" +
            (g.items.length
              ? '<div class="feed-list">' + g.items.map(feedItemHtml).join("") + "</div>"
              : '<div class="empty" style="padding:10px 0">暂无新内容</div>') +
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
      });
      // 两个页签互斥显示，缺这一步「订阅」内容会被 hidden 永久挡住
      $("mineFav").hidden = mineTab !== "fav";
      $("mineSub").hidden = mineTab !== "sub";
      renderMine();
    });
  });

  /* ===== 智能问答（原有逻辑 + 来源收藏） ===== */
  var qa = {
    "保研成绩怎么算？": {
      a: "保研综合成绩一般由学业成绩与综合素质测评构成，不同学院权重可能不同，具体以教务处当年通知为准。",
      src: "教务处官网（示例）"
    },
    "这学期校历安排": {
      a: "校历页签提供教学周、考试周与假期安排，具体日期以学校官方发布为准。",
      src: "学校官网 · 校历（示例）"
    },
    "清水河到沙河班车时刻": {
      a: "工作日开行通勤班车，发车时间与站点以后勤保障部最新通知为准。",
      src: "后勤保障部（示例）"
    }
  };
  var fallback = {
    a: "这个问题知识库暂未收录，建议去对应部门官网核实。",
    src: "知识库未收录"
  };

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
    wrap.id = "typingMsg";
    wrap.innerHTML = '<span class="msg-avatar"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3c2.8 1.4 5 1.8 7 1.8v8.2c0 4.4-3.4 8-7 10-3.6-2-7-5.6-7-10V4.8c2 0 4.2-.4 7-1.8z"/><path d="M12 6v13M9.5 10h5"/></svg></span>' +
      '<div class="bubble"><span class="typing"><i></i><i></i><i></i></span></div>';
    area.appendChild(wrap);
    scrollBottom();
  }

  function removeTyping(){
    var t = document.getElementById("typingMsg");
    if (t) t.remove();
  }

  function srcLine(src){
    var icon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 3h7v7M21 3l-9 9"/><path d="M19 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h6"/></svg>';
    return '<div class="src-line">' + icon + (src === "知识库未收录" ? "知识库未收录" : "来源：" + esc(src)) + "</div>";
  }

  // 全部来源列表（可展开，每条可收藏）
  function sourcesBlock(sources){
    if (!sources || !sources.length) return "";
    var html = '<details class="src-detail"><summary>全部来源（' +
      sources.length + "）</summary>";
    sources.forEach(function(s, i){
      var item = {
        title: s.title, url: s.source,
        board: s.board_name, time: (s.create_time || "").slice(0, 10)
      };
      html += '<div class="src-item"><a href="' + esc(s.source) +
        '" target="_blank" rel="noopener">[' + (i + 1) + "] " +
        esc(s.title) + "</a>" +
        '<span class="src-meta">' + esc(s.board_name) + " · " +
        esc((s.create_time || "").slice(0, 10)) + "</span>" +
        favBtnHtml(item, true) + "</div>";
    });
    return html + "</details>";
  }

  function localReply(text){
    var entry = qa[text] || fallback;
    setTimeout(function(){
      removeTyping();
      addMsg("bot", entry.a + srcLine(entry.src));
    }, 900 + Math.random() * 500);
  }

  function send(text){
    text = (text || "").trim();
    if (!text) return;
    if (currentView !== "chat") switchView("chat");
    addMsg("user", esc(text));
    input.value = "";
    showTyping();
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
      removeTyping();
      addMsg("bot", esc(res.answer) + srcLine(res.source) +
        sourcesBlock(res.sources));
    }).catch(function(){
      localReply(text);
    });
  }

  sendBtn.addEventListener("click", function(){ send(input.value); });
  input.addEventListener("keydown", function(e){
    // isComposing：中文输入法选词时按回车不应触发发送
    if (e.key === "Enter" && !e.isComposing && e.keyCode !== 229) send(input.value);
  });
  $("quickRow").addEventListener("click", function(e){
    var b = e.target.closest(".quick");
    if (b) send(b.getAttribute("data-q"));
  });

  /* ===== 后端连接设置 ===== */
  function setApiBase(v){
    API_BASE = (v || DEFAULT_API_BASE).replace(/\/+$/, "");
    try { localStorage.setItem("zd_api_base", API_BASE); } catch(e){}
    var inp = $("apiBaseInput");
    if (inp) inp.value = API_BASE;
  }

  function checkConn(){
    var st = $("connState"), tip = $("connTip");
    if (!st) return;
    st.className = "state";
    st.textContent = "检测中…";
    fetch(apiUrl("/api/health"), { cache:"no-store" })
      .then(function(r){ return r.json(); })
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
    $("connBody").hidden = !$("connBody").hidden;
  });
  $("apiBaseSave").addEventListener("click", function(){
    setApiBase($("apiBaseInput").value);
    checkConn();
  });
  $("apiBaseReset").addEventListener("click", function(){
    setApiBase(DEFAULT_API_BASE);
    checkConn();
  });
  $("apiBaseInput").addEventListener("keydown", function(e){
    if (e.key === "Enter"){ setApiBase(e.target.value); checkConn(); }
  });
  $("apiBaseInput").value = API_BASE;
  checkConn();
})();
