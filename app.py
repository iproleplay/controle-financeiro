from flask import Flask, render_template, request, redirect, session
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise Exception("DATABASE_URL não configurada.")

# ================= CONEXÃO =================
def get_connection():
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor
    )

# ================= CRIAR TABELAS (PRODUÇÃO) =================
def criar_tabelas():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            nome VARCHAR(100),
            email VARCHAR(150) UNIQUE,
            senha TEXT,
            renda_mensal FLOAT DEFAULT 0,
            role VARCHAR(20) DEFAULT 'user',
            meta_percentual FLOAT DEFAULT 70
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gastos (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            descricao TEXT,
            valor FLOAT,
            categoria VARCHAR(100),
            data DATE,
            tipo VARCHAR(20) DEFAULT 'Variável'
        );
    """)

    conn.commit()
    conn.close()

with app.app_context():
    criar_tabelas()

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
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM usuarios WHERE email=%s",
            (request.form.get("email"),)
        )
        user = cursor.fetchone()

        if user and check_password_hash(user["senha"], request.form.get("senha")):
            session["usuario_id"] = user["id"]
            session["nome"] = user["nome"]
            session["role"] = user["role"]
            conn.close()
            return redirect("/dashboard")

        conn.close()
        return "Login inválido"

    return render_template("login.html")

# ================= CADASTRO =================
@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():

    if request.method == "POST":
        conn = get_connection()
        cursor = conn.cursor()

        senha_hash = generate_password_hash(request.form.get("senha"))

        cursor.execute("""
            INSERT INTO usuarios (nome, email, senha)
            VALUES (%s, %s, %s)
        """, (
            request.form.get("nome"),
            request.form.get("email"),
            senha_hash
        ))

        conn.commit()
        conn.close()
        return redirect("/")

    return render_template("cadastro.html")

# ================= DASHBOARD =================
@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():

    if "usuario_id" not in session:
        return redirect("/")

    conn = get_connection()
    cursor = conn.cursor()
    usuario_id = session["usuario_id"]

    if request.method == "POST":
        tipo = request.form.get("tipo")

        if tipo == "gasto":
            cursor.execute("""
                INSERT INTO gastos 
                (usuario_id, descricao, valor, categoria, data, tipo)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                usuario_id,
                request.form.get("categoria"),
                float(request.form.get("valor")),
                request.form.get("categoria"),
                datetime.now().date(),
                request.form.get("tipo_gasto")
            ))
            conn.commit()

    cursor.execute("SELECT * FROM usuarios WHERE id=%s", (usuario_id,))
    user = cursor.fetchone()

    renda_mensal = float(user["renda_mensal"] or 0)

    cursor.execute("""
        SELECT * FROM gastos 
        WHERE usuario_id=%s 
        ORDER BY data DESC
    """, (usuario_id,))
    gastos = cursor.fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        nome=session["nome"],
        gastos=gastos,
        renda_mensal=renda_mensal,
        saldo=0,
        meta_percentual=70,
        meta_valor=0,
        percentual_usado=0,
        resumo_categoria=[],
        resumo_tipo=[],
        evolucao_mensal=[]
    )

# ================= LOGOUT =================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    app.run(debug=True)