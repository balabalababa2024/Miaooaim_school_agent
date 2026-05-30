// ---------------- 通用 ----------------
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);
const fmtH = h => `${String(Math.floor(h)).padStart(2,'0')}:${String(Math.round((h%1)*60)).padStart(2,'0')}`;
const AGENT_COLOR = {academic:'#ff7a7a', study_env:'#4fd1c5', logistics:'#ffd166', policy:'#a78bfa'};
let charts = {};
function destroy(id){ if(charts[id]){charts[id].destroy(); delete charts[id];} }

// ---------------- 全局用户态 ----------------
let ME = null;

// ---------------- Tab 切换 ----------------
$$('.tab').forEach(t=>{
  if(t.id==='policyBtn' || t.id==='loginBtn' || !t.dataset.tab) return;
  t.onclick=()=>{
    // 需登录的页面拦截
    if((t.dataset.tab==='mydata'||t.dataset.tab==='admin') && !ME){
      openAuth(); return;
    }
    if(t.dataset.tab==='admin' && (!ME || ME.role!=='admin')){ alert('需要管理员权限'); return; }
    $$('.tab').forEach(x=>x.classList.remove('active'));
    t.classList.add('active');
    $$('.page').forEach(p=>p.classList.remove('active'));
    $('#page-'+t.dataset.tab).classList.add('active');
    if(t.dataset.tab==='dashboard') loadDashboard();
    if(t.dataset.tab==='history') loadHistory();
    if(t.dataset.tab==='mydata') loadMyData();
    if(t.dataset.tab==='admin') loadUsers('');
  };
});

// 示例 chip
$$('.chip').forEach(c=> c.onclick=()=> $('#reqInput').value=c.dataset.ex);

// ---------------- 规划主流程 ----------------
$('#runBtn').onclick = async ()=>{
  const req = $('#reqInput').value.trim();
  if(!req){ alert('请输入规划需求'); return; }
  const btn=$('#runBtn'); btn.disabled=true; btn.innerHTML='<span class="spinner"></span>多智能体博弈中…';
  $('#flowEmpty').classList.add('hidden'); $('#flow').classList.remove('hidden'); $('#flow').innerHTML='';
  $('#resultArea').classList.add('hidden');
  try{
    const r = await fetch('/api/plan',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({student_id:$('#studentSel').value, request:req})});
    const j = await r.json();
    if(j.code!==0){ alert('错误: '+j.msg); return; }
    renderFlow(j.data); renderResult(j.data);
  }catch(e){ alert('请求失败: '+e); }
  finally{ btn.disabled=false; btn.innerHTML='🚀 启动多智能体博弈规划'; }
};

function renderFlow(d){
  const f=$('#flow'); let html='';
  if(d.reused){
    html += `<div class="reuse-banner">⚡ <b>命中动态经验库</b>（相似度 ${d.match_score}）—— 系统检索到历史成熟规划案例，
      <b>跳过 3 轮博弈直接复用</b>，体现「经验自进化、越用越快」。</div>`;
  }
  // CoT
  if(d.cot && d.cot.steps){
    html += `<div class="cot"><b>🧠 能力1 · CoT 思维链需求拆解</b>`;
    d.cot.steps.forEach(s=> html+=`<div class="step">${s}</div>`);
    html += `</div>`;
  }
  // 工具调用
  if(d.tool_calls && d.tool_calls.length){
    html += `<div style="margin-bottom:12px"><b style="font-size:13px">🔧 能力5 · 工具自主编排</b><div class="tools">`;
    d.tool_calls.forEach(t=> html+=`<span class="toolbadge ${t.ok?'ok':''}">${t.tool} · ${t.detail||''}</span>`);
    html += `</div></div>`;
  }
  // 博弈轮次
  if(d.rounds && d.rounds.length){
    html += `<b style="font-size:13px">⚔ 能力2 · 多智能体多轮博弈协商</b>`;
    d.rounds.forEach(rd=>{
      const s=rd.snapshot;
      html += `<div class="round"><div class="round-head"><span>第 ${rd.round} 轮</span>
        <span>冲突 ${rd.conflicts.length} · 违规 ${rd.violations.length}</span></div><div class="round-body">
        <div class="snap">
          <div class="pill"><span class="dot a"></span>学业 <b>${s.academic.selected}</b> ${s.academic.daily_hours}h/天 · 风险${s.academic.risk_score}</div>
          <div class="pill"><span class="dot b"></span>自习 <b>${s.study_env.floor}</b> ${fmtH(s.study_env.start)}-${fmtH(s.study_env.end)} · 环境${s.study_env.env_score}</div>
          <div class="pill"><span class="dot c"></span>餐饮上限 <b>${s.logistics.daily_meal_cap}</b>元/天</div>
        </div>`;
      rd.conflicts.forEach(c=> html+=`<div class="conf"><span class="tag">${c.type}</span>${c.detail}</div>`);
      rd.violations.forEach(v=> html+=`<div class="conf"><span class="tag">政策违规</span>${v}</div>`);
      (rd.actions||[]).forEach(a=> html+=`<div class="act">↳ ${a}</div>`);
      html += `</div></div>`;
    });
  }
  if(d.summary) html += `<div class="act" style="font-size:13px">📌 ${d.summary}</div>`;
  f.innerHTML = html;
}

