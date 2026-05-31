"""
校园多智能体综合生活学业协同规划平台 —— Flask 入口
=================================================
运行方式（VSCode 终端 / 直接运行本文件）：
    pip install -r requirements.txt
    python app.py
然后浏览器打开 http://127.0.0.1:5000
"""
import functools
import os
import tempfile

from flask import Flask, jsonify, render_template, request, session

from core.database import (
    init_db, get_conn, get_experience_store, get_static_rule_store,
    create_user, authenticate, get_user, list_users, set_user_status,
    insert_grade, insert_consumption, import_csv_for_student, my_data,
)

# 修复：正确导入母 Agent
from core.agents.master import MasterAgent
supervisor = MasterAgent()

app = Flask(__name__)
app.secret_key = os.environ.get("CAMPUS_SECRET", "campus-agent-dev-secret-key")

# 修复：删掉重复定义 + 错误的 Supervisor
init_db()

# 学生列表（供前端下拉）
STUDENTS = [
    {"id": "2021001", "name": "张明"}, {"id": "2021002", "name": "李雪"},
    {"id": "2021003", "name": "王浩"}, {"id": "2021004", "name": "刘婷"},
    {"id": "2021005", "name": "陈强"},
]


@app.route("/")
def index():
    return render_template("index.html", students=STUDENTS)


# =============================================================== 鉴权辅助 ====
def current_user():
    sid = session.get("uid")
    return get_user(sid) if sid else None


def login_required(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            return jsonify({"code": 401, "msg": "请先登录", "data": None})
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        u = current_user()
        if not u:
            return jsonify({"code": 401, "msg": "请先登录", "data": None})
        if u["role"] != "admin":
            return jsonify({"code": 403, "msg": "需要管理员权限", "data": None})
        return fn(*args, **kwargs)
    return wrapper


def _pub(user):
    """脱敏后的用户信息（不含密码哈希/盐）。"""
    return {k: user[k] for k in ("student_id", "name", "role", "status")}


# =============================================================== 用户管理 ====
@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json(force=True)
    sid = (data.get("student_id") or "").strip()
    name = (data.get("name") or "").strip()
    pwd = data.get("password") or ""
    if not sid or not name or not pwd:
        return jsonify({"code": 400, "msg": "学号、姓名、密码均不能为空", "data": None})
    if len(pwd) < 6:
        return jsonify({"code": 400, "msg": "密码至少 6 位", "data": None})
    if not create_user(sid, name, pwd):
        return jsonify({"code": 409, "msg": "该学号已注册", "data": None})
    return jsonify({"code": 0, "msg": "注册成功，请等待管理员审核后登录", "data": None})


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(force=True)
    sid = (data.get("student_id") or "").strip()
    pwd = data.get("password") or ""
    user, err = authenticate(sid, pwd)
    if err:
        return jsonify({"code": 401, "msg": err, "data": None})
    session["uid"] = user["student_id"]
    return jsonify({"code": 0, "msg": "登录成功", "data": _pub(user)})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.pop("uid", None)
    return jsonify({"code": 0, "msg": "已退出登录", "data": None})


@app.route("/api/me")
def api_me():
    u = current_user()
    return jsonify({"code": 0, "msg": "ok", "data": _pub(u) if u else None})


@app.route("/api/admin/users")
@admin_required
def api_admin_users():
    status = request.args.get("status") or None
    return jsonify({"code": 0, "msg": "ok", "data": list_users(status)})


@app.route("/api/admin/review", methods=["POST"])
@admin_required
def api_admin_review():
    data = request.get_json(force=True)
    sid = (data.get("student_id") or "").strip()
    status = data.get("status")
    if status not in ("active", "rejected"):
        return jsonify({"code": 400, "msg": "status 仅支持 active / rejected", "data": None})
    target = get_user(sid)
    if not target:
        return jsonify({"code": 404, "msg": "用户不存在", "data": None})
    if target["role"] == "admin":
        return jsonify({"code": 400, "msg": "不能修改管理员账号状态", "data": None})
    set_user_status(sid, status)
    return jsonify({"code": 0, "msg": f"已{'通过' if status == 'active' else '驳回'}", "data": None})


# =============================================================== 数据中心 ====
@app.route("/api/my_data")
@login_required
def api_my_data():
    sid = current_user()["student_id"]
    return jsonify({"code": 0, "msg": "ok", "data": my_data(sid)})


@app.route("/api/data/grade", methods=["POST"])
@login_required
def api_add_grade():
    u = current_user()
    d = request.get_json(force=True)
    subject = (d.get("subject") or "").strip()
    if not subject:
        return jsonify({"code": 400, "msg": "请填写科目", "data": None})
    try:
        insert_grade(
            u["student_id"], u["name"], subject,
            score=float(d.get("score", 0)),
            attendance=float(d.get("attendance", 1.0)),
            failed=bool(d.get("failed", False)),
            difficulty=float(d.get("difficulty", 0.6)),
            credit=int(d.get("credit", 3)))
    except (TypeError, ValueError):
        return jsonify({"code": 400, "msg": "成绩/出勤/学分等需为数字", "data": None})
    return jsonify({"code": 0, "msg": "成绩已录入", "data": None})


@app.route("/api/data/consumption", methods=["POST"])
@login_required
def api_add_consumption():
    u = current_user()
    d = request.get_json(force=True)
    item = (d.get("item") or "").strip()
    if not item:
        return jsonify({"code": 400, "msg": "请填写消费项目", "data": None})
    try:
        insert_consumption(
            u["student_id"], u["name"],
            day=int(d.get("day", 1)),
            category=(d.get("category") or "食堂").strip(),
            item=item, amount=float(d.get("amount", 0)))
    except (TypeError, ValueError):
        return jsonify({"code": 400, "msg": "日期/金额需为数字", "data": None})
    return jsonify({"code": 0, "msg": "消费已录入", "data": None})


@app.route("/api/data/import_csv", methods=["POST"])
@login_required
def api_import_csv():
    u = current_user()
    table = request.form.get("table", "grades")
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"code": 400, "msg": "请选择 CSV 文件", "data": None})
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    try:
        file.save(tmp.name)
        tmp.close()
        n = import_csv_for_student(u["student_id"], u["name"], table, tmp.name)
        return jsonify({"code": 0, "msg": f"成功导入 {n} 行", "data": {"rows": n}})
    except Exception as e:
        return jsonify({"code": 400, "msg": f"导入失败：{e}", "data": None})
    finally:
        if os.path.exists(tmp.name):
            os.remove(tmp.name)


