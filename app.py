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

    # ===== SALVAR RENDA =====
    if request.method == "POST" and request.form.get("tipo") == "renda":
        renda = request.form.get("renda")
        if renda:
            cursor.execute("""
                UPDATE usuarios
                SET renda_mensal=%s
                WHERE id=%s
            """, (float(renda), usuario_id))
            conn.commit()

    # ===== SALVAR GASTO =====
    if request.method == "POST" and request.form.get("tipo") == "gasto":
        descricao = request.form.get("descricao")
        valor = request.form.get("valor")
        categoria = request.form.get("categoria")

        if descricao and valor and categoria:
            cursor.execute("""
                INSERT INTO gastos (usuario_id, descricao, valor, categoria, data)
                VALUES (%s, %s, %s, %s, %s)
            """, (usuario_id, descricao, float(valor), categoria, datetime.now().date()))
            conn.commit()

    # ===== PEGAR RENDA =====
    cursor.execute("SELECT renda_mensal FROM usuarios WHERE id=%s", (usuario_id,))
    renda_mensal = float(cursor.fetchone()["renda_mensal"] or 0)

    # ===== TOTAL GASTOS =====
    cursor.execute("SELECT SUM(valor) AS total FROM gastos WHERE usuario_id=%s", (usuario_id,))
    total_gastos = float(cursor.fetchone()["total"] or 0)

    saldo = renda_mensal - total_gastos

    # ===== RESUMO POR CATEGORIA =====
    cursor.execute("""
        SELECT categoria, SUM(valor) AS total
        FROM gastos
        WHERE usuario_id=%s
        GROUP BY categoria
    """, (usuario_id,))

    resumo_categoria = [(row["categoria"], float(row["total"])) for row in cursor.fetchall()]

    # ===== EVOLUÇÃO MENSAL =====
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

    conn.close()

    return render_template(
        "dashboard.html",
        nome=session["nome"],
        renda_mensal=renda_mensal,
        saldo=saldo,
        resumo_categoria=resumo_categoria,
        evolucao_mensal=evolucao_mensal
    )


# ================= CRIAR COLUNA AUTOMÁTICO =================
@app.route("/criar_coluna")
def criar_coluna():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS renda_mensal NUMERIC;")
    conn.commit()
    conn.close()
    return "Coluna criada com sucesso!"


# ================= TESTE =================
@app.route("/teste")
def teste():
    return "Servidor funcionando!"


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")