function renderResult(d){
  const p=d.final_plan; if(!p) return;
  $('#resultArea').classList.remove('hidden');
  const st=p.study, sr=p.study_room, bg=p.budget, pol=p.policy;
  $('#finalPlan').innerHTML = `
    <div class="res-box"><h4>📚 学习计划</h4><ul>
      <li>方案：<b>${st.plan_name}</b></li>
      <li>每日学习：<b>${st.daily_hours}h</b></li>
      <li>风险分：<b>${st.risk_score}</b></li>
      <li>薄弱：${(st.weak_subjects||[]).join('、')||'无'}</li>
      ${st.blocks.map(b=>`<li>· ${b.subject} ${b.hours}h</li>`).join('')}
    </ul></div>
    <div class="res-box"><h4>🏫 自习选址</h4><ul>
      <li>地点：<b>${sr.floor}</b></li>
      <li>时段：<b>${fmtH(sr.start)}-${fmtH(sr.end)}</b></li>
      <li>环境分：<b>${sr.env_score}</b></li>
      <li>拥挤指数：${sr.crowd_index}</li>
    </ul></div>
    <div class="res-box"><h4>💰 预算管控</h4><ul>
      <li>月预算：<b>${bg.monthly_budget}</b>元</li>
      <li>每日餐饮上限：<b>${bg.daily_meal_cap}</b>元</li>
    </ul>
    <ul class="small">${bg.saving_plan.map(s=>`<li>· ${s}</li>`).join('')}</ul></div>
    <div class="res-box"><h4>🏛 合规约束</h4><ul class="small">
      <li>自习室关闭：${fmtH(pol.study_room_close)}</li>
      <li>宿舍熄灯：${fmtH(pol.lights_out)}</li>
      <li>奖学金门槛：${pol.scholarship_gpa}分</li>
      <li>水电建议上限：${pol.utility_cap}元</li>
    </ul></div>`;
  drawGantt(p.gantt); drawConsume(p.consumption_breakdown); drawEnv(p.env_curve);
}

// ---------------- 图表 ----------------
function drawGantt(g){
  destroy('gantt'); if(!g) return;
  const subjects=[...new Set(g.bars.map(b=>b.subject))];
  const palette=['#6c8bff','#9b6bff','#4fd1c5','#ffd166','#ff7a7a'];
  const datasets=subjects.map((subj,i)=>({
    label:subj,
    data:g.days.map(day=>{
      const b=g.bars.find(x=>x.day===day&&x.subject===subj);
      return b?[b.start,b.end]:null;
    }),
    backgroundColor:palette[i%palette.length], borderRadius:5, barPercentage:.7
  }));
  charts.gantt=new Chart($('#ganttChart'),{type:'bar',data:{labels:g.days,datasets},
    options:{indexAxis:'y',responsive:true,scales:{
      x:{min:7,max:23,ticks:{color:'#9aa3d4',callback:v=>v+':00'},grid:{color:'#2e3672'}},
      y:{stacked:true,ticks:{color:'#9aa3d4'},grid:{color:'#2e3672'}}},
      plugins:{legend:{labels:{color:'#e8ebff'}},title:{display:true,text:g.slot.floor+' 自习',color:'#9aa3d4'}}}});
}
function drawConsume(c){
  destroy('consume'); if(!c) return;
  charts.consume=new Chart($('#consumeChart'),{type:'doughnut',
    data:{labels:Object.keys(c),datasets:[{data:Object.values(c),
      backgroundColor:['#6c8bff','#ffd166']}]},
    options:{plugins:{legend:{labels:{color:'#e8ebff'}}}}});
}
function drawEnv(curve){
  destroy('env'); if(!curve||!curve.length) return;
  charts.env=new Chart($('#envChart'),{type:'line',
    data:{labels:curve.map(c=>c.hour+':00'),datasets:[{label:'舒适度',
      data:curve.map(c=>c.comfort),borderColor:'#4fd1c5',backgroundColor:'rgba(79,209,197,.15)',
      fill:true,tension:.35,pointRadius:2}]},
    options:{scales:{x:{ticks:{color:'#9aa3d4'},grid:{color:'#2e3672'}},
      y:{ticks:{color:'#9aa3d4'},grid:{color:'#2e3672'}}},
      plugins:{legend:{labels:{color:'#e8ebff'}}}}});
}

