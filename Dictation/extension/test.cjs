const { readFileSync } = require('node:fs');
const { runInNewContext } = require('node:vm');
const assert = require('node:assert/strict');
let handler, input = '', loggedOut = false, recording = false, starts = 0, sends = 0;
let observers = [];
const listeners = {};
const fakeWindow = {addEventListener(){},confirm(){throw new Error('No confirmation dialog should be shown');}};
const make = (label, click) => ({disabled:false, textContent:label, getClientRects:()=>[{}], getAttribute:()=>label, click});
const send = make('Send message', ()=>sends++);
const start = make('Dictate', ()=>{ recording=true; starts++; });
const submit = make('Stop dictation', ()=>{recording=false; input='Xin chào tiếng Việt';});
const cancel = make('Cancel dictation', ()=>{recording=false;});
class Textarea {
  get value(){return input;}
  set value(value){input=value;}
  get tagName(){return 'TEXTAREA';}
  getClientRects(){return [{}];}
  dispatchEvent(){}
}
runInNewContext(readFileSync(__dirname+'/content.js','utf8'), {
  window:fakeWindow, performance:{now:()=>0},
  document:{documentElement:{appendChild(){}},addEventListener(name,fn){listeners[name]=fn;},createElement(){return {style:{},setAttribute(){}};}, querySelectorAll(selector) {
    if (selector==='button') return [...(loggedOut?[make('Log in',()=>{})]:[]),send,...(recording?[submit,cancel]:[start])];
    return [new Textarea()];
  }},
  chrome:{runtime:{id:'test', onMessage:{addListener(fn){handler=fn;}}}},
  MutationObserver:class {constructor(fn){observers.push(fn);} observe(){} disconnect(){}},
  HTMLTextAreaElement:Textarea, Event:class {},
  setTimeout:()=>1, clearTimeout:()=>{}
});
function action(action, extra={}) {let result; handler({type:'dictation-trial',action,...extra},{id:'test'},v=>result=v); return result;}
loggedOut=true;
assert.match(action('start').status,/đăng nhập/);
assert.equal(starts,0);
loggedOut=false; input='draft';
assert.match(action('start').status,/bản nháp/);
assert.equal(starts,0);
input=''; assert.equal(action('start').state,'recording');
action('stop'); // No observer callback: simulate a throttled background tab.
assert.equal(action('status').text,'Xin chào tiếng Việt');
assert.equal(action('status').state,'done');
input='User edited draft';
assert.equal(action('clearCopied',{copied:'wrong result'}).error,true);
assert.equal(input,'User edited draft');
assert.equal(action('clearCopied',{copied:'Xin chào tiếng Việt'}).state,'idle');
assert.equal(input,'');
assert.equal(action('status').text,'Xin chào tiếng Việt');
const key = {isTrusted:true,code:'Backquote',ctrlKey:true,preventDefault(){}};
listeners.keydown(key);
assert.equal(recording,true);
const count=starts;
listeners.keydown({...key,repeat:true});
assert.equal(starts,count);
listeners.keyup({...key,ctrlKey:false});
assert.equal(recording,false);
observers.forEach(fn=>fn());
assert.equal(action('status').state,'done');
assert.equal(sends,0);
console.log('PASS: login/draft guards, dictation result, clear even edited composer after copy, no Send message');
