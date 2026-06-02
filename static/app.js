// ==================== 当前登录态 ====================
let currentUser = null;

// ==================== 页面加载 ====================
window.onload = async function(){
    // 检查登录状态
    try{
        let mr = await fetch("/api/me");
        let mj = await mr.json();
        if(mj.code === 0){
            currentUser = mj.data;
            renderUserArea(currentUser);
        }
    }catch(e){}

    // 加载学生列表
    let sel = document.getElementById("studentSel");
    sel.innerHTML = "<option>加载中...</option>";
    try{
        let r = await fetch("/api/students");
        let j = await r.json();
        sel.innerHTML = "";
        if(j.data && j.data.length > 0){
            j.data.forEach(s=>{
                let opt = document.createElement("option");
                opt.value = s.student_id;
                opt.innerText = s.name + "（" + s.student_id + "）";
                sel.appendChild(opt);
            });
            // 自动选中当前登录用户
            if(currentUser){
                let match = Array.from(sel.options).find(o=>o.value===currentUser.student_id);
                if(match) sel.value = currentUser.student_id;
            }
        } else {
            sel.innerHTML = "<option value=''>暂无学生数据</option>";
        }
    }catch(e){
        sel.innerHTML = "<option>加载失败</option>";
    }
};

// ==================== 标签切换 ====================
document.querySelectorAll('.tab').forEach(t=>{
    t.onclick=function(){
        document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
        this.classList.add('active');
        let p = this.dataset.tab;
        document.querySelectorAll('.page').forEach(x=>x.classList.remove('active'));
        document.getElementById('page-'+p).classList.add('active');
        if(p==='mydata')loadMyData();
        if(p==='history')loadHistory();
        if(p==='dashboard')loadDashboard();
    };
});

// ==================== 示例点击 ====================
document.querySelectorAll('.chip[data-ex]').forEach(chip=>{
    chip.onclick=()=>{
        document.getElementById('reqInput').value = chip.dataset.ex;
    };
});

// ==================== 登录/注册弹窗 ====================
let authMode = 'login'; // 'login' or 'register'

document.getElementById('loginBtn').onclick=()=>{
    document.getElementById('authModal').classList.remove('hidden');
    switchAuthTab('login');
};
document.getElementById('authClose').onclick=()=>{
    document.getElementById('authModal').classList.add('hidden');
    clearAuthMsg();
};

document.getElementById('tabLogin').onclick=()=>switchAuthTab('login');
document.getElementById('tabRegister').onclick=()=>switchAuthTab('register');

function switchAuthTab(mode){
    authMode = mode;
    document.getElementById('tabLogin').classList.toggle('active', mode==='login');
    document.getElementById('tabRegister').classList.toggle('active', mode==='register');
    document.getElementById('regName').classList.toggle('hidden', mode==='login');
    document.getElementById('authSubmit').textContent = mode==='login' ? '登录' : '注册';
    document.getElementById('authTitle').textContent = mode==='login' ? '🔐 登录' : '📝 注册';
    document.getElementById('authHint').textContent = mode==='login'
        ? '默认测试账号：stu001 / 123456'
        : '注册后即可登录使用，密码至少6位';
    clearAuthMsg();
}

function clearAuthMsg(){
    let msg = document.getElementById('authMsg');
    msg.textContent = '';
    msg.className = 'auth-msg';
}

function showAuthMsg(text, ok){
    let msg = document.getElementById('authMsg');
    msg.textContent = text;
    msg.className = 'auth-msg ' + (ok ? 'ok' : 'err');
}