// ---------------- 看板 ----------------
async function loadDashboard(){
  const j=await (await fetch('/api/dashboard')).json(); const d=j.data;
  $('#kpis').innerHTML=`
    <div class="kpi"><div class="num">${d.risk_rank.length}</div><div class="lbl">在册学生</div></div>
    <div class="kpi"><div class="num">${d.static_rule_count}</div><div class="lbl">静态政策向量条目</div></div>
    <div class="kpi"><div class="num">${d.experience_count}</div><div class="lbl">动态经验案例（自进化）</div></div>
    <div class="kpi"><div class="num">${d.env_by_hour.length}</div><div class="lbl">自习时段监测点</div></div>`;
  destroy('riskRank');
  charts.riskRank=new Chart($('#riskRankChart'),{type:'bar',
    data:{labels:d.risk_rank.map(r=>r.name),datasets:[
      {label:'均分',data:d.risk_rank.map(r=>r.avg_score),backgroundColor:'#6c8bff',borderRadius:5},
      {label:'挂科数',data:d.risk_rank.map(r=>r.fails),backgroundColor:'#ff7a7a',borderRadius:5}]},
    options:{scales:{x:{ticks:{color:'#9aa3d4'},grid:{color:'#2e3672'}},
      y:{ticks:{color:'#9aa3d4'},grid:{color:'#2e3672'}}},plugins:{legend:{labels:{color:'#e8ebff'}}}}});
  destroy('envHour');
  charts.envHour=new Chart($('#envHourChart'),{type:'line',
    data:{labels:d.env_by_hour.map(e=>e.hour+':00'),datasets:[
      {label:'平均CO₂',data:d.env_by_hour.map(e=>e.avg_co2),borderColor:'#a78bfa',tension:.3,yAxisID:'y'},
      {label:'平均人流',data:d.env_by_hour.map(e=>e.avg_traffic),borderColor:'#ffd166',tension:.3,yAxisID:'y1'}]},
    options:{scales:{x:{ticks:{color:'#9aa3d4'},grid:{color:'#2e3672'}},
      y:{position:'left',ticks:{color:'#9aa3d4'},grid:{color:'#2e3672'}},
      y1:{position:'right',ticks:{color:'#9aa3d4'},grid:{drawOnChartArea:false}}},
      plugins:{legend:{labels:{color:'#e8ebff'}}}}});
  destroy('consumeRank');
  charts.consumeRank=new Chart($('#consumeRankChart'),{type:'bar',
    data:{labels:d.consume.map(c=>c.name),datasets:[{label:'月度消费(元)',
      data:d.consume.map(c=>c.total),backgroundColor:'#4fd1c5',borderRadius:5}]},
    options:{scales:{x:{ticks:{color:'#9aa3d4'},grid:{color:'#2e3672'}},
      y:{ticks:{color:'#9aa3d4'},grid:{color:'#2e3672'}}},plugins:{legend:{labels:{color:'#e8ebff'}}}}});
}

// ---------------- 存档 ----------------
async function loadHistory(){
  const j=await (await fetch('/api/history')).json();
  const list=$('#historyList');
  if(!j.data.length){ list.innerHTML='<div class="empty">暂无规划存档，去「智能规划」生成一条吧。</div>'; return; }
  list.innerHTML=j.data.map(h=>{
    const p=JSON.parse(h.final_plan||'{}'); const st=p.study||{}; const sr=p.study_room||{};
    return `<div class="hist">
      <div>${h.reused?'<span class="badge-reuse">复用</span> ':''}<b>${h.request}</b></div>
      <div class="meta"><span>学生 ${h.student_id} · ${st.plan_name||''} ${st.daily_hours||''}h · 自习 ${sr.floor||''}</span>
      <span>${h.created_at} · ${h.rounds}轮博弈</span></div></div>`;
  }).join('');
}

