from flask import Flask, render_template, request, redirect, session
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "seguro123")

# ================= CONEXÃO =================
def get_connection():
    DATABASE_URL = os.environ.get("DATABASE_URL")
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor,
        connect_timeout=5
    )

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

            cursor.execute(
                "SELECT * FROM usuarios WHERE email=%s",
                (request.form.get("email"),)
            )
            user = cursor.fetchone()
            conn.close()

            if user and check_password_hash(user["senha"], request.form.get("senha")):
                session["usuario_id"] = user["id"]
                session["nome"] = user["nome"]
                return redirect("/dashboard")
            else:
                return "Login inválido"

        except Exception as e:
            return f"Erro login: {e}"

    return render_template("login.html")

# ================= CADASTRO =================
@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        try:
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

        except Exception as e:
            return f"Erro cadastro: {e}"

    return render_template("cadastro.html")

# ================= DASHBOARD =================
@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "usuario_id" not in session:
        return redirect("/")

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # TRATAR POST
        if request.method == "POST":
            tipo = request.form.get("tipo")

            # SALVAR RENDA
            if tipo == "renda":
                renda = request.form.get("renda", 0)
                cursor.execute("""
                    UPDATE usuarios
                    SET renda_mensal=%s
                    WHERE id=%s
                """, (float(renda), session["usuario_id"]))
                conn.commit()

            # SALVAR GASTO
            if tipo == "gasto":
                descricao = request.form.get("descricao")
                valor = request.form.get("valor")
                categoria = request.form.get("categoria")

                if descricao and valor:
                    cursor.execute("""
                        INSERT INTO gastos (usuario_id, descricao, valor, categoria, data)
                        VALUES (%s,%s,%s,%s,%s)
                    """, (
                        session["usuario_id"],
                        descricao,
                        float(valor),
                        categoria,
                        datetime.now().date()
                    ))
                    conn.commit()

        # BUSCAR RENDA
        cursor.execute("""
            SELECT renda_mensal FROM usuarios WHERE id=%s
        """, (session["usuario_id"],))
        renda_row = cursor.fetchone()
        renda_mensal = float(renda_row["renda_mensal"] or 0) if renda_row else 0

        # BUSCAR GASTOS
        cursor.execute("""
            SELECT * FROM gastos
            WHERE usuario_id=%s
            ORDER BY data DESC
        """, (session["usuario_id"],))
        gastos = cursor.fetchall()

        total_gastos = sum(float(g["valor"]) for g in gastos) if gastos else 0
        saldo = renda_mensal - total_gastos

        conn.close()

        return render_template(
            "dashboard.html",
            nome=session["nome"],
            gastos=gastos,
            renda_mensal=renda_mensal,
            saldo=saldo,
            percentual=0,
            resumo_categoria=[],
            evolucao_mensal=[]
        )

    except Exception as e:
        return f"Erro dashboard: {e}"

# ================= LOGOUT =================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ================= START =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)