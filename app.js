/* Public-source research viewer. No keys, tracking, or simulated data. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const state = {data:null, governance:null, feed:null, catalog:null, chain:null, insights:null, feedLimit:60, events:[], sources:[], section:'overview', archive:false, lastFocus:null, filter:null, loading:false};
  const SVG = 'http://www.w3.org/2000/svg';
  const icons = {
    chain:'M4 5h5v5H4z M15 5h5v5h-5z M9 17h6v5H9z M9 7h6 M6 10v7h3 M18 10v7h-3',
    overview:'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
    resources:'m3 20 7-12 4 6 3-5 5 11Z M9 9l3-5 3 5',
    materials:'M4 19V9 M10 19V4 M16 19v-7 M22 19V7',
    geopolitics:'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM3 12h18 M12 3c5 6 5 12 0 18-5-6-5-12 0-18Z',
    technology:'M8 3v4 M16 3v4 M8 17v4 M16 17v4 M3 8h4 M3 16h4 M17 8h4 M17 16h4 M7 7h10v10H7z M10 10h4v4h-4z',
    competition:'M3 6h7v7H3z M14 11h7v7h-7z M10 9h5 M15 6l3 3-3 3 M9 17h5',
    decarbonisation:'M5 19c-4-10 7-15 15-15 0 12-6 18-13 13 M5 21l11-12',
    governance:'M4 21V8l8-5 8 5v13 M8 11h2 M14 11h2 M8 15h2 M14 15h2 M10 21v-3h4v3',
    feeds:'M4 4c9 0 16 7 16 16 M4 10c6 0 10 4 10 10 M4 16a4 4 0 0 1 4 4',
    sources:'M4 6c0-4 16-4 16 0s-16 4-16 0Zm0 0v12c0 4 16 4 16 0V6 M4 12c0 4 16 4 16 0'
  };
  const sections = [
    {id:'overview',label:'决策总览',title:'重点议题与影响路径',kicker:'DECISION INTELLIGENCE'},
    {id:'chain',label:'化学与产业链',title:'化学、工艺与产业链关系',kicker:'BATTERY VALUE CHAIN'},
    {id:'resources',label:'矿权与资源',title:'矿权、资源与上游投资',test:/矿权|资源|上游/,kicker:'RESOURCE SECURITY'},
    {id:'materials',label:'原料与供需',title:'原材料价格与供需观察',test:/原料|价格|供需|材料/,kicker:'MATERIALS & BALANCE'},
    {id:'geopolitics',label:'地缘与航运',title:'地缘、贸易与运输通道',test:/地缘|航运|贸易|政策|冲突/,kicker:'GEOPOLITICS & TRADE'},
    {id:'technology',label:'关键技术',title:'技术瓶颈与突破进展',test:/技术|科研|专利/,kicker:'TECHNOLOGY FRONTIER'},
    {id:'competition',label:'竞争与合作',title:'竞争格局与战略合作',test:/竞争|合作|协同/,kicker:'COMPETITIVE LANDSCAPE'},
    {id:'decarbonisation',label:'矿山零碳',title:'矿山零碳与能源转型',test:/零碳|微电网|换电|用能/,kicker:'MINE DECARBONISATION'},
    {id:'governance',label:'法人治理',title:'法人登记与治理变更',test:/治理|工商|董监高|注册|任免/,kicker:'ENTITY GOVERNANCE'},
    {id:'feeds',label:'研究线索',title:'分层信源与议题线索',kicker:'RESEARCH WORKBENCH'},
    {id:'sources',label:'信源与证据',title:'来源覆盖、类型与运行记录',kicker:'SOURCE TRANSPARENCY'}
  ];
  const el = (tag,cls,text) => { const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined&&text!==null)e.textContent=String(text);return e; };
  const svg = (tag,attrs={}) => {const e=document.createElementNS(SVG,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,String(v));return e;};
  const text = v => Array.isArray(v)?v.map(text).filter(Boolean).join(' · '):(v===null||v===undefined?'':typeof v==='object'?JSON.stringify(v):String(v));
  const safeURL = u => {try{const v=new URL(u,location.href);return ['http:','https:'].includes(v.protocol)?v.href:null;}catch{return null;}};
  const link = (label,url,cls) => {const a=el('a',cls,label);const valid=safeURL(url);if(valid){a.href=valid;a.target='_blank';a.rel='noopener noreferrer';}else a.removeAttribute('href');return a;};
  const asDate = value => {if(!value)return null;const n=new Date(value);return isNaN(n.getTime())?null:n;};
  const shortDate = value => {const d=asDate(value);return d?new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(d).replaceAll('/','-'):'日期未标注';};
  const timeDate = value => {const d=asDate(value);return d?new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(d):'未记录';};
  const pri = event => {const p=text(event.priority).toUpperCase();if(p==='P0'||p.includes('高')||p.includes('紧急'))return 'P0';if(p==='P1'||p.includes('中')||p.includes('重点'))return 'P1';if(p==='P2'||p.includes('低')||p.includes('观察'))return 'P2';return p||'未分级';};
  const isPrimary = event => {const e=text(event.evidence_level);return /^(A|A1|一手|官方|企业披露|公司公告|研究报告|research|primary|official)/i.test(e)&&!/待核验|线索|未核验/.test(e);};
  const prioritySort = (a,b) => ({P0:0,P1:1,P2:2}[pri(a)]??3)-({P0:0,P1:1,P2:2}[pri(b)]??3)||(asDate(b.published_at)?.getTime()||0)-(asDate(a.published_at)?.getTime()||0);
  function normalizedStatus(v){const s=text(v).trim();if(/fail|error|blocked|unavailable|inaccessible|unsuccessful/i.test(s)||/失败|不可访问|无法访问|拒绝访问/.test(s))return 'unavailable';if(/partial|restricted/i.test(s)||/部分|受限|限制|付费/.test(s))return 'partial';if(/not[ _-]?(attempted|checked|visited|verified)|pending|unknown/i.test(s)||/未尝试|未访问|未核验|未检查|尚未|未记录/.test(s))return 'unknown';if(/^(success|ok|available|accessible|verified|reachable)$/i.test(s)||/成功|已核验|可访问|已访问/.test(s))return 'success';return 'unknown';}
  function sourceLabel(s){const status=normalizedStatus(s);return {success:'访问成功',partial:'部分 / 受限',unavailable:'访问失败',unknown:'未记录访问'}[status];}
  function message(t){$('notice').hidden=!t;$('notice').textContent=t||'';}
  function empty(title,description){const e=el('div','empty-state');e.append(el('div','empty-mark','◈'),el('h3','',title),el('p','',description));return e;}
  function cleanEvents(list){return (Array.isArray(list)?list:[]).filter(e=>e&&typeof e==='object'&&e.title).map((e,i)=>({...e,id:e.id||`record-${i}-${e.title}`,category:e.category||'其他公开信息'}));}
  function rebuildData(){
    const base=cleanEvents(state.data?.events);
    const governance=!state.archive?cleanEvents(state.governance?.events).map(e=>({...e,_governance:true})):[];
    const ids=new Set();state.events=[...base,...governance].filter(e=>{const key=e.id;if(ids.has(key))return false;ids.add(key);return true;});
    const sourceKey=new Set();state.sources=[...(state.data?.sources||[]),...(!state.archive?(state.governance?.sources||[]):[])].filter(s=>{const k=text(s.id||s.url||s.name);if(sourceKey.has(k))return false;sourceKey.add(k);return true;});
  }
  async function readJSON(path,optional=false){try{const r=await fetch(path,{cache:'no-store'});if(!r.ok)throw new Error(`HTTP ${r.status}`);return await r.json();}catch(e){if(optional)return null;throw e;}}
  async function load(path='data/latest.json',isArchive=false){
    state.loading=true;$('refresh').disabled=true;message('');
    try{
      const results=await Promise.allSettled([readJSON(path),isArchive?Promise.resolve(null):readJSON('data/governance-latest.json',true),readJSON('data/feed-latest.json',true),readJSON('data/source-catalog.json',true),readJSON('data/chain.json',true),readJSON(isArchive?path.replace('/history/','/insights-history/'):'data/insights.json',true)]);
      if(results[0].status!=='fulfilled')throw results[0].reason;
      if(!results[0].value||typeof results[0].value!=='object')throw new Error('数据结构无效');
      state.data=results[0].value;state.archive=isArchive;state.governance=results[1].status==='fulfilled'?results[1].value:null;state.feed=results[2].status==='fulfilled'?results[2].value:null;
      state.catalog=results[3].status==='fulfilled'?results[3].value:null;state.chain=results[4].status==='fulfilled'?results[4].value:null;state.insights=results[5].status==='fulfilled'?results[5].value:null;rebuildData();fillCategories();fillFeedSources();renderAll();
    }catch(err){
      message(`未能读取${isArchive?'所选历史':'最新'}数据（${err.message}）。${state.data?'当前仍显示此前已加载的快照。':'请稍后刷新，或查看项目更新记录。'}`);
      if(!state.data){$('content').replaceChildren(empty('数据尚未载入','未取得数据时，不展示模拟事件或监控评分。'));$('asof').textContent='尚未读取';$('freshness-text').textContent='数据读取失败';$('overview').hidden=true;renderNav();}
    }finally{state.loading=false;$('refresh').disabled=false;}
  }
  async function loadManifest(){const m=await readJSON('data/manifest.json',true);if(!m)return;let records=Array.isArray(m)?m:(m.snapshots||m.history||m.entries||[]);records=records.map(r=>typeof r==='string'?{date:r,path:`data/history/${r}.json`}:r).filter(r=>r.path||r.file||r.url);records.sort((a,b)=>text(b.date).localeCompare(text(a.date)));for(const r of records){const path=r.path||r.file||r.url;const u=safeURL(path);if(!u||new URL(u).origin!==location.origin)continue;const option=el('option','',r.label||r.date||path);option.value=path;$('snapshot').append(option);}}
  function fillCategories(){const previous=$('category').value;$('category').replaceChildren(el('option','','全部领域'));$('category').firstChild.value='';for(const c of [...new Set([...state.events.map(e=>text(e.category)),...catalogSources().flatMap(sourceCategories)])]){const o=el('option','',c);o.value=c;$('category').append(o);}$('category').value=[...$('category').options].some(o=>o.value===previous)?previous:'';}
  function sectionEvents(section=state.section){const s=sections.find(s=>s.id===section);return s?.test?state.events.filter(e=>s.test.test(text(e.category))):state.events;}
  function currentEvents(){let events=sectionEvents();const query=$('search').value.trim().toLowerCase();const category=$('category').value;const priority=$('priority').value;const evidence=$('evidence').value;const days=$('period').value;const end=asDate(state.data?.meta?.as_of)||asDate(state.data?.meta?.generated_at)||new Date();return events.filter(e=>{
    if(query&&!text([e.title,e.summary,e.impact,e.action,e.entity,e.country,e.category,e.source_name]).toLowerCase().includes(query))return false;
    if(category&&text(e.category)!==category)return false;if(priority&&pri(e)!==priority)return false;
    if(evidence==='primary'&&!isPrimary(e))return false;if(evidence==='other'&&isPrimary(e))return false;
    if(days!=='all'){const d=asDate(e.published_at);if(!d)return false;const age=(end.getTime()-d.getTime())/86400000;if(age>Number(days)||age<-1)return false;}return true;
  }).sort(prioritySort);}
  function navigate(section,route,nodeId){
    if(!sections.some(s=>s.id===section))return;state.section=section;$('category').value='';$('search').value='';
    if(section==='chain'&&(route||nodeId))window.IntelligenceUI?.setRoute(route,nodeId);
    const hash=section==='chain'?(window.IntelligenceUI?.getChainHash?.()||'#chain'):'#'+section;
    history.replaceState(null,'',hash);renderNav();renderContent();
    if(!nodeId)$('main').scrollIntoView({behavior:'smooth',block:'start'});
  }
  function insightContext(){return {data:state.data,chain:state.chain,insights:state.insights,catalog:state.catalog,feed:state.feed,query:$('search').value,onSection:navigate,onEvent:openEvent,onInsight:openInsight};}
  function renderNav(){const nav=$('sections');nav.replaceChildren();for(const section of sections){if(section.id==='feeds'){nav.append(el('div','nav-divider'),el('div','nav-secondary-title','研究底稿'));}const b=el('button','nav-item'+(state.section===section.id?' active':''));b.type='button';b.setAttribute('aria-current',state.section===section.id?'page':'false');const icon=svg('svg',{viewBox:'0 0 24 24',class:'nav-icon','aria-hidden':true,fill:'none',stroke:'currentColor','stroke-width':1.5,'stroke-linejoin':'round','stroke-linecap':'round'});icon.append(svg('path',{d:icons[section.id]}));b.append(icon,el('span','',section.label));const n=section.id==='chain'?(state.chain?.nodes?.length||0):section.id==='overview'?(state.insights?.insights?.length||state.events.length):section.id==='sources'?(catalogSources().length||state.sources.length):section.id==='feeds'?(state.feed?.items?.length||0):sectionEvents(section.id).length;b.append(el('span','nav-count',n||'—'));b.onclick=()=>navigate(section.id);nav.append(b);}}
  function catalogSources(){return Array.isArray(state.catalog?.sources)?state.catalog.sources:[];}
  function sourceCategories(source){return Array.isArray(source.category)?source.category:[source.category||'其他'];}
  function sourceTier(source){return source.source_tier||(/论坛|社区/.test(source.publisher_type||'')?'community':/媒体|杂志/.test(source.publisher_type||'')?'media':/研究|博客/.test(source.publisher_type||'')?'research':'primary');}
  const tierLabels={primary:'原始披露',research:'专业研究',media:'专业媒体',community:'论坛社区'};
  function sourceMode(source){return source.automation_enabled?'auto':source.method==='registry'?'registry':'research';}
  function feedAudit(source){return (state.feed?.sources||[]).find(x=>x.publisher_id===source.publisher_id||x.id===source.feed_source_id||x.id===source.id);}
  function fillFeedSources(){const previous=$('feed-source').value;$('feed-source').replaceChildren(el('option','','全部采集机构'));$('feed-source').firstChild.value='';for(const source of state.feed?.sources||[]){const option=el('option','',source.name);option.value=source.id;$('feed-source').append(option);}$('feed-source').value=[...$('feed-source').options].some(o=>o.value===previous)?previous:'';}
  function renderStats(){const catalog=catalogSources();const stats=[['深度议题',state.insights?.insights?.length||'—','时间脉络、影响路径与决策问题','WHY','accent'],['产业链节点',state.chain?.nodes?.length||'—','矿产、化学、工艺、系统与回收','CHM',''],['已核验事件',state.events.length,'原始披露事实，可查看证据','EVT',''],['独立信源',catalog.length||state.sources.length,'机构去重；采集状态见信源页','SRC','']];const out=$('stats');out.replaceChildren();for(const [label,value,note,code,accent]of stats){const c=el('div','stat');c.append(el('span','stat-code',code),el('div','stat-label',label),el('div','stat-value '+accent,value),el('div','stat-note',note));out.append(c);}}
  function renderPriorities(){const out=$('priorities');out.replaceChildren();const stories=state.insights?.insights||[];const records=stories.length?stories.slice(0,3):[...state.events].sort(prioritySort).slice(0,3);for(const [i,item] of records.entries()){const row=el('article','priority-item');row.append(el('span','priority-rank',String(i+1).padStart(2,'0')));const body=el('div'),meta=el('div','priority-meta');meta.append(el('span','',stories.length?(item.tags||[]).slice(0,2).join(' / '):item.category),el('span','',shortDate(item.as_of||item.published_at)));const title=el('button','priority-title',item.title);title.onclick=()=>stories.length?openInsight(item):openEvent(item);body.append(meta,title,el('p','',item.thesis||item.impact||item.summary));row.append(body);out.append(row);}}
  function renderAll(){const meta=state.data.meta||{};$('asof').textContent=shortDate(meta.as_of||meta.generated_at);$('freshness-text').textContent=`${state.archive?'历史快照':'策展数据'} · 最近核验 ${timeDate(meta.generated_at)}`;$('scope-note').textContent=meta.update_note||meta.scope||'所有事件保留原始来源';$('footer-date').textContent=`数据快照：${shortDate(meta.as_of||meta.generated_at)} · 网页与数据独立更新`;renderStats();renderNav();renderPriorities();renderMarkers();renderContent();}
  function renderContent(){const section=sections.find(s=>s.id===state.section);$('section-title').textContent=section.title;$('section-kicker').textContent=section.kicker;$('overview').hidden=state.section!=='overview';$('filters').hidden=state.section==='chain';const extras=['category','priority','evidence','period'];for(const id of extras)$(id).hidden=id==='category'?['feeds','overview','chain'].includes(state.section):['feeds','sources','overview','chain'].includes(state.section);$('source-mode').hidden=state.section!=='sources';$('source-tier').hidden=!['sources','feeds'].includes(state.section);$('feed-source').hidden=state.section!=='feeds';const content=$('content');content.replaceChildren();
    if(state.section==='chain'){$('result-count').textContent=(state.chain?.nodes?.length||0)+' 个节点 · '+(state.chain?.edges?.length||0)+' 条关系';window.IntelligenceUI?.renderChain(content,insightContext());return;}
    if(state.section==='sources'){renderSources(content);window.IntelligenceUI?.renderSocial(content,state.catalog);return;}if(state.section==='feeds'){renderFeeds(content);return;}
    if(state.section==='overview'&&window.IntelligenceUI?.renderOverview(content,insightContext())){$('result-count').textContent=(state.insights?.insights?.length||0)+' 个重点议题';return;}
    const events=currentEvents();$('result-count').textContent=events.length+' 条已核验事件';
    if(state.section==='materials')renderPrices(content);
    const stories=(state.insights?.insights||[]).filter(x=>section.test?.test(text(x.categories))&&(!$('search').value||text([x.title,x.thesis,x.tags]).toLowerCase().includes($('search').value.toLowerCase())));
    if(stories.length){const group=el('div','related-stories');group.append(el('h3','','先看影响，再看事实'));for(const item of stories)group.append(window.IntelligenceUI.insightCard(item,state.insights,(route,nodeId)=>navigate('chain',route,nodeId)));content.append(group);}
    let target=content;if(stories.length){const archive=el('details','evidence-archive');archive.append(el('summary','',events.length+' 条相关已核验事实'));content.append(archive);target=archive;}
    if(state.section==='governance'){const g=state.governance;if(g){target.append(el('div','section-intro','法人治理快照：'+timeDate(g.meta?.generated_at)));}}
    if(!events.length){target.append(empty('没有符合条件的已收录事实','可以调整筛选条件。'));return;}
    for(const event of events)target.append(eventRow(event));
  }
  function evidenceChip(event){const p=isPrimary(event);return el('span','evidence-chip'+(p?'':' other'),p?'◇ 一手披露':`◇ ${event.evidence_level||'证据待分级'}`);}
  function eventRow(event){const row=el('article','event-row');const stamp=el('div','event-stamp');const date=shortDate(event.published_at);stamp.append(el('div','day',date==='日期未标注'?'未标注':date.slice(5)),el('div','year',date==='日期未标注'?'日期':date.slice(0,4)),el('span','priority-label '+pri(event),pri(event)));const body=el('div','event-main');const meta=el('div','event-meta');meta.append(el('span','category-chip',event.category),el('span','',text(event.country)||'区域未标注'),evidenceChip(event));const title=el('button','event-title',event.title);title.onclick=()=>openEvent(event);body.append(meta,title,el('p','event-summary',event.summary||'请查看原始披露。'));
    const metrics=(Array.isArray(event.metrics)?event.metrics:[]).slice(0,3);if(metrics.length){const list=el('div','metrics-inline');for(const m of metrics){const tag=el('span','metric-inline');if(typeof m==='string')tag.textContent=m;else{tag.append(document.createTextNode((m.label||m.name||'指标')+' '),el('b','',text(m.value)+(m.unit?' '+m.unit:'')));}list.append(tag);}body.append(list);}
    const source=el('div','event-source');source.append(link(event.source_name||'原始来源',event.source_url));if(event.entity)source.append(el('span','entity',text(event.entity)));body.append(source);
    const impact=el('div','event-impact');impact.append(el('span','label','产业与投资影响 · 研判'),el('p','',event.impact||'影响尚待研究，不作自动风险定性。'));const details=el('button','event-detail-link','查看事实、脉络与证据');details.onclick=()=>openEvent(event);impact.append(details);const story=(state.insights?.insights||[]).find(x=>(x.related_event_ids||[]).includes(event.id));if(story){const b=el('button','event-story-link','阅读关联深度分析');b.onclick=()=>openInsight(story);impact.append(b);}row.append(stamp,body,impact);return row;}
  function renderPrices(out){
    const all=Array.isArray(state.data?.prices)?state.data.prices:[];
    const query=$('search').value.trim().toLowerCase();
    const matches=p=>text([p.material,p.name,p.unit,p.source_name,p.cost_transmission]).toLowerCase().includes(query);
    const prices=all.filter(matches);
    const history=(state.data?.price_history||[]).filter(matches).sort((a,b)=>text(b.date).localeCompare(text(a.date))||text(a.material).localeCompare(text(b.material)));
    const intro=el('div','section-intro');
    intro.append(el('strong','','有日期、有口径的材料参考价。'),document.createTextNode(' 金属报价、地区锂盐指标和实际采购成交价分别理解；下列影响路径为研判，价格变化需要与库存、供给阶段和合同定价方式共同观察。'));
    out.append(intro);
    if(!prices.length&&!history.length){out.append(empty('本快照未收录符合条件的报价','可调整搜索，或查看下方已核验的原料与供需事件。'));return;}
    const number=v=>typeof v==='number'&&isFinite(v)?v.toLocaleString('zh-CN',{maximumFractionDigits:4}):text(v);
    const wrap=el('div','data-table-wrap'),table=el('table','data-table price-table');
    const head=el('thead'),tr=el('tr');
    for(const title of ['品种 / 规格','参考价','变动 / 基期','实际观察日','产业链传导 · 研判','原始证据'])tr.append(el('th','',title));
    head.append(tr);table.append(head);const body=el('tbody');
    for(const price of prices){
      const row=el('tr'),material=el('td');material.append(el('strong','',price.material||price.name));
      if(price.market_basis)material.append(el('div','source-note',price.market_basis));
      row.append(material,el('td','number',number(price.value)+(price.unit?' '+price.unit:'')));
      const change=el('td'),valid=typeof price.change_pct==='number'&&isFinite(price.change_pct);
      change.append(el('div',valid?(price.change_pct>0?'number positive':'number negative'):'source-note',valid?(price.change_pct>0?'+':'')+number(price.change_pct)+'%':'未提供可比涨跌'));
      if(price.comparison_basis)change.append(el('div','source-note',price.comparison_basis));
      row.append(change,el('td','date',shortDate(price.date)));
      const transmission=el('td','price-transmission');
      if(price.cost_transmission)transmission.append(el('p','',price.cost_transmission));
      const story=(state.insights?.insights||[]).find(x=>x.id===price.related_insight_id);
      if(story){const button=el('button','event-story-link','查看价格传导分析');button.type='button';button.onclick=()=>openInsight(story);transmission.append(button);}
      if(price.chain_node_ids?.length){const button=el('button','event-story-link','定位产业链环节');button.type='button';button.onclick=()=>navigate('chain',price.chain_route||'all',price.chain_node_ids[0]);transmission.append(button);}
      row.append(transmission);
      const source=el('td','source-note');source.append(link(price.source_name||'原始数据',price.source_url));
      if(price.source_doc_date)source.append(el('div','','文件日期 '+shortDate(price.source_doc_date)));
      row.append(source);body.append(row);
    }
    if(prices.length){table.append(body);wrap.append(table);out.append(wrap);}
    if(history.length){
      const details=el('details','evidence-archive price-history');details.append(el('summary','',history.length+' 条已核验历史报价 · 保留原始日期和单位'));
      const scroll=el('div','data-table-wrap'),historical=el('table','data-table'),header=el('tr');
      for(const title of ['观察日','品种 / 规格','数值 / 单位','口径与出处'])header.append(el('th','',title));historical.append(header);
      for(const point of history){const r=el('tr');r.append(el('td','date',shortDate(point.date)),el('td','',point.material||point.name),el('td','number',number(point.value)+(point.unit?' '+point.unit:'')));const source=el('td','source-note');source.append(link(point.source_name||'原始数据',point.source_url));if(point.comparison_basis)source.append(el('div','',point.comparison_basis));r.append(source);historical.append(r);}
      scroll.append(historical);details.append(scroll);out.append(details);
    }
  }
  function renderSources(out){
    const catalog=catalogSources();const q=$('search').value.trim().toLowerCase();const category=$('category').value;const mode=$('source-mode').value;const tier=$('source-tier').value;
    const all=catalog.length?catalog:state.sources;const sources=all.filter(x=>(!q||text([x.name,x.publisher,x.country,x.category,x.free_scope,x.limitations,x.note]).toLowerCase().includes(q))&&(!category||sourceCategories(x).includes(category))&&(!mode||sourceMode(x)===mode)&&(!tier||sourceTier(x)===tier));
    $('result-count').textContent=`${sources.length} / ${all.length} ${catalog.length?'家机构':'个引用页面 / 文件'}`;
    const intro=el('div','section-intro');if(catalog.length){intro.append(el('strong','',`信源目录核验：${timeDate(state.catalog?.meta?.checked_at||state.catalog?.meta?.generated_at)}。`),document.createTextNode(' 同一机构的多个入口合并计数。目录收录、自动采集与实体登记监测分别管理；免费网页不等于免费完整数据库。历史情报快照不回溯此目录。'));}else{intro.textContent='机构目录未载入，以下回退展示本期引用页面与文件；页面数量不代表独立机构数。';}out.append(intro);
    const totals=el('div','source-totals');for(const [key,label]of [['auto','已配置自动采集'],['research','供检索与核验'],['registry','登记入口 · 待主体映射']]){const item=el('div','source-total');item.append(el('strong','',all.filter(x=>sourceMode(x)===key).length),el('span','',label));totals.append(item);}out.append(totals);
    const coverage=el('div','coverage-chips');for(const name of [...new Set(all.flatMap(sourceCategories))]){const count=all.filter(x=>sourceCategories(x).includes(name)).length;const button=el('button','coverage-chip'+(category===name?' active':''),`${name} ${count}`);button.onclick=()=>{$('category').value=category===name?'':name;renderContent();};coverage.append(button);}out.append(coverage);
    if(!catalog.length){out.append(el('div','section-intro','机构目录未载入：以下只列本期引用页面，不能把页面数量当成独立机构数。'));}if(!sources.length){out.append(empty('没有匹配的信源','可按国家、机构、产业领域和接入方式重新筛选。'));return;}
    const wrap=el('div','data-table-wrap'),table=el('table','data-table catalog-table'),head=el('thead'),tr=el('tr');for(const h of ['机构 / 国家','覆盖领域','接入方式与频率','访问与运行状态','免费内容与边界'])tr.append(el('th','',h));head.append(tr);table.append(head);const body=el('tbody');
    for(const source of sources){const row=el('tr'),name=el('td');name.append(link(source.name||source.publisher,source.url),el('div','source-country',text(source.country)||'全球'),el('div','source-type-badge',tierLabels[sourceTier(source)]));const domains=el('td','',sourceCategories(source).join(' / '));const method=el('td','source-note');const m=sourceMode(source);method.append(el('span','catalog-mode '+m,{auto:'自动采集',research:'检索核验',registry:'待主体映射'}[m]),el('div','',m==='auto'?`${source.collection_method==='html'?'公开新闻列表':'RSS / Atom'} · 每日约07:40`:(source.method==='api'?'公开接口 · 尚未接入定时采集':source.method==='registry'?'按登记主体查询，尚未建立实际子公司监测':'公开入口 · 定期研究核验')),el('small','',source.frequency||'按来源披露节奏更新'));if(source.interface_capability)method.append(el('small','',source.interface_capability));
      const status=el('td','source-note');const audit=feedAudit(source);if(m==='auto'&&audit){status.append(el('span','source-status '+normalizedStatus(audit.status),audit.status==='success'?'本次采集成功':'本次采集失败'),el('div','',timeDate(audit.checked_at)),el('small','',audit.error||`${audit.relevant_count??0} 条匹配线索`));}else{const st=source.access_status||source.status;status.append(el('span','source-status '+normalizedStatus(st),normalizedStatus(st)==='success'?'入口已核验':sourceLabel(st)),el('div','',shortDate(source.checked_at||source.last_checked)));}
      const note=el('td','source-note');note.append(el('div','',source.free_scope||source.note||'以机构实际公开范围为准'),el('small','source-limit',source.limitations||'尚未验证全量字段与历史覆盖。'));row.append(name,domains,method,status,note);body.append(row);
    }table.append(body);wrap.append(table);out.append(wrap);
    if(catalog.length&&state.sources.length){const detail=el('details','audit-details');detail.append(el('summary','',`本期情报引用证据：${state.sources.length} 个具体页面 / 文件`));const list=el('div','citation-list');for(const source of state.sources){const item=el('div');item.append(link(source.name||'原始来源',source.url),el('small','',source.note||''));list.append(item);}detail.append(list);out.append(detail);}
  }
  function renderFeeds(out){const feed=state.feed;if(!feed){$('result-count').textContent='尚未取得采集记录';out.append(empty('研究线索尚未发布','采集任务生成 feed-latest.json 后，标题、原始链接和运行记录会显示在这里。主情报快照仍可正常浏览。'));return;}
    const q=$('search').value.trim().toLowerCase();const selected=$('feed-source').value;const tier=$('source-tier').value;const items=(feed.items||[]).filter(i=>(!selected||i.source_id===selected)&&(!tier||sourceTier(i)===tier)&&text([i.title,i.source_name,i.categories,i.country]).toLowerCase().includes(q)).sort((a,b)=>(asDate(b.published_at)?.getTime()||0)-(asDate(a.published_at)?.getTime()||0));$('result-count').textContent=`${items.length} 条研究线索`;
    const intro=el('div','section-intro');intro.append(el('strong','',`最近采集：${timeDate(feed.meta?.generated_at)}。`),document.createTextNode(' 这里保留原始披露、专业研究、媒体和社区的发现线索；主界面只展示已核验结论。发布时间与首次发现时间分别保存，采集时间不代表新事件。来源访问失败时保留此前取得的线索，当前条目数不等于今日新增数。'));if(state.archive)intro.append(el('p','','此栏目显示独立的最新采集结果，不随所选情报快照回溯。'));out.append(intro);
    if(feed.meta?.baseline_source_count&&!feed.meta?.initial_baseline){out.append(el('div','section-intro',`本次有${feed.meta.baseline_source_count}个首次接入来源；其历史条目用于建立基线，不是今日新增事件。`));}if(feed.meta?.initial_baseline){const baseline=el('div','section-intro');baseline.textContent=feed.meta.baseline_note||'首次建库：当前所见条目包含历史公告，不计为当日新增事件。';out.append(baseline);}
    const sources=(feed.sources||[]).filter(x=>!selected||x.id===selected);if(sources.length){const auditBox=el('details','audit-details');auditBox.append(el('summary','',`采集运行记录：${sources.filter(x=>x.status==='success').length} / ${sources.length} 个来源成功，点击查看`));const wrap=el('div','data-table-wrap'),table=el('table','data-table'),head=el('thead'),tr=el('tr');for(const h of ['采集源','运行状态','本次相关条目','最近成功','说明'])tr.append(el('th','',h));head.append(tr);table.append(head);const body=el('tbody');for(const s of sources){const r=el('tr'),name=el('td');name.append(link(s.name,s.url));const status=el('td');status.append(el('span','source-status '+normalizedStatus(s.status),sourceLabel(s.status)));r.append(name,status,el('td','number',s.relevant_count??s.item_count??'—'),el('td','date',shortDate(s.last_success_at)),el('td','source-note',s.error||'仅抓取允许公开访问的内容'));body.append(r);}table.append(body);wrap.append(table);auditBox.append(wrap);out.append(auditBox);}
    if(!items.length){out.append(empty('本次没有匹配的线索','请结合来源运行状态判断：无新条目、无匹配与采集失败是不同情况。'));return;}
    for(const item of items.slice(0,state.feedLimit)){const row=el('article','feed-item');const meta=el('div','event-meta');meta.append(el('span','category-chip',item.source_name||'公开来源'),el('span','',shortDate(item.published_at)),el('span','evidence-chip other',tierLabels[sourceTier(item)]+' · 发现线索'));row.append(meta,link(item.title,item.url,'feed-title'));const dates=el('div','feed-dates',`首次发现 ${timeDate(item.first_seen_at)}${item.categories?.length?' · '+item.categories.join(' / '):''}${!item.published_at?' · 源站未标注发布日期':''}`);row.append(dates);out.append(row);}
    if(items.length>state.feedLimit){const more=el('button','more-button',`再显示60条 · 已显示${Math.min(state.feedLimit,items.length)} / ${items.length}`);more.onclick=()=>{state.feedLimit+=60;renderContent();};out.append(more);}
  }
  function openEvent(event){$('drawer').classList.remove('story-drawer');state.lastFocus=document.activeElement;const d=$('drawer-body');d.replaceChildren();const head=el('div','drawer-head'),meta=el('div','event-meta');meta.append(el('span','priority-label '+pri(event),pri(event)),el('span','category-chip',event.category),evidenceChip(event));const title=el('h2','',event.title);title.id='drawer-title';head.append(meta,title);d.append(head);
    const grid=el('dl','detail-grid');for(const [label,value] of [['涉及主体',text(event.entity)||'未标注'],['国家 / 区域',text(event.country)||'未标注'],['事件日期',shortDate(event.event_date)],['公开披露日期',shortDate(event.published_at)],['本次核验时间',timeDate(event.verified_at)],['证据类型',event.evidence_level||'未分级']]){const item=el('div');item.append(el('dt','',label),el('dd','',value));grid.append(item);}d.append(grid);
    const metrics=Array.isArray(event.metrics)?event.metrics:[];if(metrics.length){const group=el('div','drawer-metrics');for(const m of metrics){const item=el('div','drawer-metric');if(typeof m==='string')item.append(el('small','',m));else item.append(el('small','',m.label||m.name||'披露指标'),el('b','',text(m.value)+(m.unit?' '+m.unit:'')));group.append(item);}d.append(group);}
    for(const [title,value] of [['公开披露事实',event.summary],['产业与投资影响 · 研究判断',event.impact],['后续观察与决策信号',event.action]]){if(!value)continue;const section=el('section','drawer-section');section.append(el('h3','',title),el('p','',value));d.append(section);}
    const related=(state.insights?.insights||[]).find(x=>(x.related_event_ids||[]).includes(event.id));if(related){const b=el('button','intel-action','阅读关联分析：'+related.title);b.onclick=()=>openInsight(related);d.append(b);}
    const evidence=el('section','drawer-section');evidence.append(el('h3','','原始证据'),link(event.source_name||'打开原始来源',event.source_url));if(event.source_url)evidence.append(el('p','source-address',event.source_url));if(Array.isArray(event.additional_sources))for(const source of event.additional_sources)evidence.append(link(source.name||source.url,source.url));d.append(evidence,el('div','drawer-note','披露事实与研究判断分别呈现。该信息不代表被监控企业与任何特定投资组合存在持股关系；公司规划、目标与测试数据应按原文条件理解。'));
    $('drawer-backdrop').hidden=false;$('drawer').hidden=false;document.body.style.overflow='hidden';$('drawer').scrollTop=0;$('drawer-close').focus();
  }
  function openInsight(item){state.lastFocus=document.activeElement;const d=$('drawer-body');d.replaceChildren();const head=el('div','drawer-head');head.append(el('span','category-chip',(item.tags||[]).join(' / ')));const title=el('h2','',item.title);title.id='drawer-title';head.append(title,el('p','insight-thesis',item.thesis));d.append(head,window.IntelligenceUI.insightDetail(item,state.insights,(route,nodeId)=>{closeDrawer();navigate('chain',route,nodeId);}));$('drawer').classList.add('story-drawer');$('drawer-backdrop').hidden=false;$('drawer').hidden=false;document.body.style.overflow='hidden';$('drawer').scrollTop=0;$('drawer-close').focus();}
  function closeDrawer(){$('drawer').hidden=true;$('drawer-backdrop').hidden=true;document.body.style.overflow='';state.lastFocus?.focus?.();}
  function mapX(lon){return (lon+180)/360*840;}function mapY(lat){return (90-Math.max(-85,Math.min(85,lat)))/180*410;}
  function pathCoordinates(rings){return rings.map(r=>r.map(([x,y],i)=>`${i?'L':'M'}${mapX(x).toFixed(1)},${mapY(y).toFixed(1)}`).join('')+'Z').join('');}
  async function loadMap(){const g=$('graticule');for(let lon=-150;lon<=150;lon+=30)g.append(svg('path',{d:`M${mapX(lon)},25V385`}));for(let lat=-60;lat<=60;lat+=30)g.append(svg('path',{d:`M0,${mapY(lat)}H840`}));const data=await readJSON('assets/land.geojson',true);if(!data)return;for(const f of data.features||[]){const geo=f.geometry;if(geo.type==='Polygon')$('land').append(svg('path',{d:pathCoordinates(geo.coordinates)}));if(geo.type==='MultiPolygon')for(const rings of geo.coordinates)$('land').append(svg('path',{d:pathCoordinates(rings)}));}}
  function renderMarkers(){const group=$('markers');group.replaceChildren();let count=0;const positions=new Map();for(const e of state.events){const lat=Number(e.lat),lon=Number(e.lon);if(e.lat===null||e.lon===null||e.lat===undefined||e.lon===undefined||!isFinite(lat)||!isFinite(lon)||lat>90||lat<-90||lon>180||lon<-180)continue;count++;const key=`${lat.toFixed(2)},${lon.toFixed(2)}`,n=positions.get(key)||0;positions.set(key,n+1);const x=mapX(lon)+(n?Math.cos(n*2.4)*8:0),y=mapY(lat)+(n?Math.sin(n*2.4)*8:0);const color={P0:'#ed8178',P1:'#ddb979',P2:'#6bceca'}[pri(e)]||'#80b7ea';const point=svg('g',{class:'map-point',tabindex:0,role:'button','aria-label':`${e.title}，查看事件详情`});point.append(svg('circle',{cx:x,cy:y,r:13,fill:color,class:'halo'}),svg('circle',{cx:x,cy:y,r:4.2,fill:color,stroke:'#101b2a','stroke-width':1.5,class:'core'}));const title=svg('title');title.textContent=e.title;point.append(title);point.addEventListener('click',()=>openEvent(e));point.addEventListener('keydown',ev=>{if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();openEvent(e);}});group.append(point);} $('map-count').textContent=`${count} 条可定位事件`;$('map-note').textContent=`已定位 ${count} / ${state.events.length} 条；位置用于研究概览，不表示实际投资敞口`;}
  function exportCSV(){const events=currentEvents();const columns=[['披露日期','published_at'],['事件日期','event_date'],['领域','category'],['标题','title'],['主体','entity'],['区域','country'],['优先级','priority'],['证据','evidence_level'],['事实摘要','summary'],['产业与投资影响（研判）','impact'],['建议核实事项','action'],['来源','source_name'],['原始链接','source_url'],['核验时间','verified_at']];const quote=v=>{let s=text(v);if(/^[=+\-@\t\r]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};const rows=[columns.map(c=>quote(c[0])).join(','),...events.map(e=>columns.map(c=>quote(e[c[1]])).join(','))];const blob=new Blob(['\ufeff'+rows.join('\r\n')],{type:'text/csv;charset=utf-8;'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`strategic-intelligence-${shortDate(state.data?.meta?.as_of||new Date())}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  $('filters').addEventListener('submit',e=>e.preventDefault());for(const id of ['search','category','priority','evidence','period','source-mode','source-tier','feed-source'])$(id).addEventListener(id==='search'?'input':'change',()=>{state.feedLimit=60;renderContent();});
  $('reset').onclick=()=>{$('search').value='';$('category').value='';$('priority').value='';$('evidence').value='';$('period').value='all';$('source-mode').value='';$('source-tier').value='';$('feed-source').value='';state.feedLimit=60;window.IntelligenceUI?.resetOverview();renderContent();};
  $('refresh').onclick=()=>{const value=$('snapshot').value;load(value==='latest'?'data/latest.json':value,value!=='latest');};$('snapshot').onchange=()=>{const value=$('snapshot').value;load(value==='latest'?'data/latest.json':value,value!=='latest');};
  $('export').onclick=exportCSV;$('drawer-close').onclick=closeDrawer;$('drawer-backdrop').onclick=closeDrawer;
  document.addEventListener('keydown',e=>{if($('drawer').hidden)return;if(e.key==='Escape')closeDrawer();if(e.key==='Tab'){const nodes=$('drawer').querySelectorAll('button,a[href],[tabindex="0"]');const first=nodes[0],last=nodes[nodes.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}}});
  function readHash(){const [section,view]=location.hash.slice(1).split('/');if(!sections.some(s=>s.id===section))return false;state.section=section;if(section==='chain')window.IntelligenceUI?.setChainView?.(view);return true;}
  window.addEventListener('hashchange',()=>{if(!readHash())return;if(!$('drawer').hidden)closeDrawer();$('category').value='';$('search').value='';renderNav();if(state.data){renderContent();$('main').scrollIntoView({behavior:'smooth',block:'start'});}});
  readHash();renderNav();load();loadManifest();loadMap();
})();
