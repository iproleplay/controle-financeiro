from flask import Flask, render_template, request, redirect, session
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)

# ================= CONFIG PRODUÇÃO =================
app.secret_key = os.environ.get("SECRET_KEY", "fallback_secret")
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise Exception("DATABASE_URL não configurada no Render.")

# ================= CONEXÃO =================
def get_connection():
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor
    )

# ================= CRIAR TABELAS =================
def criar_tabelas():
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:

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

    except Exception as e:
        print("Erro ao criar tabelas:", e)

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
        try:
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT * FROM usuarios WHERE email=%s",
                        (request.form.get("email"),)
                    )
                    user = cursor.fetchone()

                    if user and check_password_hash(user["senha"], request.form.get("senha")):
                        session["usuario_id"] = user["id"]
                        session["nome"] = user["nome"]
                        session["role"] = user["role"]
                        return redirect("/dashboard")

            return "Login inválido"

        except Exception as e:
            return f"Erro no login: {e}"

    return render_template("login.html")

# ================= CADASTRO =================
@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        try:
            with get_connection() as conn:
                with conn.cursor() as cursor:
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

            return redirect("/")

        except Exception as e:
            return f"Erro no cadastro: {e}"

    return render_template("cadastro.html")

# ================= DASHBOARD =================
@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():

    if "usuario_id" not in session:
        return redirect("/")

    usuario_id = session["usuario_id"]

    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:

                if request.method == "POST":

                    # ===== SALVAR RENDA =====
                    if request.form.get("tipo") == "renda":
                        nova_renda = float(request.form.get("renda_mensal") or 0)

                        cursor.execute("""
                            UPDATE usuarios
                            SET renda_mensal = %s
                            WHERE id = %s
                        """, (nova_renda, usuario_id))

                        conn.commit()

                    # ===== SALVAR GASTO =====
                    elif request.form.get("tipo") == "gasto":
                        cursor.execute("""
                            INSERT INTO gastos 
                            (usuario_id, descricao, valor, categoria, data, tipo)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (
                            usuario_id,
                            request.form.get("descricao"),
                            float(request.form.get("valor")),
                            request.form.get("categoria"),
                            datetime.now().date(),
                            request.form.get("tipo_gasto")
                        ))
                        conn.commit()

                # ===== BUSCAR DADOS =====
                cursor.execute("SELECT * FROM usuarios WHERE id=%s", (usuario_id,))
                user = cursor.fetchone()

                cursor.execute("""
                    SELECT * FROM gastos 
                    WHERE usuario_id=%s 
                    ORDER BY data DESC
                """, (usuario_id,))
                gastos = cursor.fetchall()

                # ===== CÁLCULOS =====
                renda_mensal = float(user["renda_mensal"] or 0)
                total_gastos = sum(float(g["valor"]) for g in gastos)
                saldo = renda_mensal - total_gastos

    except Exception as e:
        return f"Erro no dashboard: {e}"

    return render_template(
        "dashboard.html",
        nome=session["nome"],
        gastos=gastos,
        renda_mensal=renda_mensal,
        saldo=saldo,
        meta_percentual=user["meta_percentual"],
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