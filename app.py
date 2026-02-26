from flask import Flask, render_template, request, redirect, session
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "seguro123")

# ================= CONEXÃO =================
def get_connection():
    DATABASE_URL = os.environ.get("DATABASE_URL")
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor,
        connect_timeout=5
    )

# ================= FILTRO BRL =================
@app.template_filter("brl")
def brl(valor):
    try:
        return "R$ {:,.2f}".format(float(valor)).replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "R$ 0,00"

# ================= LOGIN =================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute(
                "SELECT * FROM usuarios WHERE email=%s",
                (request.form["email"],)
            )
            user = cursor.fetchone()
            conn.close()

            if user and check_password_hash(user["senha"], request.form["senha"]):
                session["usuario_id"] = user["id"]
                session["nome"] = user["nome"]
                return redirect("/dashboard")
            else:
                return "Login inválido"

        except Exception as e:
            return f"Erro login: {e}"

    return render_template("login.html")

# ================= CADASTRO =================
@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        try:
            conn = get_connection()
            cursor = conn.cursor()

            senha_hash = generate_password_hash(request.form["senha"])

            cursor.execute("""
                INSERT INTO usuarios (nome, email, senha)
                VALUES (%s, %s, %s)
            """, (
                request.form["nome"],
                request.form["email"],
                senha_hash
            ))

            conn.commit()
            conn.close()

            return redirect("/")

        except Exception as e:
            return f"Erro cadastro: {e}"

    return render_template("cadastro.html")

# ================= DASHBOARD =================
@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "usuario_id" not in session:
        return redirect("/")

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # INSERIR GASTO
        if request.method == "POST":
            cursor.execute("""
                INSERT INTO gastos (usuario_id, descricao, valor, categoria, data)
                VALUES (%s,%s,%s,%s,%s)
            """, (
                session["usuario_id"],
                request.form["descricao"],
                float(request.form["valor"]),
                request.form["categoria"],
                datetime.now().date()
            ))
            conn.commit()

        # LISTAR GASTOS
        cursor.execute("""
            SELECT * FROM gastos
            WHERE usuario_id=%s
            ORDER BY data DESC
        """, (session["usuario_id"],))

        gastos = cursor.fetchall()

        conn.close()

        return render_template(
            "dashboard.html",
            nome=session["nome"],
            gastos=gastos,
            renda_mensal=0,
            saldo=0,
            percentual=0,
            resumo_categoria=[],
            evolucao_mensal=[]
        )

    except Exception as e:
        return f"Erro dashboard: {e}"

# ================= LOGOUT =================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ================= START =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)