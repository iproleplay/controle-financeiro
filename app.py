from flask import Flask, render_template, request, redirect, session, flash
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "fallback_secret")

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise Exception("DATABASE_URL não configurada.")

# ================= CONEXÃO =================
def get_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# ================= CRIAR TABELAS =================
def criar_tabelas():
    try:
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
                valor FLOAT,
                categoria VARCHAR(100),
                data DATE,
                tipo VARCHAR(20)
            );
        """)

        conn.commit()
        conn.close()

    except Exception as e:
        print("Erro criando tabelas:", e)

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
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM usuarios WHERE email=%s", (request.form["email"],))
            user = cursor.fetchone()
            conn.close()

            if user and check_password_hash(user["senha"], request.form["senha"]):
                session["usuario_id"] = user["id"]
                session["nome"] = user["nome"]
                session["role"] = user["role"]
                return redirect("/dashboard")

            flash("Login inválido", "error")

        except Exception as e:
            return f"Erro login: {e}"

    return render_template("login.html")

# ================= DASHBOARD =================
@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():

    if "usuario_id" not in session:
        return redirect("/")

    usuario_id = session["usuario_id"]

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # ===== POST =====
        if request.method == "POST":

            tipo = request.form.get("tipo")

            if tipo == "renda":
                cursor.execute(
                    "UPDATE usuarios SET renda_mensal=%s WHERE id=%s",
                    (float(request.form["renda_mensal"]), usuario_id)
                )

            elif tipo == "meta":
                cursor.execute(
                    "UPDATE usuarios SET meta_percentual=%s WHERE id=%s",
                    (float(request.form["meta_percentual"]), usuario_id)
                )

            elif tipo == "gasto":
                cursor.execute("""
                    INSERT INTO gastos (usuario_id, valor, categoria, data, tipo)
                    VALUES (%s,%s,%s,%s,%s)
                """, (
                    usuario_id,
                    float(request.form["valor"]),
                    request.form["categoria"],
                    datetime.now().date(),
                    request.form["tipo_gasto"]
                ))

            conn.commit()
            conn.close()
            return redirect("/dashboard")

        # ===== BUSCAR DADOS =====
        cursor.execute("SELECT * FROM gastos WHERE usuario_id=%s ORDER BY data DESC", (usuario_id,))
        gastos = cursor.fetchall()

        cursor.execute("SELECT * FROM usuarios WHERE id=%s", (usuario_id,))
        user = cursor.fetchone()

        renda = float(user["renda_mensal"] or 0)
        total = sum(float(g["valor"]) for g in gastos)
        saldo = renda - total

        meta_percentual = float(user["meta_percentual"] or 0)
        meta_valor = renda * (meta_percentual / 100)
        percentual_usado = (total / meta_valor * 100) if meta_valor > 0 else 0

        # ===== GRÁFICOS CONVERTENDO PARA TUPLA =====

        cursor.execute("""
            SELECT categoria, SUM(valor) as total
            FROM gastos
            WHERE usuario_id=%s
            GROUP BY categoria
        """, (usuario_id,))
        dados_cat = cursor.fetchall()
        resumo_categoria = [(d["categoria"], float(d["total"])) for d in dados_cat]

        cursor.execute("""
            SELECT tipo, SUM(valor) as total
            FROM gastos
            WHERE usuario_id=%s
            GROUP BY tipo
        """, (usuario_id,))
        dados_tipo = cursor.fetchall()
        resumo_tipo = [(d["tipo"], float(d["total"])) for d in dados_tipo]

        cursor.execute("""
            SELECT TO_CHAR(data,'MM/YYYY') as mes, SUM(valor) as total
            FROM gastos
            WHERE usuario_id=%s
            GROUP BY mes
            ORDER BY mes
        """, (usuario_id,))
        dados_mes = cursor.fetchall()
        evolucao_mensal = [(d["mes"], float(d["total"])) for d in dados_mes]

        conn.close()

    except Exception as e:
        return f"Erro dashboard: {e}"

    return render_template(
        "dashboard.html",
        nome=session["nome"],
        gastos=gastos,
        renda_mensal=renda,
        saldo=saldo,
        meta_percentual=meta_percentual,
        meta_valor=meta_valor,
        percentual_usado=percentual_usado,
        resumo_categoria=resumo_categoria,
        resumo_tipo=resumo_tipo,
        evolucao_mensal=evolucao_mensal
    )

# ================= LOGOUT =================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ================= RENDER =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)