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

    # ---------- ADICIONAR GASTO ----------
    if request.method == "POST":
        descricao = request.form.get("descricao")
        valor = request.form.get("valor")
        categoria = request.form.get("categoria")

        if descricao and valor and categoria:
            cursor.execute("""
                INSERT INTO gastos (usuario_id, descricao, valor, categoria, data)
                VALUES (%s, %s, %s, %s, %s)
            """, (usuario_id, descricao, float(valor), categoria, datetime.now().date()))
            conn.commit()

    # ---------- TOTAL GASTOS ----------
    cursor.execute("SELECT SUM(valor) AS total FROM gastos WHERE usuario_id=%s", (usuario_id,))
    total_gastos = float(cursor.fetchone()["total"] or 0)

    saldo = -total_gastos

    # ---------- RESUMO CATEGORIA ----------
    cursor.execute("""
        SELECT categoria, SUM(valor) AS total
        FROM gastos
        WHERE usuario_id=%s
        GROUP BY categoria
    """, (usuario_id,))

    resumo_categoria = []
    for row in cursor.fetchall():
        resumo_categoria.append((row["categoria"], float(row["total"])))

    # ---------- EVOLUÇÃO MENSAL ----------
    cursor.execute("""
        SELECT DATE_TRUNC('month', data) AS mes,
               SUM(valor) AS total
        FROM gastos
        WHERE usuario_id=%s
        GROUP BY mes
        ORDER BY mes
    """, (usuario_id,))

    evolucao_mensal = []
    meses_pt = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]

    for row in cursor.fetchall():
        data_mes = row["mes"]
        nome_mes = f"{meses_pt[data_mes.month - 1]}/{data_mes.year}"
        evolucao_mensal.append((nome_mes, float(row["total"])))

    # ---------- COMPARAÇÃO MENSAL ----------
    cursor.execute("""
        SELECT DATE_TRUNC('month', data) AS mes,
               SUM(valor) AS total
        FROM gastos
        WHERE usuario_id=%s
        GROUP BY mes
        ORDER BY mes DESC
        LIMIT 2
    """, (usuario_id,))

    comparacao = cursor.fetchall()

    mes_atual_total = float(comparacao[0]["total"]) if len(comparacao) > 0 else 0
    mes_anterior_total = float(comparacao[1]["total"]) if len(comparacao) > 1 else 0

    variacao_percentual = 0
    if mes_anterior_total > 0:
        variacao_percentual = ((mes_atual_total - mes_anterior_total) / mes_anterior_total) * 100

    conn.close()

    return render_template(
        "dashboard.html",
        nome=session["nome"],
        saldo=saldo,
        meta=0,
        progresso=0,
        historico={},
        resumo_categoria=resumo_categoria,
        evolucao_mensal=evolucao_mensal,
        mes_atual_total=mes_atual_total,
        mes_anterior_total=mes_anterior_total,
        variacao_percentual=variacao_percentual
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")