// ---------------- 政策问答 ----------------
$('#policyBtn').onclick=()=> $('#policyModal').classList.remove('hidden');
$('#policyClose').onclick=()=> $('#policyModal').classList.add('hidden');
$('#policyModal').onclick=e=>{ if(e.target.id==='policyModal') $('#policyModal').classList.add('hidden'); };
$('#policyAsk').onclick=async()=>{
  const q=$('#policyInput').value.trim(); if(!q) return;
  const j=await (await fetch('/api/policy_qa',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({question:q})})).json();
  const d=j.data;
  $('#policyAnswer').innerHTML=`<div class="ans">${d.answer}</div>`+
    (d.sources&&d.sources.length?`<div class="src">📎 来源：${d.sources.map(s=>`【${s.section}】(${s.score})`).join(' ')}</div>`:'');
};

// ---------------- 通用请求 ----------------
async function api(url, opts){
  const r = await fetch(url, opts);
  return r.json();
}
async function postJSON(url, body){
  return api(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});
}

// ---------------- 鉴权 / 登录态 ----------------
let authMode = 'login';
function openAuth(){ $('#authModal').classList.remove('hidden'); setAuthMode('login'); $('#authMsg').textContent=''; }
function closeAuth(){ $('#authModal').classList.add('hidden'); }
$('#loginBtn').onclick = openAuth;
$('#authClose').onclick = closeAuth;
$('#authModal').onclick = e=>{ if(e.target.id==='authModal') closeAuth(); };
$('#tabLogin').onclick = ()=> setAuthMode('login');
$('#tabRegister').onclick = ()=> setAuthMode('register');

function setAuthMode(m){
  authMode=m;
  $('#tabLogin').classList.toggle('active', m==='login');
  $('#tabRegister').classList.toggle('active', m==='register');
  $('#regName').classList.toggle('hidden', m!=='register');
  $('#authTitle').textContent = m==='login'?'🔐 登录':'📝 注册';
  $('#authSubmit').textContent = m==='login'?'登录':'注册';
  $('#authHint').textContent = m==='login'
    ? '默认管理员账号：admin / admin123。新注册学生需管理员审核通过后方可登录。'
    : '注册后状态为「待审核」，管理员通过后即可登录使用。';
  $('#authMsg').textContent='';
}

$('#authSubmit').onclick = async ()=>{
  const sid=$('#auth_sid').value.trim(), pwd=$('#auth_pwd').value;
  const msg=$('#authMsg');
  if(authMode==='register'){
    const name=$('#auth_name').value.trim();
    const j=await postJSON('/api/register',{student_id:sid,name,password:pwd});
    msg.className='auth-msg '+(j.code===0?'ok':'err'); msg.textContent=j.msg;
    if(j.code===0) setTimeout(()=>setAuthMode('login'),1200);
  }else{
    const j=await postJSON('/api/login',{student_id:sid,password:pwd});
    msg.className='auth-msg '+(j.code===0?'ok':'err'); msg.textContent=j.msg;
    if(j.code===0){ ME=j.data; applyAuth(); closeAuth(); }
  }
};

function applyAuth(){
  const area=$('#authArea');
  if(ME){
    area.innerHTML=`<span class="user-chip">${ME.name}
      <span class="role ${ME.role==='admin'?'admin':''}">${ME.role==='admin'?'管理员':'学生'}</span>
      <span class="logout" id="logoutBtn">退出</span></span>`;
    $('#logoutBtn').onclick=async()=>{ await postJSON('/api/logout'); ME=null; applyAuth();
      // 退回规划页
      $$('.tab').forEach(x=>x.classList.remove('active'));
      document.querySelector('.tab[data-tab="plan"]').classList.add('active');
      $$('.page').forEach(p=>p.classList.remove('active')); $('#page-plan').classList.add('active');
    };
    $('#adminTab').style.display = ME.role==='admin'?'':'none';
  }else{
    area.innerHTML='<button class="tab ghost" id="loginBtn">登录 / 注册</button>';
    $('#loginBtn').onclick=openAuth;
    $('#adminTab').style.display='none';
  }
}

// 启动时拉取当前登录态
(async()=>{ const j=await api('/api/me'); ME=j.data; applyAuth(); })();

