import os
import json
import logging
import traceback
from functools import wraps
from flask import Flask, render_template, jsonify, request, session, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from pydantic import BaseModel, field_validator, ValidationError
from core.supervisor import Supervisor  # 导入调度器

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ====================== 数据库配置 ======================
DB_USER = os.getenv("MYSQL_USER", "root")
DB_PASS = os.getenv("MYSQL_PASSWORD", "123456")
DB_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
DB_PORT = os.getenv("MYSQL_PORT", "3306")
DB_NAME = os.getenv("MYSQL_DATABASE", "my_agent_db")

app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    f"?charset=utf8mb4"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 3600,
    "pool_size": 10,
    "max_overflow": 20,
}
app.secret_key = os.getenv("SECRET_KEY", "my_secret_key_123456")
app.config['TEMPLATES_AUTO_RELOAD'] = True

db = SQLAlchemy(app)


# ====================== Pydantic 请求模型 ======================
class LoginRequest(BaseModel):
    student_id: str
    password: str

    @field_validator('student_id')
    @classmethod
    def v_sid(cls, v):
        v = v.strip()
        if not v:
            raise ValueError('学号不能为空')
        if len(v) > 50:
            raise ValueError('学号过长')
        return v

    @field_validator('password')
    @classmethod
    def v_pwd(cls, v):
        v = v.strip()
        if not v:
            raise ValueError('密码不能为空')
        return v


class RegisterRequest(BaseModel):
    student_id: str
    name: str
    password: str

    @field_validator('student_id')
    @classmethod
    def v_sid(cls, v):
        v = v.strip()
        if not v:
            raise ValueError('学号不能为空')
        if len(v) > 50:
            raise ValueError('学号过长')
        return v

    @field_validator('name')
    @classmethod
    def v_name(cls, v):
        v = v.strip()
        if not v:
            raise ValueError('姓名不能为空')
        if len(v) > 50:
            raise ValueError('姓名过长')
        return v

    @field_validator('password')
    @classmethod
    def v_pwd(cls, v):
        v = v.strip()
        if not v:
            raise ValueError('密码不能为空')
        if len(v) < 6:
            raise ValueError('密码至少需要6位')
        return v


class PlanRequest(BaseModel):
    request: str

    @field_validator('request')
    @classmethod
    def v_req(cls, v):
        v = v.strip()
        if not v:
            raise ValueError('请输入规划需求')
        if len(v) > 2000:
            raise ValueError('需求内容过长（最多2000字）')
        return v


# ====================== 工具函数 ======================
def parse_body(model_cls):
    """从 request.json 解析并校验，失败返回 None，错误已在调用方处理"""
    data = request.get_json(silent=True)
    if data is None:
        return None, jsonify({"code": 1, "msg": "请求体必须是 JSON 格式"})
    try:
        return model_cls(**data), None
    except ValidationError as e:
        # 取第一个错误的提示
        msg = e.errors()[0].get('msg', '参数校验失败')
        # 去掉 pydantic 的 "Value error, " 前缀
        if msg.startswith('Value error, '):
            msg = msg[len('Value error, '):]
        return None, jsonify({"code": 1, "msg": msg})