document.getElementById('authSubmit').onclick=async()=>{
    let uid = document.getElementById('auth_sid').value.trim();
    let pwd = document.getElementById('auth_pwd').value.trim();
    if(!uid || !pwd){
        showAuthMsg('请填写学号和密码', false);
        return;
    }

    let url, body;
    if(authMode === 'register'){
        let name = document.getElementById('auth_name').value.trim();
        if(!name){
            showAuthMsg('请填写姓名', false);
            return;
        }
        if(pwd.length < 6){
            showAuthMsg('密码至少需要6位', false);
            return;
        }
        url = '/api/register';
        body = {student_id: uid, name: name, password: pwd};
    } else {
        url = '/api/login';
        body = {student_id: uid, password: pwd};
    }

    let btn = document.getElementById('authSubmit');
    btn.disabled = true;
    btn.textContent = authMode==='login' ? '登录中…' : '注册中…';

    try{
        let r = await fetch(url, {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify(body)
        });
        let j = await r.json();
        if(j.code === 0){
            if(authMode === 'register'){
                showAuthMsg('注册成功！请切换到登录', true);
                switchAuthTab('login');
                document.getElementById('auth_sid').value = uid;
            } else {
                // 登录成功
                document.getElementById('authModal').classList.add('hidden');
                location.reload();
            }
        } else {
            showAuthMsg(j.msg || '操作失败', false);
        }
    }catch(e){
        showAuthMsg('网络请求失败', false);
    }finally{
        btn.disabled = false;
        btn.textContent = authMode==='login' ? '登录' : '注册';
    }
};

// ==================== 渲染用户态顶栏 ====================
function renderUserArea(user){
    let area = document.getElementById('authArea');
    area.innerHTML = `
        <span class="user-chip">
            <span>👤 ${user.name}</span>
            <span class="role">${user.role==='admin'?'管理员':'学生'}</span>
        </span>
        <button class="tab ghost" id="logoutBtn">退出</button>
    `;
    document.getElementById('logoutBtn').onclick = async()=>{
        await fetch('/api/logout', {method:'POST'});
        location.reload();
    };
}

// ==================== Agent 配置 ====================
const AGENT_META = {
    academic:  {icon: "🔴", label: "学业规划Agent", color: "var(--a)"},
    study_env: {icon: "🟢", label: "自习环境Agent", color: "var(--b)"},
    logistics: {icon: "🟡", label: "后勤消费Agent", color: "var(--c)"},
    policy:    {icon: "🟣", label: "政策合规Agent", color: "var(--d)"}
};

const SEVERITY_COLORS = {
    HIGH: "var(--a)",
    MID:  "var(--warn)",
    LOW:  "var(--mut)"
};