# ===================== 【修复】智能规划接口 =====================
@app.route("/api/plan", methods=["POST"])
def api_plan():
    data = request.get_json(force=True)
    student_id = data.get("student_id", "2021001")
    req = (data.get("request") or "").strip()

    if not req:
        return jsonify({"code": 400, "msg": "请输入规划需求", "data": None})

    try:
        # 修复：调用 MasterAgent 的正确方法
        result = supervisor.run_all(
            student_id=student_id,
            daily_study_hours=4.0,
            monthly_budget=1200.0
        )
        return jsonify({"code": 0, "msg": "ok", "data": result})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"code": 500, "msg": str(e), "data": None})


# ===================== 【修复】政策问答 =====================
@app.route("/api/policy_qa", methods=["POST"])
def api_policy_qa():
    data = request.get_json(force=True)
    q = (data.get("question") or "").strip()
    if not q:
        return jsonify({"code": 400, "msg": "请输入问题", "data": None})

    try:
        ans = supervisor.policy.ask(q)
        return jsonify({"code": 0, "msg": "ok", "data": ans})
    except:
        return jsonify({"code": 0, "msg": "ok", "data": {"answer": "暂无法回答"}})


# ===================== 【修复】历史记录 =====================
@app.route("/api/history")
def api_history():
    sid = request.args.get("student_id")
    try:
        conn = get_conn()
        cur = conn.cursor()
        if sid:
            cur.execute("SELECT id, student_id, request, plan, conflict_log, create_time FROM plan_history WHERE student_id = %s ORDER BY id DESC", (sid,))
        else:
            cur.execute("SELECT id, student_id, request, plan, conflict_log, create_time FROM plan_history ORDER BY id DESC")
        rows = cur.fetchall()
        conn.close()
        return jsonify({"code":0, "msg":"ok", "data": rows})
    except:
        return jsonify({"code":0, "msg":"ok", "data":[]})


# ===================== 仪表盘 =====================
@app.route("/api/dashboard")
def api_dashboard():
    """全局数据统计看板。"""
    try:
        conn = get_conn()
        risk_rank = [dict(r) for r in conn.execute(
            "SELECT name, ROUND(AVG(score),1) AS avg_score, SUM(failed) AS fails "
            "FROM grades GROUP BY student_id ORDER BY avg_score ASC").fetchall()]
        env_by_hour = [dict(r) for r in conn.execute(
            "SELECT hour, ROUND(AVG(co2),0) AS avg_co2, ROUND(AVG(traffic),0) AS avg_traffic "
            "FROM iot GROUP BY hour ORDER BY hour").fetchall()]
        consume = [dict(r) for r in conn.execute(
            "SELECT name, ROUND(SUM(amount),1) AS total FROM consumption "
            "GROUP BY student_id ORDER BY total DESC").fetchall()]
        conn.close()
    except:
        risk_rank = []
        env_by_hour = []
        consume = []

    return jsonify({"code": 0, "msg": "ok", "data": {
        "risk_rank": risk_rank,
        "env_by_hour": env_by_hour,
        "consume": consume,
        "static_rule_count": get_static_rule_store().count(),
        "experience_count": get_experience_store().count(),
    }})


if __name__ == "__main__":
    print("=" * 56)
    print("  校园多智能体协同规划平台已启动")
    print("  浏览器访问: http://127.0.0.1:5000")
    print("=" * 56)
    app.run(host="127.0.0.1", port=5000, debug=False)