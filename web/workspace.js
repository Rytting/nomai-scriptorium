/* Local editor checkpoints. Structured cloning preserves BigInts and exact grids;
   a checkpoint never commits a draft or decodes/re-encodes the wall to save it. */
const WORKSPACE_DB = "nomai-workspace-v1";
let workspaceDB = null, workspaceReady = false, workspaceBusy = false;
let workspaceTimer = null, workspaceRevision = 0, savedRevision = 0;
let saveStatus = "Not saved locally", saveQueue = Promise.resolve();
let historyPast = [], historyFuture = [], historyGroup = null;
const HISTORY_LIMIT = 20;

function captureWorkspace(){
  if (state.mode !== "write") return state.writerDraft?.workspace || null;
  keepAimDraft();
  return structuredClone({ version:1, lang:LANG, scroll:state.scroll, svg:state.svg,
    settings:{hw:state.hw,seed:state.seed,tilt:state.tilt,flip:state.flip,
      handMix:state.handMix,tight:state.tight},
    composer:{text:$("msg").value,sig:$("sig").value,signed:state.signed,
      dialect:state.dialect,base:state.base},
    aim:state.aim, aimChosen:state.aimChosen, drafts:state.editDrafts || new Map(),
    committed:state.committed, source:state.scrollSource,
    placements:(state.placements || []).map(p=>({ncols:p.L.ncols,tilt:p.L.tilt,
      flip:p.L.flip,tight:p.L.b,shift:p.shift,seed:p.seed,verified:p.verified})),
    view:editorView, layoutKey:state.layoutKey,
    openSettings:[...document.querySelectorAll(".editor-settings")].map(d=>d.open)
  });
}
function validateWorkspace(s){
  if (!s || s.version!==1 || !Array.isArray(s.scroll) || s.scroll.length>1000
      || typeof s.svg!=="string" || !s.composer || !s.settings
      || !["new","edit","reply"].includes(s.aim?.kind) || !Number.isInteger(s.aim.index)
      || !(s.drafts instanceof Map) || !Array.isArray(s.placements)) throw Error("Invalid checkpoint");
  for (const [i,sp] of s.scroll.entries()){
    if(typeof sp.text!=="string" || typeof sp.sig!=="string"
      || !["strict","upstream"].includes(sp.dialect) || ![256,200000].includes(sp.base)
      || !(sp.grid?.glyphs instanceof Map) || !Array.isArray(sp.grid.paths)
      || !Array.isArray(sp.grid.conns) || !Number.isInteger(sp.grid.ncols)
      || (i===0 ? sp.parent!==null : !Number.isInteger(sp.parent) || sp.parent<0 || sp.parent>=i))
      throw Error("Invalid wall record");
  }
  if(s.scroll.length && (s.aim.index<0 || s.aim.index>=s.scroll.length
    || s.placements.length!==s.scroll.length)) throw Error("Invalid target");
  for(const p of s.placements) if(!Array.isArray(p.shift) || p.shift.length!==2
    || ![p.ncols,p.tilt,p.flip,p.tight,p.seed,...p.shift].every(Number.isFinite))
    throw Error("Invalid placement");
  if(!["hw","seed","tilt","flip","handMix","tight"].every(k=>Number.isFinite(s.settings[k])))
    throw Error("Invalid settings");
  const c=s.composer;
  if(typeof c.text!=="string" || typeof c.sig!=="string" || typeof c.signed!=="boolean"
    || ![256,200000].includes(c.base) || !["strict","upstream"].includes(c.dialect))
    throw Error("Invalid composer");
  if(s.view && (!Object.values(s.view).every(Number.isFinite) || s.view.zoom<1 || s.view.zoom>4
    || s.view.w<=0 || s.view.h<=0))throw Error("Invalid viewport");
}
function restoreWorkspace(saved){
  validateWorkspace(saved);
  const s=structuredClone(saved);
  workspaceBusy=true;
  try {
    if(reshapeTimer){clearTimeout(reshapeTimer);reshapeTimer=null;}
    stopTranslation(); cancelReadLoad();
    state.mode="write"; state.pending=null; state.writerDraft=null;
    Object.assign(state,s.settings);
    state.scroll=s.scroll;state.svg=s.svg;state.aim=s.aim;state.aimChosen=s.aimChosen;
    state.editDrafts=s.drafts;state.committed=s.committed;state.scrollSource=s.source;
    state.written=s.scroll[0]?.text || "";state.signedAs=s.composer.signed?s.composer.sig:"";
    state.seen=new Set(s.scroll.map((_,i)=>i));state.sel=s.aim.index;
    state.parents=s.scroll.map(sp=>sp.parent);
    state.placements=s.placements.map(p=>({L:layoutFor(p.ncols,p.tilt,p.flip,p.tight),
      shift:p.shift,seed:p.seed,verified:p.verified}));
    state.layoutKey=s.layoutKey;state.laidGrids=s.scroll.map(sp=>sp.grid);
    state.laidFlips=s.scroll.map(sp=>sp.flip);
    syncEditorLayout();
    for(const id of ["write-pane","write-main","write-actions","write-controls"]) $(id).hidden=false;
    $("read-pane").hidden=true;$("tcell").innerHTML="";
    $("m-write").setAttribute("aria-pressed","true");$("m-read").setAttribute("aria-pressed","false");
    $("msg").value=s.composer.text;$("sig").value=s.composer.sig;
    setBaseUI(s.composer.base);setDialectUI(s.composer.dialect);setSigned(s.composer.signed,false);
    for(const [id,value] of [["hw",state.hw],["tight",state.tight],["handmix",state.handMix],
      ["tilt",Math.round(state.tilt*180/Math.PI)]]) $(id).value=value;
    hwRead();syncMix();syncTilt();syncCurl();
    $("tight-read").textContent=t(state.tight<=.22?"very tight":state.tight<=.34?"tight":state.tight<=.46?"open":"very open");
    if(s.scroll.length){
      state.track=trackFromLayout(state.placements[0].L);state.socket=socketFor(state.track);
      draw(s.svg,false);applyInk(sigsOf());
      if(s.view){editorView=s.view;applyWallView();}
      pointEditor(false);paint(s.scroll,false,false,false);
    }else{state.socket=null;state.track=null;editorView=null;empty("waiting for words");}
    if(s.openSettings)document.querySelectorAll(".editor-settings").forEach((d,i)=>d.open=!!s.openSettings[i]);
    paintThread();showAim();syncWrite();
  } finally { workspaceBusy=false; }
}
function paintSaveStatus(){
  const el=$("editor-save-status");if(el)el.textContent=t(saveStatus);
}
function scheduleWorkspaceSave(){
  if(!workspaceReady || workspaceBusy || state.mode!=="write")return;
  workspaceRevision++;saveStatus="Saving…";paintSaveStatus();
  clearTimeout(workspaceTimer);
  workspaceTimer=setTimeout(()=>saveWorkspace(false),500);
}
function saveWorkspace(manual=false){
  clearTimeout(workspaceTimer);workspaceTimer=null;
  if(!workspaceReady)return Promise.resolve(false);
  // Shape controls are debounced. Saving must include the resulting drawing, too.
  if(reshapeTimer){clearTimeout(reshapeTimer);reshapeTimer=null;timedBuild();}
  let snapshot;
  try{snapshot=captureWorkspace();}
  catch(e){saveStatus="Local save unavailable";paintSaveStatus();if(manual)hud(t(saveStatus));return Promise.resolve(false);}
  const revision=workspaceRevision;
  if(!snapshot)return Promise.resolve(false);
  const write=async()=>{
    try{
      if(!workspaceDB)throw Error("Storage unavailable");
      await new Promise((resolve,reject)=>{
        const tx=workspaceDB.transaction("walls","readwrite");
        tx.objectStore("walls").put(snapshot,"current");
        tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error);
      });
      savedRevision=Math.max(savedRevision,revision);
      if(savedRevision===workspaceRevision)saveStatus="Autosaved";
      if(manual)hud(t("Saved"));
      paintSaveStatus();return true;
    }catch(e){saveStatus="Local save unavailable";paintSaveStatus();if(manual)hud(t(saveStatus));return false;}
  };
  saveQueue=saveQueue.then(write,write);
  return saveQueue;
}
function syncHistory(){
  if($("editor-undo"))$("editor-undo").disabled=!historyPast.length;
  if($("editor-redo"))$("editor-redo").disabled=!historyFuture.length;
}
function rememberHistory(group=null, committed=false){
  if(!workspaceReady || workspaceBusy || state.mode!=="write")return;
  if(group && historyGroup===group)return;
  const s=captureWorkspace();
  if(committed && s.aim.kind==="edit" && s.scroll[s.aim.index]){
    const sp=s.scroll[s.aim.index];
    s.composer={text:sp.text,sig:sp.sig,signed:!!sp.sig,dialect:sp.dialect,base:sp.base};
    s.drafts.delete("edit:"+s.aim.index);
    s.committed=JSON.stringify([sp.text,sp.sig,sp.dialect,sp.base,"edit",s.aim.index]);
  }
  historyPast.push(s);if(historyPast.length>HISTORY_LIMIT)historyPast.shift();
  historyFuture=[];historyGroup=group;syncHistory();
}
function travelHistory(direction){
  if(state.mode!=="write")return;
  if(reshapeTimer){clearTimeout(reshapeTimer);reshapeTimer=null;timedBuild();}
  const from=direction<0?historyPast:historyFuture,to=direction<0?historyFuture:historyPast;
  if(!from.length)return;
  const current=captureWorkspace(),previous=from[from.length-1];
  restoreWorkspace(previous);from.pop();to.push(current);historyGroup=null;
  syncHistory();scheduleWorkspaceSave();
}
async function initWorkspace(){
  let interacted=false;
  const mark=()=>{interacted=true;};
  document.addEventListener("input",mark,true);document.addEventListener("pointerdown",mark,true);
  try{
    workspaceDB=await new Promise((resolve,reject)=>{
      const req=indexedDB.open(WORKSPACE_DB,1);
      req.onupgradeneeded=()=>req.result.createObjectStore("walls");
      req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);
      req.onblocked=()=>reject(Error("Storage busy"));
    });
    const saved=await new Promise((resolve,reject)=>{
      const req=workspaceDB.transaction("walls").objectStore("walls").get("current");
      req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);
    });
    if(saved){
      try{
        const libraryEntry=location.hash.startsWith("#library-scroll=");
        if(libraryEntry && state.mode==="read" && state.writerDraft?.workspace.source==="opening"){
          // The library borrows the reader; the saved writing stays behind it.
          validateWorkspace(saved);
          state.writerDraft={lang:saved.lang || LANG,workspace:saved};
          saveStatus="Autosaved";
        }else if(!interacted && !libraryEntry){
          restoreWorkspace(saved);saveStatus="Autosaved";
        }
      }
      catch(e){saveStatus="Could not restore saved wall";hud(t(saveStatus));}
    }
  }catch(e){saveStatus="Local save unavailable";}
  finally{
    document.removeEventListener("input",mark,true);document.removeEventListener("pointerdown",mark,true);
    workspaceReady=true;paintSaveStatus();syncHistory();
  }
  for(const id of ["hw","tight","handmix","tilt"]){
    const el=$(id),input=el.oninput;
    el.oninput=e=>{rememberHistory("shape:"+id);input(e);scheduleWorkspaceSave();};
    el.addEventListener("change",()=>{historyGroup=null;});
  }
  document.addEventListener("input",()=>scheduleWorkspaceSave());
  document.addEventListener("click",()=>scheduleWorkspaceSave());
  document.addEventListener("pointerup",()=>scheduleWorkspaceSave());
  document.addEventListener("keydown",e=>{
    const mod=e.ctrlKey||e.metaKey,key=e.key.toLowerCase();
    if(mod && key==="s"){e.preventDefault();saveWorkspace(true);return;}
    if(state.mode!=="write" || !mod || e.altKey
      || e.target.closest('input,textarea,[contenteditable]'))return;
    if(key==="z" || key==="y"){
      e.preventDefault();travelHistory(key==="y" || e.shiftKey ? 1 : -1);
    }
  });
  const flush=()=>{if(workspaceTimer || savedRevision<workspaceRevision)saveWorkspace(false);};
  window.addEventListener("pagehide",flush);
  document.addEventListener("visibilitychange",()=>{if(document.hidden)flush();});
}
