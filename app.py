from flask import Flask, render_template, request, redirect, session
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chave_padrao_segura")

DATABASE_URL = os.environ.get("DATABASE_URL")


# ================= CONEXÃO SEGURA =================
def get_connection():
    if not DATABASE_URL:
        raise Exception("DATABASE_URL não configurada no Render.")
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    except Exception as e:
        print("Erro ao conectar no banco:", e)
        raise e


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
        email = request.form.get("email")
        senha = request.form.get("senha")

        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM usuarios WHERE email=%s", (email,))
            user = cursor.fetchone()
            conn.close()
        except Exception as e:
            return f"Erro ao conectar no banco: {e}"

        if user and check_password_hash(user["senha"], senha):
            session["usuario_id"] = user["id"]
            session["nome"] = user["nome"]
            return redirect("/dashboard")
        else:
            return "Login inválido"

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
    except Exception as e:
        return f"Erro banco: {e}"

    # FILTROS
    mes_filtro = request.args.get("mes")
    categoria_filtro = request.args.get("categoria")

    filtro_sql = "WHERE usuario_id=%s"
    params = [usuario_id]

    if mes_filtro:
        filtro_sql += " AND EXTRACT(MONTH FROM data)=%s"
        params.append(mes_filtro)

    if categoria_filtro:
        filtro_sql += " AND categoria=%s"
        params.append(categoria_filtro)

    # SALVAR RENDA
    if request.method == "POST" and request.form.get("tipo") == "renda":
        renda = request.form.get("renda")
        cursor.execute(
            "UPDATE usuarios SET renda_mensal=%s WHERE id=%s",
            (float(renda), usuario_id),
        )
        conn.commit()

    # SALVAR GASTO
    if request.method == "POST" and request.form.get("tipo") == "gasto":
        cursor.execute(
            """
            INSERT INTO gastos (usuario_id, descricao, valor, categoria, data)
            VALUES (%s,%s,%s,%s,%s)
            """,
            (
                usuario_id,
                request.form["descricao"],
                float(request.form["valor"]),
                request.form["categoria"],
                datetime.now().date(),
            ),
        )
        conn.commit()

    # EXCLUIR
    if request.args.get("excluir"):
        cursor.execute(
            "DELETE FROM gastos WHERE id=%s AND usuario_id=%s",
            (request.args.get("excluir"), usuario_id),
        )
        conn.commit()
        conn.close()
        return redirect("/dashboard")

    # RENDA
    cursor.execute("SELECT renda_mensal FROM usuarios WHERE id=%s", (usuario_id,))
    renda_row = cursor.fetchone()
    renda_mensal = float(renda_row["renda_mensal"] or 0) if renda_row else 0

    # GASTOS
    cursor.execute(f"SELECT * FROM gastos {filtro_sql} ORDER BY data DESC", params)
    gastos = cursor.fetchall()

    total_gastos = sum([float(g["valor"]) for g in gastos]) if gastos else 0
    saldo = renda_mensal - total_gastos
    percentual = (total_gastos / renda_mensal * 100) if renda_mensal > 0 else 0

    # RESUMO CATEGORIA
    cursor.execute(
        f"""
        SELECT categoria, SUM(valor) as total
        FROM gastos {filtro_sql}
        GROUP BY categoria
        """,
        params,
    )
    resumo_categoria = [
        (r["categoria"], float(r["total"])) for r in cursor.fetchall()
    ]

    # EVOLUÇÃO MENSAL
    cursor.execute(
        """
        SELECT DATE_TRUNC('month', data) as mes, SUM(valor) as total
        FROM gastos
        WHERE usuario_id=%s
        GROUP BY mes
        ORDER BY mes
        """,
        (usuario_id,),
    )

    evolucao_mensal = []
    meses_pt = [
        "Jan",
        "Fev",
        "Mar",
        "Abr",
        "Mai",
        "Jun",
        "Jul",
        "Ago",
        "Set",
        "Out",
        "Nov",
        "Dez",
    ]

    for row in cursor.fetchall():
        evolucao_mensal.append(
            (f"{meses_pt[row['mes'].month-1]}/{row['mes'].year}", float(row["total"]))
        )

    conn.close()

    return render_template(
        "dashboard.html",
        nome=session["nome"],
        renda_mensal=renda_mensal,
        saldo=saldo,
        percentual=percentual,
        gastos=gastos,
        resumo_categoria=resumo_categoria,
        evolucao_mensal=evolucao_mensal,
    )


# ================= LOGOUT =================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")