// ==================== 生成规划（核心） ====================
document.getElementById('runBtn').onclick=async()=>{
    let req=document.getElementById('reqInput').value;
    if(!req){alert('请输入需求');return;}

    let btn = document.getElementById('runBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>多智能体协商中…';

    // 清空旧结果
    document.getElementById('flow').innerHTML = '';
    document.getElementById('flowEmpty').classList.add('hidden');
    document.getElementById('flow').classList.remove('hidden');
    document.getElementById('resultArea').classList.add('hidden');

    try{
        let r=await fetch('/api/plan',{
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({request:req})
        });
        let j=await r.json();

        if(j.code!==0){
            alert(j.msg || '规划生成失败');
            return;
        }

        renderNegotiation(j.data);
    }catch(e){
        alert('请求失败: ' + e.message);
    }finally{
        btn.disabled = false;
        btn.innerHTML = '🚀 启动多智能体博弈规划';
    }
};

// ==================== 渲染协商全过程 ====================
function renderNegotiation(data){
    let flow = document.getElementById('flow');
    flow.innerHTML = '';

    // 1. CoT 思维链
    if(data.cot){
        flow.innerHTML += renderCoT(data.cot);
    }

    // 2. 每轮协商详情
    if(data.rounds && data.rounds.length > 0){
        data.rounds.forEach(rd=>{
            flow.innerHTML += renderRound(rd);
        });
    }

    // 3. 共识状态横幅
    flow.innerHTML += renderConsensusBanner(data.consensus, data.total_rounds);

    // 4. 最终方案
    if(data.plan){
        renderFinalPlan(data.plan);
    }

    // 滚动到底部
    flow.scrollTop = flow.scrollHeight;
}

// ==================== CoT 渲染 ====================
function renderCoT(cot){
    let steps = [];
    if(cot.budget) steps.push(`💰 月度预算：<b>${cot.budget}元</b>`);
    if(cot.daily_hours) steps.push(`📚 每日学习：<b>${cot.daily_hours}小时</b>`);
    if(cot.want_env !== undefined) steps.push(`🏫 自习环境：<b>${cot.want_env ? '需要好的环境' : '无特殊要求'}</b>`);
    if(cot.care_policy !== undefined) steps.push(`📋 合规关注：<b>${cot.care_policy ? '严格遵守校规' : '灵活处理'}</b>`);
    if(cot.intensity) steps.push(`⚡ 学习强度：<b>${cot.intensity}</b>`);
    if(cot.subjects && cot.subjects.length > 0) steps.push(`🎯 重点科目：<b>${cot.subjects.join('、')}</b>`);

    return `
    <div class="cot">
        <div class="step" style="font-weight:700;margin-bottom:8px">🧠 CoT 需求拆解</div>
        ${steps.map(s=>`<div class="step">${s}</div>`).join('')}
    </div>`;
}

// ==================== 单轮渲染 ====================
function renderRound(rd){
    let roundLabel = rd.stage === '共识达成' ? '✅ 共识达成' : `🔄 第${rd.round}轮：${rd.stage}`;
    let hasConflicts = rd.conflicts && rd.conflicts.length > 0;

    let html = `<div class="round">`;
    html += `<div class="round-head">
        <span>${roundLabel}</span>
        <span style="font-size:12px;color:var(--mut)">
            ${hasConflicts ? '⚠️ 发现'+rd.conflicts.length+'个冲突' : '✅ 无冲突'}
        </span>
    </div>`;
    html += `<div class="round-body">`;

    // 各 Agent 提案快照
    if(rd.proposals){
        html += `<div class="snap">`;
        for(let [agent, info] of Object.entries(rd.proposals)){
            let meta = AGENT_META[agent] || {icon:"⚪", label:agent, color:"var(--mut)"};
            let detail = formatProposalDetail(agent, info);
            html += `<div class="pill" style="border-left:3px solid ${meta.color}">
                <span>${meta.icon} <b>${meta.label}</b></span><br>
                <span style="font-size:11px;color:var(--mut)">${detail}</span>
            </div>`;
        }
        html += `</div>`;
    }

    // 冲突列表
    if(hasConflicts){
        rd.conflicts.forEach(c=>{
            let sevColor = SEVERITY_COLORS[c.severity] || 'var(--mut)';
            let agents = (c.between||[]).map(a=>(AGENT_META[a]||{}).label||a).join(' ↔ ');
            html += `<div class="conf">
                <span class="tag" style="background:${sevColor}">${c.severity}</span>
                <b>${c.type}</b>：${c.description}
                <div style="margin-top:4px;font-size:11px;color:var(--mut)">涉及：${agents}</div>
            </div>`;
        });
    }

    // 协商调整
    if(rd.resolutions && rd.resolutions.length > 0){
        rd.resolutions.forEach(res=>{
            let agentLabel = (AGENT_META[res.agent]||{}).label || res.agent;
            html += `<div class="act">
                ✅ <b>${agentLabel}</b>：${res.action}
            </div>`;
        });
    }

    // Agent 自述理由
    if(rd.agent_rationale){
        for(let [agent, reason] of Object.entries(rd.agent_rationale)){
            let meta = AGENT_META[agent] || {icon:"⚪", label:agent};
            html += `<div style="font-size:11.5px;color:var(--mut);margin:4px 0;padding-left:8px;border-left:2px solid var(--line)">
                ${meta.icon} ${meta.label}：${reason}
            </div>`;
        }
    }

    html += `</div></div>`;
    return html;
}

// ==================== 提案详情格式化 ====================
function formatProposalDetail(agent, info){
    switch(agent){
        case 'academic':
            return `每日${info.daily_hours||0}h | 风险${info.risk_score||0} | ${(info.weak_subjects||[]).join('/')||'无挂科'}`;
        case 'study_env':
            let t = info.start && info.end ? `${fmtTime(info.start)}-${fmtTime(info.end)}` : '';
            return `${info.floor||''} ${t} | 环境${info.env_score||0}`;
        case 'logistics':
            return `预算${info.monthly_budget||0} | 已花${info.total_spent||0} | 日均餐${info.daily_meal_cap||0}`;
        case 'policy':
            return (info.summary||'已加载政策').substring(0,60);
        default:
            return (info.summary||'').substring(0,60);
    }
}

// ==================== 共识横幅 ====================
function renderConsensusBanner(consensus, totalRounds){
    if(consensus){
        return `<div class="reuse-banner" style="border-color:var(--ok);background:rgba(95,224,160,.1)">
            🎉 <b>多智能体协商达成共识</b> — 共经过 ${totalRounds} 轮博弈，各Agent方案已收敛
        </div>`;
    } else {
        return `<div class="reuse-banner" style="border-color:var(--warn)">
            ⚠️ <b>协商未完全达成共识</b> — 经过 ${totalRounds} 轮博弈，以下为最大均衡方案
        </div>`;
    }
}

// ==================== 最终方案渲染 ====================
function renderFinalPlan(plan){
    document.getElementById('finalPlan').innerHTML = `
        <div class="res-box">
            <h4>📚 学业规划</h4>
            <div style="font-size:12.5px;line-height:1.7;white-space:pre-wrap">${plan.study||'—'}</div>
        </div>
        <div class="res-box">
            <h4>🏫 自习计划</h4>
            <div style="font-size:12.5px;line-height:1.7;white-space:pre-wrap">${plan.env||'—'}</div>
        </div>
        <div class="res-box">
            <h4>💰 消费预算</h4>
            <div style="font-size:12.5px;line-height:1.7;white-space:pre-wrap">${plan.consume||'—'}</div>
        </div>
        <div class="res-box">
            <h4>📋 合规提醒</h4>
            <div style="font-size:12.5px;line-height:1.7;white-space:pre-wrap">${plan.policy||'—'}</div>
        </div>
    `;

    // 如果有综合方案，显示在下方
    if(plan.summary){
        document.getElementById('finalPlan').innerHTML += `
        <div class="res-box" style="grid-column:1/-1">
            <h4>🎯 综合方案（多智能体博弈结果）</h4>
            <div style="font-size:13px;line-height:1.8;white-space:pre-wrap">${plan.summary}</div>
        </div>`;
    }

    document.getElementById('resultArea').classList.remove('hidden');

    // 渲染图表
    renderCharts(plan);
}

// ==================== 图表渲染 ====================
function renderCharts(plan){
    renderGanttChart();
    renderConsumeChart();
    renderEnvChart();
}

function renderGanttChart(){
    let ctx = document.getElementById('ganttChart');
    if(!ctx) return;
    if(ctx._chart) ctx._chart.destroy();

    let days = ['周一','周二','周三','周四','周五','周六','周日'];
    let studyData = [6,6,6,6,6,4,4];
    let selfStudyData = [3,3,3,3,3,2,2];

    ctx._chart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: days,
            datasets: [
                {label:'课程学习(h)', data:studyData, backgroundColor:'rgba(108,139,255,.7)'},
                {label:'自习(h)', data:selfStudyData, backgroundColor:'rgba(79,209,197,.7)'}
            ]
        },
        options: {
            responsive: true,
            scales: {
                x: {stacked: true, ticks:{color:'#9aa3d4'}, grid:{color:'#2e3672'}},
                y: {stacked: true, ticks:{color:'#9aa3d4'}, grid:{color:'#2e3672'}, max:12}
            },
            plugins: {legend:{labels:{color:'#e8ebff'}}}
        }
    });
}

