from flask import Flask, render_template, request, redirect, session, flash
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
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

@app.before_request
def init_db():
    if not hasattr(app, "db_init"):
        criar_tabelas()
        app.db_init = True

# ================= FILTRO BRL =================
@app.template_filter("brl")
def brl(valor):
    try:
        return "R$ {:,.2f}".format(float(valor)).replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "R$ 0,00"

# ================= LOGIN =================
@app.route("/", methods=["GET","POST"])
def login():
    if request.method == "POST":
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

    return render_template("login.html")

# ================= DASHBOARD =================
@app.route("/dashboard", methods=["GET","POST"])
def dashboard():

    if "usuario_id" not in session:
        return redirect("/")

    usuario_id = session["usuario_id"]
    conn = get_connection()
    cursor = conn.cursor()

    # ===== POST =====
    if request.method == "POST":

        tipo = request.form.get("tipo")

        if tipo == "renda":
            nova_renda = request.form.get("renda_mensal")
            if nova_renda:
                cursor.execute(
                    "UPDATE usuarios SET renda_mensal=%s WHERE id=%s",
                    (float(nova_renda), usuario_id)
                )

        elif tipo == "meta":
            nova_meta = request.form.get("meta_percentual")
            if nova_meta:
                cursor.execute(
                    "UPDATE usuarios SET meta_percentual=%s WHERE id=%s",
                    (float(nova_meta), usuario_id)
                )

        elif tipo == "gasto":
            valor = request.form.get("valor")
            categoria = request.form.get("categoria")
            tipo_gasto = request.form.get("tipo_gasto")

            if valor and categoria and tipo_gasto:
                cursor.execute("""
                    INSERT INTO gastos (usuario_id, valor, categoria, data, tipo)
                    VALUES (%s,%s,%s,%s,%s)
                """, (
                    usuario_id,
                    float(valor),
                    categoria,
                    datetime.now().date(),
                    tipo_gasto
                ))

        conn.commit()
        return redirect("/dashboard")

    # ===== EXCLUIR =====
    excluir = request.args.get("excluir")
    if excluir:
        cursor.execute(
            "DELETE FROM gastos WHERE id=%s AND usuario_id=%s",
            (excluir, usuario_id)
        )
        conn.commit()
        return redirect("/dashboard")

    # ===== FILTRO =====
    mes = request.args.get("mes")
    ano = request.args.get("ano")

    filtro = "WHERE usuario_id=%s"
    params = [usuario_id]

    if mes:
        filtro += " AND EXTRACT(MONTH FROM data)=%s"
        params.append(mes)

    if ano:
        filtro += " AND EXTRACT(YEAR FROM data)=%s"
        params.append(ano)

    cursor.execute(f"SELECT * FROM gastos {filtro} ORDER BY data DESC", tuple(params))
    gastos = cursor.fetchall()

    # ===== DADOS USUARIO =====
    cursor.execute("SELECT * FROM usuarios WHERE id=%s", (usuario_id,))
    user = cursor.fetchone()

    renda = float(user["renda_mensal"] or 0)
    total = sum(float(g["valor"]) for g in gastos)
    saldo = renda - total

    meta_percentual = float(user["meta_percentual"] or 0)
    meta_valor = renda * (meta_percentual / 100)
    percentual_usado = (total / meta_valor * 100) if meta_valor > 0 else 0

    # ===== GRÁFICOS (TUPLAS) =====

    cursor.execute(f"""
        SELECT categoria, SUM(valor)
        FROM gastos {filtro}
        GROUP BY categoria
    """, tuple(params))
    resumo_categoria = cursor.fetchall()

    cursor.execute(f"""
        SELECT tipo, SUM(valor)
        FROM gastos {filtro}
        GROUP BY tipo
    """, tuple(params))
    resumo_tipo = cursor.fetchall()

    cursor.execute("""
        SELECT TO_CHAR(data,'MM/YYYY'), SUM(valor)
        FROM gastos
        WHERE usuario_id=%s
        GROUP BY 1
        ORDER BY 1
    """, (usuario_id,))
    evolucao_mensal = cursor.fetchall()

    conn.close()

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

if __name__ == "__main__":
    app.run(debug=True)