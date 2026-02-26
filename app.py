from flask import Flask, render_template, request, redirect, session
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chave_padrao_segura")

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_connection():
    if not DATABASE_URL:
        raise Exception("DATABASE_URL não configurada.")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


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
        email = request.form.get("email")
        senha = request.form.get("senha")

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE email=%s", (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user["senha"], senha):
            session["usuario_id"] = user["id"]
            session["nome"] = user["nome"]
            session["role"] = user.get("role", "user")
            return redirect("/dashboard")
        else:
            return "Login inválido"

    return render_template("login.html")


# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    if "usuario_id" not in session:
        return redirect("/")

    return render_template("dashboard.html", nome=session["nome"])


# ================= ADMIN =================
@app.route("/admin")
def admin():
    if session.get("role") != "admin":
        return "Acesso negado."

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome, email, role FROM usuarios ORDER BY id")
    usuarios = cursor.fetchall()
    conn.close()

    return render_template("admin.html", usuarios=usuarios)


@app.route("/admin/editar/<int:user_id>", methods=["POST"])
def editar_usuario(user_id):
    if session.get("role") != "admin":
        return "Acesso negado."

    nome = request.form.get("nome")
    email = request.form.get("email")
    senha = request.form.get("senha")
    role = request.form.get("role")

    conn = get_connection()
    cursor = conn.cursor()

    if senha:
        senha_hash = generate_password_hash(senha)
        cursor.execute("""
            UPDATE usuarios
            SET nome=%s, email=%s, senha=%s, role=%s
            WHERE id=%s
        """, (nome, email, senha_hash, role, user_id))
    else:
        cursor.execute("""
            UPDATE usuarios
            SET nome=%s, email=%s, role=%s
            WHERE id=%s
        """, (nome, email, role, user_id))

    conn.commit()
    conn.close()

    return redirect("/admin")


@app.route("/admin/excluir/<int:user_id>")
def excluir_usuario(user_id):
    if session.get("role") != "admin":
        return "Acesso negado."

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM usuarios WHERE id=%s", (user_id,))
    conn.commit()
    conn.close()

    return redirect("/admin")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")