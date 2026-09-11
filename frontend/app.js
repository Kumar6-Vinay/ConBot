const form=document.getElementById("chatForm");
const input=document.getElementById("promptInput");
const messages=document.getElementById("chatMessages");
const send=document.querySelector(".send");
const title=document.getElementById("chatTitle");
const historyKey="conbot-history-v2",themeKey="conbot-theme";
const API=location.hostname==="localhost"||location.hostname==="127.0.0.1"?"http://localhost:8000":"";
const MAX=4000,TIMEOUT=125000;

function escapeHtml(s){return s.replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;")}
function inline(s){return escapeHtml(s).replace(/\*\*(.+?)\*\*/g,"<strong>$1</strong>").replace(/\*([^*\n]+)\*/g,"<em>$1</em>")}
function markdown(s){
  const out=[];let p=[],list=null;
  const fp=()=>{if(p.length){out.push("<p>"+inline(p.join("\n")).replaceAll("\n","<br>")+"</p>");p=[]}};
  const fl=()=>{if(list){out.push("</"+list+">");list=null}};
  for(const raw of s.replace(/\r\n/g,"\n").split("\n")){
    const l=raw.trim();if(!l){fp();fl();continue}
    const h=l.match(/^#{1,3}\s+(.+)$/);
    if(h){fp();fl();const n=h[0].match(/^#+/)[0].length+1;out.push(`<h${n}>${inline(h[1])}</h${n}>`);continue}
    const u=l.match(/^[-*]\s+(.+)$/),o=l.match(/^\d+[.)]\s+(.+)$/);
    if(u||o){fp();const t=u?"ul":"ol";if(list!==t){fl();out.push("<"+t+">");list=t}out.push("<li>"+inline((u||o)[1])+"</li>");continue}
    fl();p.push(l);
  }fp();fl();return out.join("");
}
function add(text,sender){
  document.getElementById("welcome")?.remove();
  const m=document.createElement("div");m.className="message "+sender;
  if(sender==="user"){
    m.innerHTML='<div class="message-content"><div class="message-text"></div></div>';
    m.querySelector(".message-text").textContent=text;
  }else{
    m.innerHTML='<div class="avatar-ai">AI</div><div class="message-content"><div class="message-name">ConBOT</div><div class="message-text"></div><div class="message-actions"><button class="message-action" data-action="copy" title="Copy">□</button><button class="message-action" data-action="like" title="Helpful">♡</button><button class="message-action" data-action="dislike" title="Not helpful">♧</button></div></div>';
    m.querySelector(".message-text").innerHTML=markdown(text);
  }
  messages.appendChild(m);messages.scrollTop=messages.scrollHeight;
}
function thinking(on){
  document.getElementById("typing")?.remove();if(!on)return;
  const m=document.createElement("div");m.id="typing";m.className="message assistant";
  m.innerHTML='<div class="avatar-ai">AI</div><div class="message-content"><div class="message-name">ConBOT</div><div class="message-text typing">Thinking…</div></div>';
  messages.appendChild(m);messages.scrollTop=messages.scrollHeight;
}
async function ask(prompt){
  const c=new AbortController(),t=setTimeout(()=>c.abort(),TIMEOUT);
  try{
    const r=await fetch(API+"/ask",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({prompt}),signal:c.signal});
    if(!r.ok)throw new Error("HTTP "+r.status);
    const d=await r.json();if(!d||typeof d.answer!=="string"||!d.answer.trim())throw new Error("Invalid");
    return d.answer;
  }catch(e){
    if(e.name==="AbortError")throw new Error("ConBOT is taking longer than expected. Please try again.");
    if(e.message.includes("429"))throw new Error("You're sending questions a little too quickly. Please wait a moment.");
    if(e.message.includes("503")||e.message.includes("504"))throw new Error("ConBOT is temporarily unavailable. Please try again in a few minutes.");
    if(e.message.includes("400"))throw new Error("We couldn't process that question. Please check it and try again.");
    throw new Error("We're having trouble connecting to ConBOT right now. Please try again in a moment.");
  }finally{clearTimeout(t)}
}
function getHistory(){try{return JSON.parse(localStorage.getItem(historyKey)||"[]")}catch{return[]}}
function renderHistory(){
  const a=getHistory(),today=document.getElementById("todayHistory"),y=document.getElementById("yesterdayHistory");today.replaceChildren();y.replaceChildren();
  if(!a.length){const e=document.createElement("div");e.className="history-empty";e.textContent="Your conversations will appear here.";today.appendChild(e);return}
  a.forEach(x=>{const b=document.createElement("button");b.className="history-item";b.textContent=x.title;b.onclick=()=>{title.textContent=x.title;closeSidebar()};today.appendChild(b)})
}
function newChat(){
  messages.innerHTML='<div class="welcome" id="welcome"><div class="mark">◈</div><h1>Ask. Learn. <span>Understand.</span></h1><p>Your AI for everyday questions, learning, ideas and understanding.</p><div class="suggestions"><button data-prompt="Explain GST simply"><b>▧</b><span>Explain GST simply</span><i>→</i></button><button data-prompt="Plan a 3-day Jaipur trip"><b>⌁</b><span>Plan a 3-day Jaipur trip</span><i>→</i></button><button data-prompt="What should I cook today?"><b>♜</b><span>What should I cook?</span><i>→</i></button><button data-prompt="Why is the price of gold changing?"><b>↗</b><span>Why is gold price changing?</span><i>→</i></button></div></div>';
  title.textContent="New conversation";input.value="";input.focus();closeSidebar();
}
function closeSidebar(){document.body.classList.remove("sidebar-open")}
function openSidebar(){document.body.classList.add("sidebar-open")}
async function submit(e){
  e.preventDefault();if(input.disabled)return;const p=input.value.trim();if(!p)return;
  if(p.length>MAX){add("Your question is too long. Please keep it under 4,000 characters.","assistant");return}
  const first=!document.querySelector(".message.user");input.disabled=true;send.disabled=true;add(p,"user");input.value="";input.style.height="auto";
  if(first){const a=getHistory();a.unshift({title:p.replace(/\s+/g," ").slice(0,55),date:Date.now()});localStorage.setItem(historyKey,JSON.stringify(a.slice(0,30)));renderHistory();title.textContent=a[0].title}
  thinking(true);try{add(await ask(p),"assistant")}catch(e){add(e.message,"assistant")}finally{thinking(false);input.disabled=false;send.disabled=false;input.focus()}
}
form.addEventListener("submit",submit);
input.addEventListener("input",()=>{input.style.height="auto";input.style.height=Math.min(input.scrollHeight,190)+"px"});
input.addEventListener("keydown",e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();form.requestSubmit()}});
document.addEventListener("click",e=>{const b=e.target.closest("[data-prompt]");if(!b)return;input.value=b.dataset.prompt;input.focus();input.dispatchEvent(new Event("input"))});
messages.addEventListener("click",async e=>{const b=e.target.closest(".message-action");if(!b)return;if(b.dataset.action==="copy"){try{await navigator.clipboard.writeText(b.closest(".message").querySelector(".message-text").innerText);b.textContent="✓";setTimeout(()=>b.textContent="□",1000)}catch{}}});
document.getElementById("newChat").onclick=newChat;
document.getElementById("newChatTop").onclick=newChat;
document.getElementById("menu").onclick=openSidebar;
document.getElementById("overlay").onclick=closeSidebar;
document.getElementById("searchChats").onclick=()=>add("Chat search will be connected when persistent conversation history is added.","assistant");
document.getElementById("settings").onclick=()=>add("Settings will be added as ConBOT features mature.","assistant");
document.getElementById("help").onclick=()=>add("Start with a question below. ConBOT is designed for everyday questions, learning and understanding.","assistant");
document.getElementById("attachment").onclick=()=>add("File upload is coming next. For now, ask ConBOT directly.","assistant");
document.getElementById("microphone").onclick=()=>add("Voice input is coming next. Your question can still be typed here.","assistant");
document.getElementById("theme").onclick=()=>{const dark=!document.body.classList.contains("dark");document.body.classList.toggle("dark",dark);localStorage.setItem(themeKey,dark?"dark":"light");document.getElementById("themeLabel").textContent=dark?"Light Mode":"Dark Mode"};
if(localStorage.getItem(themeKey)==="dark"){document.body.classList.add("dark");document.getElementById("themeLabel").textContent="Light Mode"}
renderHistory();
window.addEventListener("keydown",e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==="n"){e.preventDefault();newChat()}});
window.addEventListener("keydown",e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==="k"){e.preventDefault();document.getElementById("searchChats").click()}});
