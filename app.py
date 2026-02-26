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

    if not DATABASE_URL:
        print("DATABASE_URL não configurada.")
        return None

    try:
        return psycopg2.connect(
            DATABASE_URL,
            cursor_factory=RealDictCursor,
            connect_timeout=5
        )
    except Exception as e:
        print("Erro ao conectar:", e)
        return None


# ================= GARANTIR COLUNAS =================
def garantir_colunas():
    conn = get_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()

        # Meta percentual
        cursor.execute("""
            ALTER TABLE usuarios
            ADD COLUMN IF NOT EXISTS meta_percentual FLOAT DEFAULT 70;
        """)

        # Tipo de gasto
        cursor.execute("""
            ALTER TABLE gastos
            ADD COLUMN IF NOT EXISTS tipo VARCHAR(20) DEFAULT 'Variável';
        """)

        conn.commit()
        conn.close()

    except Exception as e:
        print("Erro ao criar colunas:", e)


with app.app_context():
    garantir_colunas()


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
            return "Erro conexão"

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
            return "Erro conexão"

        try:
            cursor = conn.cursor()
            senha_hash = generate_password_hash(request.form.get("senha"))

            cursor.execute("""
                INSERT INTO usuarios (nome, email, senha, renda_mensal, role, meta_percentual)
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (
                request.form.get("nome"),
                request.form.get("email"),
                senha_hash,
                0,
                "user",
                70
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
        return "Erro conexão"

    try:
        cursor = conn.cursor()
        usuario_id = session["usuario_id"]

        # ================= FILTRO MÊS/ANO =================
        mes = request.args.get("mes")
        ano = request.args.get("ano")

        filtro_sql = ""
        params = [usuario_id]

        if mes and ano:
            filtro_sql = " AND EXTRACT(MONTH FROM data)=%s AND EXTRACT(YEAR FROM data)=%s "
            params.extend([int(mes), int(ano)])

        # ================= EXCLUIR =================
        if request.args.get("excluir"):
            cursor.execute("""
                DELETE FROM gastos
                WHERE id=%s AND usuario_id=%s
            """, (request.args.get("excluir"), usuario_id))
            conn.commit()
            return redirect("/dashboard")

        # ================= POST =================
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

            if tipo == "meta":
                meta = request.form.get("meta_percentual", 70)
                cursor.execute("""
                    UPDATE usuarios
                    SET meta_percentual=%s
                    WHERE id=%s
                """, (float(meta), usuario_id))
                conn.commit()

            if tipo == "gasto":
                valor = request.form.get("valor")
                categoria = request.form.get("categoria")
                tipo_gasto = request.form.get("tipo_gasto", "Variável")

                if valor:
                    cursor.execute("""
                        INSERT INTO gastos (usuario_id, descricao, valor, categoria, data, tipo)
                        VALUES (%s,%s,%s,%s,%s,%s)
                    """, (
                        usuario_id,
                        categoria,
                        float(valor),
                        categoria,
                        datetime.now().date(),
                        tipo_gasto
                    ))
                    conn.commit()

        # ================= BUSCAR USUÁRIO =================
        cursor.execute("""
            SELECT renda_mensal, meta_percentual
            FROM usuarios WHERE id=%s
        """, (usuario_id,))
        user = cursor.fetchone()

        renda_mensal = float(user["renda_mensal"] or 0)
        meta_percentual = float(user["meta_percentual"] or 70)

        # ================= GASTOS FILTRADOS =================
        cursor.execute(f"""
            SELECT * FROM gastos
            WHERE usuario_id=%s
            {filtro_sql}
            ORDER BY data DESC
        """, tuple(params))
        gastos = cursor.fetchall()

        total_gastos = sum(float(g["valor"]) for g in gastos) if gastos else 0
        saldo = renda_mensal - total_gastos

        # ================= META =================
        meta_valor = renda_mensal * (meta_percentual / 100)
        percentual_usado = (total_gastos / meta_valor * 100) if meta_valor > 0 else 0

        # ================= RESUMO CATEGORIA =================
        cursor.execute(f"""
            SELECT categoria, SUM(valor) as total
            FROM gastos
            WHERE usuario_id=%s
            {filtro_sql}
            GROUP BY categoria
        """, tuple(params))
        resumo_categoria = [
            (r["categoria"], float(r["total"])) 
            for r in cursor.fetchall()
        ]

        # ================= RESUMO FIXO VS VARIÁVEL =================
        cursor.execute(f"""
            SELECT 
                COALESCE(tipo, 'Variável') as tipo,
                SUM(valor) as total
            FROM gastos
            WHERE usuario_id=%s
            {filtro_sql}
            GROUP BY COALESCE(tipo, 'Variável')
        """, tuple(params))

        resumo_tipo = [
            (r["tipo"], float(r["total"])) 
            for r in cursor.fetchall()
        ]

        # ================= EVOLUÇÃO MENSAL =================
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
                (f"{meses_pt[row['mes'].month-1]}/{row['mes'].year}",
                 float(row["total"]))
            )

        conn.close()

        return render_template(
            "dashboard.html",
            nome=session["nome"],
            gastos=gastos,
            renda_mensal=renda_mensal,
            saldo=saldo,
            meta_percentual=meta_percentual,
            meta_valor=meta_valor,
            percentual_usado=percentual_usado,
            resumo_categoria=resumo_categoria,
            resumo_tipo=resumo_tipo,
            evolucao_mensal=evolucao_mensal
        )

    except Exception as e:
        return f"Erro dashboard: {e}"


# ================= ADMIN =================
@app.route("/admin")
def admin():

    if session.get("role") != "admin":
        return "Acesso negado."

    conn = get_connection()
    if not conn:
        return "Erro conexão"

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome, email, role FROM usuarios ORDER BY id")
        usuarios = cursor.fetchall()
        conn.close()
        return render_template("admin.html", usuarios=usuarios)

    except Exception as e:
        return f"Erro admin: {e}"


# ================= LOGOUT =================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)