// ---------------- 个人数据中心 ----------------
$$('.sub-tab[data-form]').forEach(b=> b.onclick=()=>{
  $$('.sub-tab[data-form]').forEach(x=>x.classList.remove('active')); b.classList.add('active');
  $$('.entry-form').forEach(f=>f.classList.remove('active'));
  $('#form-'+b.dataset.form).classList.add('active');
});

async function loadMyData(){
  if(!ME) return;
  const j=await api('/api/my_data'); const d=j.data||{grades:[],consumption:[]};
  $('#myDataEmpty').classList.add('hidden'); $('#myDataBody').classList.remove('hidden');
  $('#gradeTable').innerHTML = d.grades.length
    ? `<tr><th>科目</th><th>类型</th><th>成绩</th><th>出勤</th><th>挂科</th><th>难度</th><th>学分</th></tr>`+
      d.grades.map(g=>`<tr><td>${g.subject}</td><td>${g.exam_label||'-'}</td><td>${g.score}</td>
        <td>${g.attendance}</td><td>${g.failed?'<span class="badge fail">挂科</span>':'否'}</td>
        <td>${g.difficulty}</td><td>${g.credit}</td></tr>`).join('')
    : '<tr><td>暂无成绩记录，请在左侧录入。</td></tr>';
  $('#consumeTable').innerHTML = d.consumption.length
    ? `<tr><th>第几天</th><th>类别</th><th>项目</th><th>金额(元)</th></tr>`+
      d.consumption.map(c=>`<tr><td>${c.day}</td><td>${c.category}</td><td>${c.item}</td><td>${c.amount}</td></tr>`).join('')
    : '<tr><td>暂无消费记录，请在左侧录入。</td></tr>';
}

$('#saveGrade').onclick = async ()=>{
  const j=await postJSON('/api/data/grade',{
    subject:$('#g_subject').value.trim(), score:$('#g_score').value,
    attendance:$('#g_attendance').value, difficulty:$('#g_difficulty').value,
    credit:$('#g_credit').value, failed:$('#g_failed').checked});
  alert(j.msg); if(j.code===0){ $('#g_subject').value=''; loadMyData(); }
};
$('#saveConsume').onclick = async ()=>{
  const j=await postJSON('/api/data/consumption',{
    item:$('#c_item').value.trim(), category:$('#c_category').value,
    day:$('#c_day').value, amount:$('#c_amount').value});
  alert(j.msg); if(j.code===0){ $('#c_item').value=''; loadMyData(); }
};
$('#importCsv').onclick = async ()=>{
  const f=$('#i_file').files[0]; if(!f){ alert('请选择 CSV 文件'); return; }
  const fd=new FormData(); fd.append('file',f); fd.append('table',$('#i_table').value);
  const j=await api('/api/data/import_csv',{method:'POST',body:fd});
  alert(j.msg); if(j.code===0){ $('#i_file').value=''; loadMyData(); }
};

// ---------------- 管理员：用户审核 ----------------
$$('.sub-tab[data-ustatus]').forEach(b=> b.onclick=()=>{
  $$('.sub-tab[data-ustatus]').forEach(x=>x.classList.remove('active')); b.classList.add('active');
  loadUsers(b.dataset.ustatus);
});

async function loadUsers(status){
  if(!ME || ME.role!=='admin') return;
  const j=await api('/api/admin/users'+(status?('?status='+status):''));
  const rows=j.data||[];
  $('#userTable').innerHTML = rows.length
    ? `<tr><th>学号</th><th>姓名</th><th>角色</th><th>状态</th><th>注册时间</th><th>操作</th></tr>`+
      rows.map(u=>`<tr><td>${u.student_id}</td><td>${u.name}</td>
        <td>${u.role==='admin'?'管理员':'学生'}</td>
        <td><span class="badge ${u.status}">${({pending:'待审核',active:'已通过',rejected:'已驳回'})[u.status]||u.status}</span></td>
        <td>${u.created_at||'-'}</td>
        <td>${u.role==='admin'?'—':
          `<button class="btn-sm ok" onclick="reviewUser('${u.student_id}','active')">通过</button>
           <button class="btn-sm no" onclick="reviewUser('${u.student_id}','rejected')">驳回</button>`}</td></tr>`).join('')
    : '<tr><td>暂无用户。</td></tr>';
}

window.reviewUser = async (sid, status)=>{
  const j=await postJSON('/api/admin/review',{student_id:sid,status});
  if(j.code!==0) alert(j.msg);
  const active=document.querySelector('.sub-tab[data-ustatus].active');
  loadUsers(active?active.dataset.ustatus:'');
};