function renderConsumeChart(){
    let ctx = document.getElementById('consumeChart');
    if(!ctx) return;
    if(ctx._chart) ctx._chart.destroy();

    ctx._chart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['食堂','超市','水电','其他'],
            datasets: [{
                data: [450, 200, 80, 70],
                backgroundColor: ['#6c8bff','#4fd1c5','#ffd166','#a78bfa']
            }]
        },
        options: {
            responsive: true,
            plugins: {legend:{labels:{color:'#e8ebff'}}}
        }
    });
}

function renderEnvChart(){
    let ctx = document.getElementById('envChart');
    if(!ctx) return;
    if(ctx._chart) ctx._chart.destroy();

    let hours = ['8:00','10:00','12:00','14:00','16:00','18:00','20:00','22:00'];
    let co2 = [420,450,480,440,460,490,510,430];
    let traffic = [20,35,45,30,50,60,40,15];

    ctx._chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: hours,
            datasets: [
                {label:'CO₂(ppm)', data:co2, borderColor:'#ff7a7a', fill:false, tension:0.4},
                {label:'人流量', data:traffic, borderColor:'#4fd1c5', fill:false, tension:0.4, yAxisID:'y1'}
            ]
        },
        options: {
            responsive: true,
            scales: {
                x: {ticks:{color:'#9aa3d4'}, grid:{color:'#2e3672'}},
                y: {ticks:{color:'#9aa3d4'}, grid:{color:'#2e3672'}, position:'left'},
                y1: {ticks:{color:'#9aa3d4'}, grid:{display:false}, position:'right'}
            },
            plugins: {legend:{labels:{color:'#e8ebff'}}}
        }
    });
}

