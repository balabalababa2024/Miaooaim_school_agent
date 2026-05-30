"""
样本数据生成器
================
真实公开数据集（Kaggle 高校成绩 / 城市 IoT 传感 / 校园消费脱敏数据）需付费或注册下载，
这里用「带固定随机种子」的代表性样本数据替代，结构与真实数据集字段一致。
如需接入真实数据：把同名 CSV 放到 data/ 目录即可，本模块不会覆盖已存在的文件。
"""
import csv
import os
import random

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

SUBJECTS = ["高等数学", "大学英语", "数据结构", "线性代数", "大学物理", "思想政治"]
DIFFICULTY = {"高等数学": 0.95, "大学英语": 0.6, "数据结构": 0.85,
              "线性代数": 0.75, "大学物理": 0.8, "思想政治": 0.45}
CREDIT = {"高等数学": 5, "大学英语": 4, "数据结构": 4,
          "线性代数": 3, "大学物理": 4, "思想政治": 2}

STUDENTS = [
    ("2021001", "张明"), ("2021002", "李雪"), ("2021003", "王浩"),
    ("2021004", "刘婷"), ("2021005", "陈强"),
]

DISHES = [
    ("红烧肉套餐", 16.0), ("番茄炒蛋盖饭", 9.0), ("黄焖鸡米饭", 15.0),
    ("青菜豆腐", 5.0), ("牛肉拉面", 13.0), ("麻辣香锅", 22.0),
    ("白米饭", 1.0), ("免费例汤", 0.0), ("水果捞", 8.0), ("煎饼果子", 6.0),
]

FLOORS = ["图书馆1F", "图书馆3F", "图书馆5F", "教学楼A203", "教学楼B501"]


def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _path(name):
    return os.path.join(DATA_DIR, name)


def gen_grades():
    """学生学业时序数据集：每科历次成绩、出勤、挂科、难度、学分、考试周。"""
    path = _path("students_grades.csv")
    if os.path.exists(path):
        return
    rng = random.Random(42)
    rows = []
    for sid, name in STUDENTS:
        base_ability = rng.uniform(60, 88)
        for subj in SUBJECTS:
            # 4 次历次成绩（期中/月考/模拟/上学期），体现波动
            for term, label in enumerate(["上学期", "月考", "期中", "模拟考"]):
                penalty = (DIFFICULTY[subj] - 0.5) * 30
                vol = rng.uniform(-12, 12)
                score = max(20, min(99, base_ability - penalty + vol))
                attendance = round(rng.uniform(0.7, 1.0), 2)
                rows.append({
                    "student_id": sid, "name": name, "subject": subj,
                    "exam_label": label, "term_index": term,
                    "score": round(score, 1), "attendance": attendance,
                    "failed": 1 if score < 60 else 0,
                    "difficulty": DIFFICULTY[subj], "credit": CREDIT[subj],
                    "exam_week": 16,  # 第16教学周为考试周
                })
    _write(path, rows)


def gen_iot():
    """自习室 IoT 时序数据：逐小时人流量、CO2、温湿度、占用率。"""
    path = _path("study_room_iot.csv")
    if os.path.exists(path):
        return
    rng = random.Random(7)
    rows = []
    for floor in FLOORS:
        for hour in range(8, 23):  # 8:00 - 22:00
            # 午后与晚间为高峰
            peak = 1.0 if hour in (10, 11, 14, 15, 19, 20) else 0.5
            traffic = int(rng.uniform(20, 120) * peak)
            co2 = int(450 + traffic * rng.uniform(3.5, 6.0))
            temp = round(rng.uniform(20, 27), 1)
            humidity = round(rng.uniform(35, 65), 1)
            occupancy = round(min(1.0, traffic / 120.0), 2)
            rows.append({
                "floor": floor, "hour": hour, "traffic": traffic,
                "co2": co2, "temperature": temp, "humidity": humidity,
                "occupancy": occupancy,
            })
    _write(path, rows)


def gen_consumption():
    """食堂&水电消费数据：每日食堂明细、菜品单价、月度水电、充值。"""
    path = _path("consumption.csv")
    if os.path.exists(path):
        return
    rng = random.Random(99)
    rows = []
    for sid, name in STUDENTS:
        for day in range(1, 31):  # 一个月
            meals = rng.randint(2, 3)
            for _ in range(meals):
                dish, price = rng.choice(DISHES)
                rows.append({
                    "student_id": sid, "name": name, "day": day,
                    "category": "食堂", "item": dish, "amount": price,
                })
        # 月度水电
        rows.append({"student_id": sid, "name": name, "day": 30,
                     "category": "水电", "item": "宿舍电费", "amount": round(rng.uniform(40, 110), 1)})
        rows.append({"student_id": sid, "name": name, "day": 30,
                     "category": "水电", "item": "宿舍水费", "amount": round(rng.uniform(15, 45), 1)})
    _write(path, rows)


def gen_policies():
    """校园政策文档：奖学金/宿舍/报修/自习室规定，存为 Markdown 供向量库切片。"""
    path = _path("policies.md")
    if os.path.exists(path):
        return
    text = """# 校园政策文档汇编

## 自习室管理规定
1. 图书馆及各教学楼自习室开放时间为每日 06:30 至 22:30，22:30 准时清场关闭。
2. 自习室夜间关闭时间为 22:30，任何自习方案不得安排在 22:30 之后使用自习室。
3. 自习室内禁止外放声音、禁止长时间占座，离开超过 30 分钟视为放弃座位。

## 宿舍管理条例
1. 学生宿舍每晚 23:00 统一熄灯断电（公共照明保留），熄灯后不得在宿舍高声学习影响他人。
2. 任何个人学习计划的居家学习时段不得安排在 23:00 之后。
3. 宿舍水电节约：人均月度水电费建议控制在 130 元以内，超出部分需自行承担。

## 奖学金评定办法
1. 申请国家奖学金的学生，学业平均成绩（加权）需达到 85 分及以上，且无任何挂科记录。
2. 申请校级一等奖学金，加权平均成绩需达到 80 分及以上。
3. 综合素质测评中，学业成绩占比 70%，不得有课程不及格。

## 设备报修流程
1. 宿舍或教室设备损坏，登录后勤服务平台提交报修单，注明楼栋、房间号、故障描述。
2. 普通报修 48 小时内处理，紧急报修（漏水、断电）2 小时内响应。
3. 报修完成后需在系统内确认评价，方可关闭工单。

## 校园消费与餐饮规定
1. 食堂提供平价窗口，免费例汤与白米饭长期供应，鼓励学生合理膳食、节约开支。
2. 校园一卡通单日消费无硬性上限，但建议学生根据生活费合理规划每日餐饮支出。
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _write(path, rows):
    if not rows:
        return
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def ensure_all():
    _ensure_dir()
    gen_grades()
    gen_iot()
    gen_consumption()
    gen_policies()


if __name__ == "__main__":
    ensure_all()
    print(f"样本数据已生成至 {DATA_DIR}")
