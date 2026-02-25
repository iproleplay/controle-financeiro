from flask import Flask, render_template, request, redirect, session
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "segredo_super_forte")

DATABASE_URL = os.environ.get("DATABASE_URL")


# ================= CONEXÃO =================
def get_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


# ================= GARANTIR COLUNA ROLE =================
def garantir_coluna_role():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        ALTER TABLE usuarios
        ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'user';
    """)
    conn.commit()
    conn.close()


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
        senha TEXT,
        role TEXT DEFAULT 'user'
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS configuracoes (
        usuario_id INTEGER PRIMARY KEY,
        salario NUMERIC DEFAULT 0,
        meta NUMERIC DEFAULT 1000
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


# Executa criação segura
try:
    criar_tabelas()
    garantir_coluna_role()
except Exception as e:
    print("Erro na inicialização:", e)


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
            session["role"] = user.get("role", "user")
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

    if request.method == "POST":
        tipo = request.form.get("tipo")

        if tipo == "meta":
            meta = float(request.form["meta"])
            cursor.execute("""
                INSERT INTO configuracoes (usuario_id, meta)
                VALUES (%s, %s)
                ON CONFLICT (usuario_id)
                DO UPDATE SET meta=EXCLUDED.meta
            """, (usuario_id, meta))
            conn.commit()

        elif tipo == "gasto":
            descricao = request.form["descricao"]
            valor = float(request.form["valor"])
            categoria = request.form["categoria"]
            data = datetime.now().date()

            cursor.execute("""
                INSERT INTO gastos (usuario_id, descricao, valor, categoria, data)
                VALUES (%s, %s, %s, %s, %s)
            """, (usuario_id, descricao, valor, categoria, data))
            conn.commit()

        elif tipo == "prioridade":
            nome = request.form["nome"]
            valor = float(request.form["valor"])

            cursor.execute("""
                INSERT INTO prioridades (usuario_id, nome, valor)
                VALUES (%s, %s, %s)
            """, (usuario_id, nome, valor))
            conn.commit()

    # CONFIG
    cursor.execute("SELECT salario, meta FROM configuracoes WHERE usuario_id=%s", (usuario_id,))
    config = cursor.fetchone()

    salario = float(config["salario"]) if config and config["salario"] else 0
    meta = float(config["meta"]) if config and config["meta"] else 1000

    cursor.execute("SELECT SUM(valor) AS total FROM gastos WHERE usuario_id=%s", (usuario_id,))
    total_gastos = cursor.fetchone()["total"] or 0

    cursor.execute("SELECT nome, valor FROM prioridades WHERE usuario_id=%s", (usuario_id,))
    prioridades = cursor.fetchall()
    total_prioridades = sum(float(p["valor"]) for p in prioridades) if prioridades else 0

    saldo = salario - float(total_gastos) - total_prioridades
    patrimonio = saldo
    progresso = min((saldo / meta) * 100, 100) if meta > 0 else 0

    # HISTÓRICO
    cursor.execute("""
        SELECT TO_CHAR(data, 'Month YYYY') AS mes,
               descricao,
               valor
        FROM gastos
        WHERE usuario_id=%s
        ORDER BY data DESC
    """, (usuario_id,))
    historico_rows = cursor.fetchall()

    historico = {}
    for row in historico_rows:
        mes = row["mes"].strip()
        if mes not in historico:
            historico[mes] = []
        historico[mes].append(row)

    # RESUMO CATEGORIA
    cursor.execute("""
        SELECT categoria, SUM(valor) AS total
        FROM gastos
        WHERE usuario_id=%s
        GROUP BY categoria
    """, (usuario_id,))
    resumo_categoria = [(r["categoria"], float(r["total"])) for r in cursor.fetchall()]

    # EVOLUÇÃO
    cursor.execute("""
        SELECT TO_CHAR(data, 'Mon') AS mes,
               SUM(valor) AS total
        FROM gastos
        WHERE usuario_id=%s
        GROUP BY mes
        ORDER BY mes
    """, (usuario_id,))
    evolucao_mensal = [(r["mes"], float(r["total"])) for r in cursor.fetchall()]

    conn.close()

    return render_template(
        "dashboard.html",
        nome=session["nome"],
        salario=salario,
        saldo=saldo,
        patrimonio=patrimonio,
        meta=meta,
        progresso=progresso,
        prioridades=prioridades,
        historico=historico,
        resumo_categoria=resumo_categoria,
        evolucao_mensal=evolucao_mensal
    )


# ================= ADMIN =================
@app.route("/admin")
def admin():
    if "usuario_id" not in session:
        return redirect("/")

    if session.get("role") != "admin":
        return "Acesso restrito ao administrador"

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome, email, role FROM usuarios ORDER BY id DESC")
    usuarios = cursor.fetchall()
    conn.close()

    return render_template("admin.html", usuarios=usuarios)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")