from flask import Flask, render_template, jsonify, request, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)

# ====================== 数据库配置 ======================
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:123456@localhost/mysql_agent'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = "my_secret_key_123456"
app.config['TEMPLATES_AUTO_RELOAD'] = True

db = SQLAlchemy(app)

# ====================== 数据库模型 ======================
class Users(db.Model):
    __tablename__ = "user"
    id = db.Column(db.BigInteger, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    role = db.Column(db.String(20))

class StudentProfile(db.Model):
    __tablename__ = "student_profile"
    id = db.Column(db.BigInteger, primary_key=True)
    student_id = db.Column(db.String(50), unique=True)
    name = db.Column(db.String(50))

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

# ====================== 页面路由 ======================
@app.route('/')
def index():
    return render_template('index.html')

# ====================== 【正确接口】学生列表 ======================
@app.route('/api/students')
def api_students():
    students = StudentProfile.query.all()
    data = []
    for s in students:
        data.append({
            "id": s.id,
            "student_id": s.student_id,
            "name": s.name
        })
    return jsonify({"code": 0, "data": data})

# ====================== 登录 ======================
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    student_id = data.get('student_id')
    password = data.get('password')

    user = Users.query.filter_by(username=student_id, password=password).first()
    if not user:
        return jsonify({"code": 1, "msg": "账号或密码错误"})

    profile = StudentProfile.query.filter_by(student_id=student_id).first()
    session['student_id'] = profile.student_id
    return jsonify({"code": 0, "data": {"name": profile.name}})

# ====================== 个人数据 ======================
@app.route('/api/my_data')
def api_my_data():
    student_id = session.get('student_id')
    if not student_id:
        return jsonify({"code": 1, "msg": "未登录"})

    grades = Grades.query.filter_by(student_id=student_id).all()
    consumes = Consumption.query.filter_by(student_id=student_id).all()

    return jsonify({
        "code": 0,
        "data": {
            "grades": [{"subject": g.subject, "score": g.score} for g in grades],
            "consumption": [{"category": c.category, "amount": c.amount} for c in consumes]
        }
    })

# ====================== 规划历史 ======================
@app.route('/api/history')
def api_history():
    student_id = session.get('student_id')
    if not student_id:
        return jsonify({"code": 1, "msg": "未登录"})

    history = PlanHistory.query.filter_by(student_id=student_id).order_by(PlanHistory.create_time.desc()).all()
    res = []
    for h in history:
        res.append({
            "request": h.request,
            "plan": h.plan,
            "create_time": h.create_time.strftime("%Y-%m-%d %H:%M")
        })
    return jsonify({"code": 0, "data": res})

# ====================== 数据看板 ======================
@app.route('/api/dashboard')
def api_dashboard():
    student_id = session.get('student_id')
    if not student_id:
        return jsonify({"code": 1, "msg": "未登录"})

    grades = Grades.query.filter_by(student_id=student_id).all()
    consumes = Consumption.query.filter_by(student_id=student_id).all()

    avg_score = 0
    if grades:
        avg_score = round(sum(g.score for g in grades) / len(grades), 1)

    total_consume = round(sum(c.amount for c in consumes), 1)

    return jsonify({
        "code": 0,
        "data": {
            "kpis": {
                "avgScore": avg_score,
                "monthConsume": total_consume,
                "risk": "中"
            }
        }
    })

# ====================== 生成规划 ======================
@app.route('/api/plan', methods=['POST'])
def api_plan():
    student_id = session.get('student_id')
    if not student_id:
        return jsonify({"code": 1, "msg": "未登录"})

    req = request.json.get('request', '')
    grades = Grades.query.filter_by(student_id=student_id).all()
    consumes = Consumption.query.filter_by(student_id=student_id).all()

    plan = {
        "study": f"共{len(grades)}门课程",
        "env": "22:30闭馆，推荐安静自习室",
        "consume": f"本月消费{sum(c.amount for c in consumes)}元",
        "policy": "符合校园管理规定"
    }

    ph = PlanHistory(
        student_id=student_id,
        request=req,
        plan=str(plan),
        create_time=datetime.now()
    )
    db.session.add(ph)
    db.session.commit()

    return jsonify({"code": 0, "data": {"plan": plan}})

@app.route('/debug-db')
def debug_db():
    from sqlalchemy import text
    result = db.session.execute(text("SELECT DATABASE();"))
    current_db = result.scalar()
    return f"当前连接的数据库：{current_db}"


if __name__ == '__main__':
    app.run(debug=True)

    from sqlalchemy import text

