let port, target, poll, busy = false, generation = 0, awaitingCopy = false;
let status = 'Chưa bật cầu nối Windows.';
let preparing;
async function dedicatedTab() {
  if (preparing) return preparing;
  preparing = (async () => {
    const saved = await chrome.storage.session.get('dictationTab');
    let tab;
    if (saved.dictationTab) {
      try {
        tab = await chrome.tabs.get(saved.dictationTab);
        const url = new URL(tab.url);
        if (url.origin !== 'https://chatgpt.com' || url.pathname !== '/') {
          throw new Error('Tab dictation đã chuyển sang trang/cuộc trò chuyện khác. Đóng tab đó rồi bật lại; không điều khiển tab làm việc.');
        }
      } catch (error) {
        if (tab) throw error;
      }
    }
    if (!tab) {
      tab = await chrome.tabs.create({url:'https://chatgpt.com/', active:false});
      await chrome.storage.session.set({dictationTab:tab.id});
    }
    const groupId = await chrome.tabs.group({tabIds:[tab.id]});
    await chrome.tabGroups.update(groupId, {title:'🎙 Dictation', color:'purple'});
    if (tab.status !== 'complete') {
      await new Promise((resolve,reject) => {
        const timer = setTimeout(() => { chrome.tabs.onUpdated.removeListener(done); reject(new Error('Tab dictation chưa tải xong. Thử bật lại.')); }, 30000);
        function done(id, change) { if (id === tab.id && change.status === 'complete') { clearTimeout(timer); chrome.tabs.onUpdated.removeListener(done); resolve(); } }
        chrome.tabs.onUpdated.addListener(done);
        chrome.tabs.get(tab.id).then(current => { if(current.status === 'complete') done(tab.id,{status:'complete'}); }).catch(reject);
      });
    }
    await chrome.scripting.executeScript({target:{tabId:tab.id},files:['content.js']});
    return tab.id;
  })();
  try { return await preparing; } finally { preparing = undefined; }
}
async function tabAction(action, extra = {}) {
  if (!target) throw new Error('Chưa chọn tab ChatGPT.');
  const tab = await chrome.tabs.get(target);
  const url = new URL(tab.url);
  if (url.origin !== 'https://chatgpt.com' || url.pathname !== '/') throw new Error('Tab chuyên dụng đã chuyển trang. Không thao tác trên cuộc trò chuyện làm việc.');
  return chrome.tabs.sendMessage(target, {type:'dictation-trial', action, ...extra});
}
function disconnect() {
  clearInterval(poll); poll = undefined; busy = false; awaitingCopy = false; generation++;
  const old = port; port = undefined; old?.disconnect();
}
async function event(message) {
  try {
    if (message.event === 'start') {
      if (busy) { port?.postMessage({type:'abort'}); return; }
      busy = true;
      const result = await tabAction('start');
      status = result.status;
      if (result.error) { busy = false; port?.postMessage({type:'abort', reason:result.status}); }
    } else if (message.event === 'stop') {
      if (!busy) return;
      // Page UI may still be obtaining microphone access when the keys release.
      const token = generation;
      let attempts = 0;
      const stop = async () => {
        if (!port || token !== generation || !busy) return;
        const result = await tabAction('stop');
        if (result.error) {
          if (++attempts < 30) { setTimeout(() => stop().catch(fail), 100); return; }
          throw new Error(result.status);
        }
        status = result.status;
        const until = Date.now() + 35000;
        poll = setInterval(async () => {
          try {
            const value = await tabAction('status');
            if (!busy || awaitingCopy || token !== generation) return;
            status = value.status;
            if (value.state === 'done' && value.text) {
              clearInterval(poll); poll = undefined;
              awaitingCopy = true;
              status = 'Đã lấy chữ; đang gửi tới clipboard Windows…';
              port.postMessage({type:'result', text:value.text});
            } else if (Date.now() > until) throw new Error('ChatGPT chưa trả chữ sau 35 giây.');
          } catch (error) { fail(error); }
        }, 250);
      };
      await stop();
    } else if (message.event === 'copied') {
      const result = await tabAction('clearCopied', {copied:message.text});
      status = message.status + (result.error ? ' ' + result.status : ' Đã xóa ô ChatGPT.');
      busy = false; awaitingCopy = false;
    } else if (message.event === 'failed') {
      busy = false; awaitingCopy = false;
      status = 'Windows thất bại: ' + message.status + '. Có thể thử lượt tiếp theo.';
    } else if (message.event === 'status') status = message.status;
  } catch (error) { fail(error); }
}
function fail(error) {
  clearInterval(poll); poll = undefined; busy = false; awaitingCopy = false; generation++;
  status = error.message || String(error);
  port?.postMessage({type:'abort', reason:status});
  tabAction('cancel').catch(()=>{});
}
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (message?.type !== 'windows-bridge') return;
  (async () => {
  if (message.action === 'enable') {
    if (busy) throw new Error('Đang xử lý lượt thu; hãy chờ hoặc Tắt trước.');
    const previous = target;
    disconnect();
    if (previous) {
      await chrome.tabs.sendMessage(previous,{type:'dictation-trial',action:'windowsMode',enabled:false}).catch(()=>{});
    }
    target = await dedicatedTab();
    port = chrome.runtime.connectNative('local.chatgpt_dictation');
    const current = port;
    port.onMessage.addListener(event);
    port.onDisconnect.addListener(() => {
      if (port !== current) return;
      status = chrome.runtime.lastError?.message || 'Cầu nối Windows đã tắt.';
      clearInterval(poll); busy = false; awaitingCopy = false; generation++; port = undefined;
      tabAction('cancel').catch(()=>{});
      tabAction('windowsMode', {enabled:false}).catch(()=>{});
    });
    status = 'Đang kết nối Windows…';
    tabAction('windowsMode', {enabled:true}).catch(fail);
  } else if (message.action === 'disable') {
    disconnect(); tabAction('cancel').catch(()=>{}); status = 'Đã tắt phím tắt Windows.';
    tabAction('windowsMode', {enabled:false}).catch(()=>{});
  } else if (message.action === 'show') {
    if (!target) target = await dedicatedTab();
    const tab = await chrome.tabs.get(target);
    await chrome.tabs.update(target,{active:true});
    await chrome.windows.update(tab.windowId,{focused:true});
  }
  reply({status, enabled:!!port, target});
  })().catch(error => reply({status:error.message, enabled:!!port, error:true}));
  return true;
});
