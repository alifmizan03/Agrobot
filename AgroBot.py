from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
import os
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()  # pastikan nama fail betul

# Check if API key terbaca
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY tidak ditemui. Sila pastikan app.env wujud dan API key betul.")

# Initialize OpenAI client
client = OpenAI(api_key=api_key)

# Initialize Flask
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///gamification.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Persona AgroBot
persona = (
    "Anda adalah 'AgroBot', pembantu pertanian yang mesra dan berpengetahuan. "
    "Anda membantu petani, pelajar dan pemula memahami teknik penanaman, "
    "jenis tanah, cuaca, baja, pengairan, kawalan perosak, dan diagnosis penyakit tanaman dengan bahasa mudah.\n\n"
    "Anda pakar dalam pertanian di Malaysia termasuk:\n"
    "- Jenis tanah sesuai untuk tanaman (lempung, berpasir, gambut).\n"
    "- Keperluan suhu, cahaya dan kelembapan bagi setiap tanaman.\n"
    "- Baja organik & kimia, cara aplikasi.\n"
    "- Masalah daun kuning, reput akar, serangan ulat & kulat.\n"
    "- Teknik penanaman sayur seperti kangkung, sawi, cili, tomato, bendi.\n"
    "- Teknologi pertanian moden seperti fertigasi & hidroponik.\n\n"
    "Jawapan mestilah ringkas, mesra, dan mudah difahami dalam Bahasa Melayu."
)

# Database model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    points = db.Column(db.Integer, default=0)
    stickers = db.Column(db.Text)

with app.app_context():
    db.create_all()

conversation_history = []

@app.route("/")
def home():
    return render_template("index_AgroBot.html")  # pastikan HTML wujud

# ---------------------------
# Chat dengan AgroBot
# ---------------------------
def generate_response(user_input, username):
    global conversation_history
    conversation_history.append({"role": "user", "content": user_input})
    messages = [{"role": "system", "content": persona}] + conversation_history

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=messages,
        max_tokens=150,
        temperature=0.7,
    )

    bot_response = response.choices[0].message.content.strip()
    conversation_history.append({"role": "assistant", "content": bot_response})

    if len(conversation_history) > 6:
        conversation_history = conversation_history[-6:]

    user = User.query.filter_by(username=username).first()
    if user:
        user.points += 10
        db.session.commit()

    return bot_response

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_input = data.get("message", "")
    username = data.get("username", "guest")

    user = User.query.filter_by(username=username).first()
    if not user:
        user = User(username=username)
        db.session.add(user)
        db.session.commit()

    response_text = generate_response(user_input, username)

    return jsonify({
        "response": response_text,
        "points": user.points,
        "stickers": user.stickers or ""
    })

# ---------------------------
# Quiz AgroBot
# ---------------------------
@app.route("/generate_quiz", methods=["POST"])
def generate_quiz():
    data = request.json
    topic = data.get("topic", "pertanian")

    prompt = (
        f"Buat satu soalan kuiz pilihan berganda tentang pertanian berkaitan {topic} dalam Bahasa Melayu. "
        "Sediakan 4 pilihan jawapan (A, B, C, D) dan nyatakan jawapan yang betul.\n"
        "Format:\nSoalan: ...\nA) ...\nB) ...\nC) ...\nD) ...\nJawapan Betul: ..."
    )

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
        temperature=0.7,
    )

    quiz_content = response.choices[0].message.content.strip()

    # Parse quiz content
    lines = quiz_content.split("\n")
    question = ""
    choices = []
    correct_answer = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.lower().startswith("soalan:"):
            question = line.split(":", 1)[1].strip()
        elif line[0] in "ABCD" and line[1:2] == ")":
            choices.append(line)
        elif line.lower().startswith("jawapan betul"):
            correct_answer = line.split(":", 1)[1].strip()

    return jsonify({
        "question": question,
        "choices": choices[:4],
        "correct_answer": correct_answer
    })

@app.route("/quiz_answer", methods=["POST"])
def quiz_answer():
    data = request.json
    user_answer = data.get("answer", "").strip()
    correct_answer = data.get("correct_answer", "").strip()

    # Buang label seperti "A) " jika ada
    def clean_answer(ans):
        ans = ans.strip()
        if len(ans) > 2 and ans[1] == ")":
            ans = ans[2:].strip()
        return ans.lower()

    user_clean = clean_answer(user_answer)
    correct_clean = clean_answer(correct_answer)

    user = User.query.filter_by(username="guest").first()
    if user_clean == correct_clean:
        if user:
            user.points += 20
            stickers = user.stickers.split(',') if user.stickers else []
            stickers.append("🌱")
            user.stickers = ",".join(stickers)
            db.session.commit()
        return jsonify({
            "message": "Betul! Anda dapat 20 mata dan pelekat 🌱!",
            "points": user.points,
            "stickers": user.stickers
        })

    return jsonify({
        "message": "Jawapan kurang tepat, cuba lagi!",
        "points": user.points
    })

# ---------------------------
# Clear chat history
# ---------------------------
@app.route("/clear", methods=["POST"])
def clear_history():
    global conversation_history
    conversation_history = []
    return jsonify({"message": "Conversation history cleared."})

def reset_user_points():
    with app.app_context():
        users = User.query.all()
        for user in users:
            user.points = 0
            user.stickers = ""
        db.session.commit()

if __name__ == "__main__":
    reset_user_points()
    app.run(debug=True)
