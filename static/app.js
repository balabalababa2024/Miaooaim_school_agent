// 页面加载自动拉取学生列表
window.onload = async function(){
    let sel = document.getElementById("studentSel");
    sel.innerHTML = "<option>加载中...</option>";
    try{
        let r = await fetch("/api/students");
        let j = await r.json();
        sel.innerHTML = "";
        j.data.forEach(s=>{
            let opt = document.createElement("option");
            opt.value = s.student_id;
            opt.innerText = s.name + "（" + s.student_id + "）";
            sel.appendChild(opt);
        });
    }catch(e){
        sel.innerHTML = "<option>加载失败</option>";
    }
};

// 标签切换
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

// 登录弹窗
document.getElementById('loginBtn').onclick=()=>{
    document.getElementById('authModal').classList.remove('hidden');
};
document.getElementById('authClose').onclick=()=>{
    document.getElementById('authModal').classList.add('hidden');
};

document.getElementById('tabLogin').onclick=()=>{
    document.getElementById('tabLogin').classList.add('active');
    document.getElementById('tabRegister').classList.remove('active');
    document.getElementById('regName').classList.add('hidden');
};
document.getElementById('tabRegister').onclick=()=>{
    document.getElementById('tabRegister').classList.add('active');
    document.getElementById('tabLogin').classList.remove('active');
    document.getElementById('regName').classList.remove('hidden');
};

// 登录提交
document.getElementById('authSubmit').onclick=async()=>{
    let uid=document.getElementById('auth_sid').value;
    let pwd=document.getElementById('auth_pwd').value;
    let r=await fetch('/api/login',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({student_id:uid,password:pwd})
    });
    let j=await r.json();
    if(j.code===0)location.reload();
    else alert(j.msg);
};

// 加载个人数据
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

// 加载历史
async function loadHistory(){
    let r=await fetch('/api/history');
    let j=await r.json();
    let list=document.getElementById('historyList');
    list.innerHTML='';
    j.data.forEach(h=>{
        list.innerHTML+=`<div class="history-item"><div>${h.request}</div><div>${h.create_time}</div></div>`;
    });
}

// 加载看板
async function loadDashboard(){
    let r=await fetch('/api/dashboard');
    let j=await r.json();
    document.getElementById('kpis').innerHTML=`
        <div class="kpi">平均分：${j.data.kpis.avgScore}</div>
        <div class="kpi">月消费：${j.data.kpis.monthConsume}</div>
        <div class="kpi">风险：${j.data.kpis.risk}</div>
    `;
}

// 生成规划
document.getElementById('runBtn').onclick=async()=>{
    let req=document.getElementById('reqInput').value;
    if(!req){alert('请输入需求');return;}
    let r=await fetch('/api/plan',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({request:req})
    });
    let j=await r.json();
    document.getElementById('finalPlan').innerHTML=`
        <div><strong>学业：</strong>${j.data.plan.study}</div>
        <div><strong>自习：</strong>${j.data.plan.env}</div>
        <div><strong>消费：</strong>${j.data.plan.consume}</div>
        <div><strong>合规：</strong>${j.data.plan.policy}</div>
    `;
    document.getElementById('resultArea').classList.remove('hidden');
};