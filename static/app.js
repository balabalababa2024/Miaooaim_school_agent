// ---------------- 通用工具 ----------------
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);
const fmtH = h => `${String(Math.floor(h)).padStart(2, '0')}:${String(Math.round((h % 1) * 60)).padStart(2, '0')}`;
let charts = {};
function destroy(id) { if (charts[id]) { charts[id].destroy(); delete charts[id]; } }

// ---------------- 用户状态 ----------------
let ME = null;

// ---------------- 标签页切换 ----------------
$$('.tab').forEach(t => {
  if (!t.dataset.tab) return;
  t.onclick = () => {
    if ((t.dataset.tab === 'mydata' || t.dataset.tab === 'admin') && !ME) { openAuth(); return; }
    $$('.tab').forEach(x => x.classList.remove('active'));
    $$('.page').forEach(p => p.classList.remove('active'));
    t.classList.add('active');
    $('#page-' + t.dataset.tab).classList.add('active');
    if (t.dataset.tab === 'dashboard') loadDashboard();
    if (t.dataset.tab === 'history') loadHistory();
    if (t.dataset.tab === 'mydata') loadMyData();
    if (t.dataset.tab === 'admin') loadUsers('');
  };
});

// 示例点击
$$('.chip').forEach(c => {
  c.onclick = () => { $('#reqInput').value = c.dataset.ex; };
});

// ---------------- 多智能体规划主流程 ----------------
$('#runBtn').onclick = async () => {
  const req = $('#reqInput').value.trim();
  if (!req) { alert('请输入规划需求'); return; }

  const btn = $('#runBtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 4 个智能体正在博弈协商…';

  $('#flowEmpty').classList.add('hidden');
  $('#flow').classList.remove('hidden');
  $('#flow').innerHTML = '';
  $('#resultArea').classList.add('hidden');

  try {
    const r = await fetch('/api/plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        student_id: $('#studentSel').value,
        request: req
      })
    });

    const j = await r.json();
    if (j.code !== 0) { alert('错误：' + j.msg); return; }
    renderAgentFlow(j.data);
    renderFinalPlan(j.data);
  } catch (e) {
    alert('请求失败：' + e.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '🚀 启动多智能体博弈规划';
  }
};

// 渲染 4 个 Agent 博弈过程（学业、自习、后勤、政策）
function renderAgentFlow(data) {
  const flow = $('#flow');
  let html = `
    <div class="round">
      <div class="round-head">✅ 多智能体协商完成</div>
      <div class="round-body">
        <div class="step">🧠 学业Agent：已评估风险、制定学习时长</div>
        <div class="step">🏫 自习Agent：已推荐最优自习室 & 时段</div>
        <div class="step">💰 后勤Agent：已完成预算与消费规划</div>
        <div class="step">🏛 政策Agent：已校验校规、熄灯、关闭时间</div>
      </div>
    </div>
  `;
  if (data.conflicts && data.conflicts.length) {
    html += `<div class="conflict-box"><b>冲突解决：</b>${data.conflicts.join('；')}</div>`;
  }
  flow.innerHTML = html;
}

// 渲染最终规划（完全适配你后端返回结构）
function renderFinalPlan(data) {
  $('#resultArea').classList.remove('hidden');
  $('#finalPlan').innerHTML = `
    <div class="res-box">
      <h4>📚 学习规划（学业Agent）</h4>
      <pre style="white-space:pre-wrap;padding:12px;background:#f4f7ff;border-radius:8px">
${data.academic ? JSON.stringify(data.academic, null, 2) : '无数据'}
      </pre>
    </div>
    <div class="res-box">
      <h4>🏫 自习规划（自习Agent）</h4>
      <pre style="white-space:pre-wrap;padding:12px;background:#f4f7ff;border-radius:8px">
${data.study_env ? JSON.stringify(data.study_env, null, 2) : '无数据'}
      </pre>
    </div>
    <div class="res-box">
      <h4>💰 预算规划（后勤Agent）</h4>
      <pre style="white-space:pre-wrap;padding:12px;background:#f4f7ff;border-radius:8px">
${data.logistics ? JSON.stringify(data.logistics, null, 2) : '无数据'}
      </pre>
    </div>
    <div class="res-box">
      <h4>🏛 政策约束（政策Agent）</h4>
      <pre style="white-space:pre-wrap;padding:12px;background:#f4f7ff;border-radius:8px">
${data.policy ? JSON.stringify(data.policy, null, 2) : '无数据'}
      </pre>
    </div>
    <div class="res-box" style="grid-column:1/-1;margin-top:10px">
      <h4>📝 全局最终规划</h4>
      <pre style="white-space:pre-wrap;padding:14px;background:#f8f9fa;border-radius:8px">
${data.final_plan || '未生成'}
      </pre>
    </div>
  `;
}