def require_login(f):
    """登录校验装饰器"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('student_id'):
            return jsonify({"code": 1, "msg": "未登录"})
        return f(*args, **kwargs)
    return wrapper


# ====================== 数据库模型 ======================
class Users(db.Model):
    __tablename__ = "users"
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='student')
    status = db.Column(db.String(20), default='active')
    create_time = db.Column(db.DateTime, default=datetime.now)


class StudentProfile(db.Model):
    __tablename__ = "student_profile"
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    user_id = db.Column(db.BigInteger)
    student_id = db.Column(db.String(50), unique=True)
    name = db.Column(db.String(50))
    grade = db.Column(db.String(50))
    major = db.Column(db.String(100))


class Grades(db.Model):
    __tablename__ = "grades"
    id = db.Column(db.BigInteger, primary_key=True)
    student_id = db.Column(db.String(50))
    subject = db.Column(db.String(50))
    score = db.Column(db.Float)


class Consumption(db.Model):
    __tablename__ = "consumption"
    id = db.Column(db.BigInteger, primary_key=True)
    student_id = db.Column(db.String(50))
    category = db.Column(db.String(50))
    amount = db.Column(db.Float)
    create_time = db.Column(db.DateTime)


class PlanHistory(db.Model):
    __tablename__ = "plan_history"
    id = db.Column(db.BigInteger, primary_key=True)
    student_id = db.Column(db.String(50))
    request = db.Column(db.Text)
    plan = db.Column(db.Text)
    create_time = db.Column(db.DateTime)


# ====================== 全局异常处理 ======================
@app.errorhandler(ValidationError)
def handle_validation_error(e):
    """Pydantic 校验异常 → 400"""
    msg = e.errors()[0].get('msg', '参数校验失败')
    if msg.startswith('Value error, '):
        msg = msg[len('Value error, '):]
    logger.warning(f"参数校验失败: {msg}")
    return jsonify({"code": 1, "msg": msg}), 400


@app.errorhandler(400)
def handle_400(e):
    return jsonify({"code": 1, "msg": "请求参数错误"}), 400


@app.errorhandler(404)
def handle_404(e):
    return jsonify({"code": 1, "msg": "接口不存在"}), 404


@app.errorhandler(405)
def handle_405(e):
    return jsonify({"code": 1, "msg": "请求方法不允许"}), 405


@app.errorhandler(500)
def handle_500(e):
    logger.error(f"服务器内部错误: {e}")
    return jsonify({"code": 1, "msg": "服务器内部错误，请稍后重试"}), 500


@app.errorhandler(Exception)
def handle_exception(e):
    """兜底：未被捕获的异常"""
    logger.error(f"未处理异常: {type(e).__name__}: {e}")
    logger.error(traceback.format_exc())
    return jsonify({"code": 1, "msg": f"服务器异常: {type(e).__name__}"}), 500


# ====================== 页面路由 ======================
@app.route('/')
def index():
    return render_template('index.html')


# ====================== 学生列表 ======================
@app.route('/api/students')
def api_students():
    students = StudentProfile.query.all()
    return jsonify({"code": 0, "data": [
        {"id": s.id, "student_id": s.student_id, "name": s.name}
        for s in students
    ]})


# ====================== 登录 ======================
@app.route('/api/login', methods=['POST'])
def api_login():
    body, err = parse_body(LoginRequest)
    if err:
        return err

    user = Users.query.filter_by(username=body.student_id).first()
    if not user:
        return jsonify({"code": 1, "msg": "账号不存在"})

    # 密码验证：优先哈希校验，兼容旧版明文密码
    password_ok = False
    if user.password.startswith('pbkdf2:') or user.password.startswith('scrypt:'):
        password_ok = check_password_hash(user.password, body.password)
    else:
        password_ok = (user.password == body.password)
        if password_ok:
            user.password = generate_password_hash(body.password)
            db.session.commit()

    if not password_ok:
        return jsonify({"code": 1, "msg": "密码错误"})

    if user.status == 'pending':
        return jsonify({"code": 1, "msg": "账号正在审核中，请等待管理员审批"})
    if user.status == 'rejected':
        return jsonify({"code": 1, "msg": "账号审核未通过，请联系管理员"})

    profile = StudentProfile.query.filter_by(student_id=body.student_id).first()
    if not profile:
        return jsonify({"code": 1, "msg": "未找到学生档案信息"})

    session['student_id'] = profile.student_id
    session['user_id'] = user.id
    session['username'] = user.username
    session['name'] = profile.name
    session['role'] = user.role

    return jsonify({"code": 0, "data": {
        "name": profile.name,
        "student_id": profile.student_id,
        "role": user.role
    }})


# ====================== 注册 ======================
@app.route('/api/register', methods=['POST'])
def api_register():
    body, err = parse_body(RegisterRequest)
    if err:
        return err

    # 检查学号是否已注册
    if Users.query.filter_by(username=body.student_id).first():
        return jsonify({"code": 1, "msg": "该学号已注册，请直接登录"})
    if StudentProfile.query.filter_by(student_id=body.student_id).first():
        return jsonify({"code": 1, "msg": "该学号已存在学生档案，请直接登录"})

    # 创建用户
    hashed = generate_password_hash(body.password)
    new_user = Users(
        username=body.student_id,
        password=hashed,
        role='student',
        status='active',
        create_time=datetime.now()
    )
    db.session.add(new_user)
    db.session.flush()

    # 创建学生档案
    new_profile = StudentProfile(
        user_id=new_user.id,
        student_id=body.student_id,
        name=body.name
    )
    db.session.add(new_profile)
    db.session.commit()

    logger.info(f"新用户注册: {body.student_id} ({body.name})")
    return jsonify({"code": 0, "msg": "注册成功，请登录"})


# ====================== 登出 ======================
@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({"code": 0, "msg": "已退出登录"})


# ====================== 当前用户信息 ======================
@app.route('/api/me')
def api_me():
    sid = session.get('student_id')
    if not sid:
        return jsonify({"code": 1, "msg": "未登录"})
    return jsonify({"code": 0, "data": {
        "student_id": sid,
        "name": session.get('name', ''),
        "role": session.get('role', 'student')
    }})


# ====================== 个人数据 ======================
@app.route('/api/my_data')
@require_login
def api_my_data():
    sid = session['student_id']
    grades = Grades.query.filter_by(student_id=sid).all()
    consumes = Consumption.query.filter_by(student_id=sid).all()
    return jsonify({"code": 0, "data": {
        "grades": [{"subject": g.subject, "score": g.score} for g in grades],
        "consumption": [{"category": c.category, "amount": c.amount} for c in consumes]
    }})


# ====================== 规划历史 ======================
@app.route('/api/history')
@require_login
def api_history():
    sid = session['student_id']
    history = PlanHistory.query.filter_by(student_id=sid) \
        .order_by(PlanHistory.create_time.desc()).all()
    return jsonify({"code": 0, "data": [
        {
            "request": h.request,
            "plan": h.plan,
            "create_time": h.create_time.strftime("%Y-%m-%d %H:%M") if h.create_time else ""
        }
        for h in history
    ]})


# ====================== 数据看板 ======================
@app.route('/api/dashboard')
@require_login
def api_dashboard():
    sid = session['student_id']
    grades = Grades.query.filter_by(student_id=sid).all()
    consumes = Consumption.query.filter_by(student_id=sid).all()

    avg_score = 0
    if grades:
        avg_score = round(sum(g.score for g in grades) / len(grades), 1)

    total_consume = round(sum(c.amount for c in consumes), 1)

    return jsonify({"code": 0, "data": {"kpis": {
        "avgScore": avg_score,
        "monthConsume": total_consume,
        "risk": "中"
    }}})


# ====================== 生成规划 ======================
@app.route('/api/plan', methods=['POST'])
@require_login
def api_plan():
    body, err = parse_body(PlanRequest)
    if err:
        return err

    sid = session['student_id']

    sv = Supervisor()
    result = sv.plan(sid, body.request)

    # 存入数据库
    try:
        ph = PlanHistory(
            student_id=sid,
            request=body.request,
            plan=str(result["final_plan"].get("summary", "")),
            create_time=datetime.now()
        )
        db.session.add(ph)
        db.session.commit()
    except Exception as db_err:
        logger.warning(f"保存规划历史到MySQL失败: {db_err}")

    return jsonify({"code": 0, "data": {
        "cot": result.get("cot", {}),
        "rounds": result.get("rounds", []),
        "consensus": result.get("consensus", False),
        "total_rounds": result.get("total_rounds", 0),
        "plan": result["final_plan"]
    }})


# ====================== SSE 流式规划 ======================
@app.route('/api/plan/stream', methods=['POST'])
@require_login
def api_plan_stream():
    body, err = parse_body(PlanRequest)
    if err:
        return err

    sid = session['student_id']
    sv = Supervisor()

    def generate():
        try:
            for evt in sv.plan_stream(sid, body.request):
                event_name = evt.get("event", "message")
                data = evt.get("data", {})
                yield f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"SSE 流式规划异常: {e}\n{traceback.format_exc()}")
            yield f"event: error\ndata: {json.dumps({'msg': str(e)}, ensure_ascii=False)}\n\n"

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )


# ====================== 调试 ======================
@app.route('/debug-db')
def debug_db():
    from sqlalchemy import text
    result = db.session.execute(text("SELECT DATABASE();"))
    current_db = result.scalar()
    return jsonify({"code": 0, "msg": f"当前连接的数据库：{current_db}"})


if __name__ == '__main__':
    with app.app_context():
        try:
            db.create_all()
            logger.info("数据库表检查/创建完成")
        except Exception as e:
            logger.error(f"数据库初始化失败，请检查 MySQL 是否启动: {e}")
            logger.error("提示: 确认 MySQL 服务已运行，且 my_agent_db 数据库已创建")
    app.run(debug=True)
