const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
let listener,nativeListener, starts=0, sent=[], stored={},created=0,targets=[];
const port={postMessage(m){sent.push(m)},disconnect(){},onMessage:{addListener(fn){nativeListener=fn}},onDisconnect:{addListener(){}}};
const context={URL,setInterval(){return 1},clearInterval(){},setTimeout(){},chrome:{
 storage:{session:{async get(){return stored},async set(v){stored=v}}},
 scripting:{async executeScript(){}},tabGroups:{async update(){}},
 tabs:{async get(id){return {id,url:'https://chatgpt.com/',status:'complete'}},async create(){created++;return {id:99,url:'https://chatgpt.com/',status:'complete'}},async group(){return 1},async sendMessage(id,m){
 targets.push(id);
 if(m.action==='start')starts++;
 return {status:'ok',state:m.action==='start'?'recording':'idle'};
}},runtime:{connectNative(){return port},onMessage:{addListener(fn){listener=fn}}}}};
vm.createContext(context);vm.runInContext(fs.readFileSync(__dirname+'/background.js','utf8'),context);
(async()=>{
 await new Promise(resolve=>listener({type:'windows-bridge',action:'enable',tabId:6},{},resolve));
 await nativeListener({event:'start'});
 await nativeListener({event:'failed',status:'synthetic clipboard failure'});
 await nativeListener({event:'start'});
 assert.equal(starts,2,'Windows failure must release busy for next recording');
 assert.equal(sent.filter(m=>m.type==='abort').length,0);
 assert.ok(targets.every(id=>id===99),'Never use work tab 6');
 await new Promise(resolve=>listener({type:'windows-bridge',action:'disable'},{},resolve));
 await new Promise(resolve=>listener({type:'windows-bridge',action:'enable',tabId:6},{},resolve));
 assert.equal(created,1,'Reuse dedicated tab instead of creating duplicates');
 console.log('PASS: retry after failure, dedicated tab isolation, reuse same tab');
})().catch(e=>{console.error(e);process.exitCode=1});
