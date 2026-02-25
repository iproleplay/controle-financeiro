from flask import Flask, render_template, request, redirect, session
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = "segredo_super_forte"

DATABASE_URL = os.environ.get("DATABASE_URL")


# ================= CONEXÃO =================
def get_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


# ================= FILTRO BRL =================
@app.template_filter("brl")
def brl(valor):
    try:
        return "R$ {:,.2f}".format(float(valor)).replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "R$ 0,00"


# ================= CRIAR TABELAS =================
def criar_tabelas():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY,
        nome TEXT,
        email TEXT UNIQUE,
        senha TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS configuracoes (
        usuario_id INTEGER PRIMARY KEY,
        salario NUMERIC,
        meta NUMERIC
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS gastos (
        id SERIAL PRIMARY KEY,
        usuario_id INTEGER,
        descricao TEXT,
        valor NUMERIC,
        categoria TEXT,
        data DATE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS prioridades (
        id SERIAL PRIMARY KEY,
        usuario_id INTEGER,
        nome TEXT,
        valor NUMERIC
    )
    """)

    conn.commit()
    conn.close()


criar_tabelas()


# ================= LOGIN =================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        senha = request.form["senha"]

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE email=%s", (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user["senha"], senha):
            session["usuario_id"] = user["id"]
            session["nome"] = user["nome"]
            return redirect("/dashboard")
        else:
            return "Login inválido"

    return render_template("login.html")


# ================= CADASTRO =================
@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        nome = request.form["nome"]
        email = request.form["email"]
        senha = generate_password_hash(request.form["senha"])

        conn = get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO usuarios (nome, email, senha) VALUES (%s, %s, %s)",
                (nome, email, senha)
            )
            conn.commit()
            conn.close()
            return redirect("/")
        except:
            conn.close()
            return "Email já cadastrado"

    return render_template("cadastro.html")


# ================= DASHBOARD =================
@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():

    if "usuario_id" not in session:
        return redirect("/")

    usuario_id = session["usuario_id"]

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT salario, meta FROM configuracoes WHERE usuario_id=%s", (usuario_id,))
    config = cursor.fetchone()

    salario = float(config["salario"]) if config and config["salario"] else 0
    meta = float(config["meta"]) if config and config["meta"] else 1000

    if request.method == "POST":
        tipo = request.form.get("tipo")

        if tipo == "meta":
            meta = float(request.form["meta"])
            cursor.execute("""
            INSERT INTO configuracoes (usuario_id, salario, meta)
            VALUES (%s, %s, %s)
            ON CONFLICT (usuario_id)
            DO UPDATE SET meta=EXCLUDED.meta
            """, (usuario_id, salario, meta))
            conn.commit()

        elif tipo == "gasto":
            descricao = request.form["descricao"]
            valor = float(request.form["valor"])
            categoria = request.form["categoria"]
            data_atual = datetime.now().date()

            cursor.execute("""
            INSERT INTO gastos (usuario_id, descricao, valor, categoria, data)
            VALUES (%s, %s, %s, %s, %s)
            """, (usuario_id, descricao, valor, categoria, data_atual))
            conn.commit()

    cursor.execute("SELECT SUM(valor) AS total FROM gastos WHERE usuario_id=%s", (usuario_id,))
    total_gastos = cursor.fetchone()["total"] or 0

    cursor.execute("SELECT SUM(valor) AS total FROM prioridades WHERE usuario_id=%s", (usuario_id,))
    total_prioridades = cursor.fetchone()["total"] or 0

    saldo = salario - float(total_gastos) - float(total_prioridades)
    progresso = min((saldo / meta) * 100, 100) if meta > 0 else 0
    falta = max(meta - saldo, 0)

    cursor.execute("""
        SELECT categoria, SUM(valor) AS total
        FROM gastos
        WHERE usuario_id=%s
        GROUP BY categoria
    """, (usuario_id,))
    resumo_categoria = [(row["categoria"], float(row["total"])) for row in cursor.fetchall()]

    conn.close()

    return render_template(
        "dashboard.html",
        nome=session["nome"],
        salario=salario,
        saldo=saldo,
        meta=meta,
        progresso=progresso,
        falta=falta,
        resumo_categoria=resumo_categoria,
        total_prioridades=total_prioridades
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")