// ==================== 工具函数 ====================
function fmtTime(h){
    let hours = Math.floor(h);
    let mins = Math.round((h - hours) * 60);
    return `${String(hours).padStart(2,'0')}:${String(mins).padStart(2,'0')}`;
}

// ==================== 个人数据 ====================
async function loadMyData(){
    let r=await fetch('/api/my_data');
    let j=await r.json();
    if(j.code!==0){alert('请登录');return;}
    document.getElementById('myDataEmpty').classList.add('hidden');
    document.getElementById('myDataBody').classList.remove('hidden');
    let gt=document.getElementById('gradeTable');
    gt.innerHTML='<tr><th>科目</th><th>分数</th></tr>';
    j.data.grades.forEach(g=>{
        gt.innerHTML+=`<tr><td>${g.subject}</td><td>${g.score}</td></tr>`;
    });
    let ct=document.getElementById('consumeTable');
    ct.innerHTML='<tr><th>类别</th><th>金额</th></tr>';
    j.data.consumption.forEach(c=>{
        ct.innerHTML+=`<tr><td>${c.category}</td><td>${c.amount}</td></tr>`;
    });
}

// ==================== 历史 ====================
async function loadHistory(){
    let r=await fetch('/api/history');
    let j=await r.json();
    let list=document.getElementById('historyList');
    list.innerHTML='';
    if(!j.data || j.data.length === 0){
        list.innerHTML = '<div class="empty">暂无历史规划记录</div>';
        return;
    }
    j.data.forEach(h=>{
        list.innerHTML+=`<div class="hist">
            <div>${h.request}</div>
            <div class="meta"><span>${h.create_time}</span></div>
        </div>`;
    });
}

// ==================== 看板 ====================
async function loadDashboard(){
    let r=await fetch('/api/dashboard');
    let j=await r.json();
    document.getElementById('kpis').innerHTML=`
        <div class="kpi"><div class="num">${j.data.kpis.avgScore}</div><div class="lbl">平均分</div></div>
        <div class="kpi"><div class="num">${j.data.kpis.monthConsume}</div><div class="lbl">月消费(元)</div></div>
        <div class="kpi"><div class="num">${j.data.kpis.risk}</div><div class="lbl">风险等级</div></div>
        <div class="kpi"><div class="num">—</div><div class="lbl">合规评分</div></div>
    `;
}
