from flask import Flask, render_template, request, redirect, session
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date

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

        if tipo == "gasto":
            descricao = request.form["descricao"]
            valor = float(request.form["valor"])
            categoria = request.form["categoria"]
            data = datetime.now().date()

            cursor.execute("""
                INSERT INTO gastos (usuario_id, descricao, valor, categoria, data)
                VALUES (%s, %s, %s, %s, %s)
            """, (usuario_id, descricao, valor, categoria, data))
            conn.commit()

    # Saldo
    cursor.execute("SELECT SUM(valor) AS total FROM gastos WHERE usuario_id=%s", (usuario_id,))
    total_gastos = float(cursor.fetchone()["total"] or 0)

    saldo = -total_gastos

    # ================= EVOLUÇÃO MENSAL =================
    cursor.execute("""
        SELECT DATE_TRUNC('month', data) AS mes,
               SUM(valor) AS total
        FROM gastos
        WHERE usuario_id=%s
        GROUP BY mes
        ORDER BY mes
    """, (usuario_id,))

    evolucao_rows = cursor.fetchall()

    meses_pt = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
    evolucao_mensal = []

    for row in evolucao_rows:
        data_mes = row["mes"]
        nome_mes = f"{meses_pt[data_mes.month - 1]}/{data_mes.year}"
        evolucao_mensal.append((nome_mes, float(row["total"])))

    # ================= COMPARAÇÃO =================
    cursor.execute("""
        SELECT DATE_TRUNC('month', data) AS mes,
               SUM(valor) AS total
        FROM gastos
        WHERE usuario_id=%s
        GROUP BY mes
        ORDER BY mes DESC
        LIMIT 2
    """, (usuario_id,))

    comparacao_rows = cursor.fetchall()

    mes_atual_total = 0
    mes_anterior_total = 0
    variacao_percentual = 0

    if len(comparacao_rows) > 0:
        mes_atual_total = float(comparacao_rows[0]["total"] or 0)

    if len(comparacao_rows) > 1:
        mes_anterior_total = float(comparacao_rows[1]["total"] or 0)

    if mes_anterior_total > 0:
        variacao_percentual = ((mes_atual_total - mes_anterior_total) / mes_anterior_total) * 100

    conn.close()

    return render_template(
        "dashboard.html",
        nome=session["nome"],
        saldo=saldo,
        evolucao_mensal=evolucao_mensal,
        mes_atual_total=mes_atual_total,
        mes_anterior_total=mes_anterior_total,
        variacao_percentual=variacao_percentual
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")