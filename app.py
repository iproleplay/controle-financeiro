from flask import Flask, render_template, request, redirect, session
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "seguro123")


# ================= CONEXÃO SEGURA =================
def get_connection():
    DATABASE_URL = os.environ.get("DATABASE_URL")

    if not DATABASE_URL:
        print("DATABASE_URL não configurada.")
        return None

    try:
        conn = psycopg2.connect(
            DATABASE_URL,
            cursor_factory=RealDictCursor,
            connect_timeout=5
        )
        return conn
    except Exception as e:
        print("Erro ao conectar no banco:", e)
        return None


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
        if not conn:
            return "Erro ao conectar ao banco."

        try:
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
                session["role"] = user.get("role", "user")
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

        conn = get_connection()
        if not conn:
            return "Erro ao conectar ao banco."

        try:
            cursor = conn.cursor()
            senha_hash = generate_password_hash(request.form.get("senha"))

            cursor.execute("""
                INSERT INTO usuarios (nome, email, senha, renda_mensal, role)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                request.form.get("nome"),
                request.form.get("email"),
                senha_hash,
                0,
                "user"
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

    conn = get_connection()
    if not conn:
        return "Erro ao conectar ao banco."

    try:
        cursor = conn.cursor()
        usuario_id = session["usuario_id"]

        # EXCLUIR GASTO
        if request.args.get("excluir"):
            cursor.execute("""
                DELETE FROM gastos
                WHERE id=%s AND usuario_id=%s
            """, (
                request.args.get("excluir"),
                usuario_id
            ))
            conn.commit()
            conn.close()
            return redirect("/dashboard")

        # POST
        if request.method == "POST":
            tipo = request.form.get("tipo")

            if tipo == "renda":
                renda = request.form.get("renda", 0)
                cursor.execute("""
                    UPDATE usuarios
                    SET renda_mensal=%s
                    WHERE id=%s
                """, (float(renda), usuario_id))
                conn.commit()

            if tipo == "gasto":
                valor = request.form.get("valor")
                categoria = request.form.get("categoria")

                if valor:
                    cursor.execute("""
                        INSERT INTO gastos (usuario_id, descricao, valor, categoria, data)
                        VALUES (%s,%s,%s,%s,%s)
                    """, (
                        usuario_id,
                        categoria,
                        float(valor),
                        categoria,
                        datetime.now().date()
                    ))
                    conn.commit()

        # RENDA
        cursor.execute("""
            SELECT renda_mensal FROM usuarios WHERE id=%s
        """, (usuario_id,))
        renda_row = cursor.fetchone()
        renda_mensal = float(renda_row["renda_mensal"] or 0) if renda_row else 0

        # GASTOS
        cursor.execute("""
            SELECT * FROM gastos
            WHERE usuario_id=%s
            ORDER BY data DESC
        """, (usuario_id,))
        gastos = cursor.fetchall()

        total_gastos = sum(float(g["valor"]) for g in gastos) if gastos else 0
        saldo = renda_mensal - total_gastos

        # RESUMO CATEGORIA
        cursor.execute("""
            SELECT categoria, SUM(valor) as total
            FROM gastos
            WHERE usuario_id=%s
            GROUP BY categoria
        """, (usuario_id,))

        resumo_categoria = [
            (r["categoria"], float(r["total"]))
            for r in cursor.fetchall()
        ]

        # EVOLUÇÃO MENSAL
        cursor.execute("""
            SELECT DATE_TRUNC('month', data) as mes, SUM(valor) as total
            FROM gastos
            WHERE usuario_id=%s
            GROUP BY mes
            ORDER BY mes
        """, (usuario_id,))

        evolucao_mensal = []
        meses_pt = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]

        for row in cursor.fetchall():
            evolucao_mensal.append(
                (f"{meses_pt[row['mes'].month-1]}/{row['mes'].year}", float(row["total"]))
            )

        conn.close()

        return render_template(
            "dashboard.html",
            nome=session["nome"],
            gastos=gastos,
            renda_mensal=renda_mensal,
            saldo=saldo,
            percentual=0,
            resumo_categoria=resumo_categoria,
            evolucao_mensal=evolucao_mensal
        )

    except Exception as e:
        return f"Erro dashboard: {e}"


# ================= CRIAR ADMIN AUTOMÁTICO =================
@app.route("/criar_admin")
def criar_admin():

    conn = get_connection()
    if not conn:
        return "Erro ao conectar ao banco."

    cursor = conn.cursor()

    cursor.execute("""
        ALTER TABLE usuarios
        ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'user';
    """)

    cursor.execute("""
        UPDATE usuarios
        SET role='admin'
        WHERE email='tigersplayrole@gmail.com';
    """)

    conn.commit()
    conn.close()

    return "Admin configurado com sucesso!"


# ================= ADMIN =================
@app.route("/admin")
def admin():

    if session.get("role") != "admin":
        return "Acesso negado."

    conn = get_connection()
    if not conn:
        return "Erro ao conectar ao banco."

    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, nome, email, role
        FROM usuarios
        ORDER BY id
    """)

    usuarios = cursor.fetchall()
    conn.close()

    return render_template("admin.html", usuarios=usuarios)


# ================= LOGOUT =================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")