// ---------------- 数据看板 ----------------
async function loadDashboard() {
  const j = await (await fetch('/api/dashboard')).json();
  const d = j.data || {};
  $('#kpis').innerHTML = `
    <div class="kpi"><div class="num">${d.static_rule_count || 0}</div><div class="lbl">政策条目</div></div>
    <div class="kpi"><div class="num">${d.experience_count || 0}</div><div class="lbl">经验案例</div></div>
  `;
}

// ---------------- 规划存档 ----------------
async function loadHistory() {
  const r = await fetch('/api/history');
  const j = await r.json();
  const list = j.data || [];
  $('#historyList').innerHTML = list.map(h => `
    <div class="hist">
      <div><b>需求：</b>${h.request}</div>
      <div><b>时间：</b>${h.create_time || h.created_at}</div>
      <div><b>冲突：</b>${h.conflict_log || '无'}</div>
    </div>
  `).join('');
}

// ---------------- 政策问答 ----------------
$('#policyBtn').onclick = () => { $('#policyModal').classList.remove('hidden'); };
$('#policyClose').onclick = () => { $('#policyModal').classList.add('hidden'); };
$('#policyAsk').onclick = async () => {
  const q = $('#policyInput').value.trim();
  if (!q) return;
  const r = await fetch('/api/policy_qa', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question: q })
  });
  const j = await r.json();
  $('#policyAnswer').innerHTML = `<div class="ans">${j.data?.answer || '暂无答案'}</div>`;
};

// ---------------- 登录 / 注册 ----------------
function openAuth() { $('#authModal').classList.remove('hidden'); }
function closeAuth() { $('#authModal').classList.add('hidden'); }
$('#loginBtn').onclick = openAuth;
$('#authClose').onclick = closeAuth;
$('#tabLogin').onclick = () => {
  $('#authTitle').innerText = '登录';
  $('#regName').classList.add('hidden');
};
$('#tabRegister').onclick = () => {
  $('#authTitle').innerText = '注册';
  $('#regName').classList.remove('hidden');
};

// 登录提交
$('#authSubmit').onclick = async () => {
  const sid = $('#auth_sid').value.trim();
  const pwd = $('#auth_pwd').value.trim();
  const name = $('#auth_name').value.trim();
  const isReg = $('#tabRegister').classList.contains('active');

  const url = isReg ? '/api/register' : '/api/login';
  const body = isReg ? { student_id: sid, name, password: pwd } : { student_id: sid, password: pwd };

  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  const j = await r.json();
  $('#authMsg').innerText = j.msg;
  if (j.code === 0) {
    setTimeout(() => {
      closeAuth();
      refreshMe();
    }, 1000);
  }
};

// 刷新用户信息
async function refreshMe() {
  const r = await fetch('/api/me');
  const j = await r.json();
  ME = j.data;
  if (ME) {
    $('#authArea').innerHTML = `<span>${ME.name}</span>`;
    $('#adminTab').style.display = ME.role === 'admin' ? 'inline-block' : 'none';
  }
}

// ---------------- 个人数据 ----------------
async function loadMyData() {
  const r = await fetch('/api/my_data');
  const j = await r.json();
  $('#myDataEmpty').classList.add('hidden');
  $('#myDataBody').classList.remove('hidden');
}

// ---------------- 管理员 ----------------
async function loadUsers(status) {
  const r = await fetch('/api/admin/users?status=' + status);
  const j = await r.json();
}

// 初始化
window.onload = refreshMe;