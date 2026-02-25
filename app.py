from flask import Flask, render_template, request, redirect, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# ================= APP =================
app = Flask(__name__)
app.secret_key = "segredo_super_forte"


# ================= FILTRO BRL =================
@app.template_filter("brl")
def brl(valor):
    try:
        return "R$ {:,.2f}".format(valor).replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "R$ 0,00"


# ================= CRIAR BANCO =================
def criar_banco():
    conn = sqlite3.connect("financeiro.db")
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT,
        email TEXT UNIQUE,
        senha TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS configuracoes (
        usuario_id INTEGER PRIMARY KEY,
        salario REAL,
        meta REAL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS gastos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER,
        descricao TEXT,
        valor REAL,
        categoria TEXT,
        data TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS prioridades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER,
        nome TEXT,
        valor REAL
    )
    """)

    conn.commit()
    conn.close()


criar_banco()


# ================= CADASTRO =================
@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        nome = request.form["nome"]
        email = request.form["email"]
        senha = generate_password_hash(request.form["senha"])

        conn = sqlite3.connect("financeiro.db")
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO usuarios (nome, email, senha) VALUES (?, ?, ?)",
                (nome, email, senha)
            )
            conn.commit()
            conn.close()
            return redirect("/")
        except:
            conn.close()
            return "Email já cadastrado"

    return render_template("cadastro.html")


# ================= LOGIN =================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        senha = request.form["senha"]

        conn = sqlite3.connect("financeiro.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome, senha FROM usuarios WHERE email=?", (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[2], senha):
            session["usuario_id"] = user[0]
            session["nome"] = user[1]
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

    conn = sqlite3.connect("financeiro.db")
    cursor = conn.cursor()

    cursor.execute("SELECT salario, meta FROM configuracoes WHERE usuario_id=?", (usuario_id,))
    config = cursor.fetchone()

    salario = config[0] if config and config[0] else 0
    meta = config[1] if config and config[1] else 1000

    if request.method == "POST":

        tipo = request.form.get("tipo")

        if tipo == "salario":
            salario = float(request.form["salario"])

            cursor.execute("""
            INSERT INTO configuracoes (usuario_id, salario, meta)
            VALUES (?, ?, ?)
            ON CONFLICT(usuario_id)
            DO UPDATE SET salario=excluded.salario
            """, (usuario_id, salario, meta))
            conn.commit()

        elif tipo == "meta":
            meta = float(request.form["meta"])

            cursor.execute("""
            INSERT INTO configuracoes (usuario_id, salario, meta)
            VALUES (?, ?, ?)
            ON CONFLICT(usuario_id)
            DO UPDATE SET meta=excluded.meta
            """, (usuario_id, salario, meta))
            conn.commit()

        elif tipo == "gasto":
            descricao = request.form["descricao"]
            valor = float(request.form["valor"])
            categoria = request.form["categoria"]
            data_atual = datetime.now().strftime("%Y-%m-%d")

            cursor.execute("""
            INSERT INTO gastos (usuario_id, descricao, valor, categoria, data)
            VALUES (?, ?, ?, ?, ?)
            """, (usuario_id, descricao, valor, categoria, data_atual))
            conn.commit()

        elif tipo == "prioridade":
            nome_p = request.form["nome"]
            valor_p = float(request.form["valor"])

            cursor.execute("""
            INSERT INTO prioridades (usuario_id, nome, valor)
            VALUES (?, ?, ?)
            """, (usuario_id, nome_p, valor_p))
            conn.commit()

    # ================= TOTAIS =================
    cursor.execute("SELECT SUM(valor) FROM gastos WHERE usuario_id=?", (usuario_id,))
    total_gastos = cursor.fetchone()[0] or 0

    cursor.execute("SELECT SUM(valor) FROM prioridades WHERE usuario_id=?", (usuario_id,))
    total_prioridades = cursor.fetchone()[0] or 0

    saldo = salario - total_gastos - total_prioridades

    progresso = min((saldo / meta) * 100, 100) if meta > 0 else 0
    falta = max(meta - saldo, 0)
    meta_atingida = progresso >= 100

    reserva_ideal = salario * 6
    progresso_reserva = min((saldo / reserva_ideal) * 100, 100) if reserva_ideal > 0 else 0

    cursor.execute("""
        SELECT categoria, SUM(valor)
        FROM gastos
        WHERE usuario_id=?
        GROUP BY categoria
    """, (usuario_id,))
    resumo_categoria = cursor.fetchall()

    cursor.execute("""
        SELECT strftime('%m', data), SUM(valor)
        FROM gastos
        WHERE usuario_id=?
        GROUP BY strftime('%m', data)
        ORDER BY strftime('%m', data)
    """, (usuario_id,))
    dados_mensais = cursor.fetchall()

    meses_dict = {
        "01": "Jan", "02": "Fev", "03": "Mar", "04": "Abr",
        "05": "Mai", "06": "Jun", "07": "Jul", "08": "Ago",
        "09": "Set", "10": "Out", "11": "Nov", "12": "Dez"
    }

    evolucao_mensal = [(meses_dict.get(mes, mes), valor) for mes, valor in dados_mensais]

    if len(evolucao_mensal) >= 2:
        variacao_mensal = evolucao_mensal[-1][1] - evolucao_mensal[-2][1]
    else:
        variacao_mensal = 0

    patrimonio = saldo

    conn.close()

    return render_template(
        "dashboard.html",
        nome=session["nome"],
        salario=salario,
        saldo=saldo,
        meta=meta,
        progresso=progresso,
        falta=falta,
        meta_atingida=meta_atingida,
        reserva_ideal=reserva_ideal,
        progresso_reserva=progresso_reserva,
        resumo_categoria=resumo_categoria,
        evolucao_mensal=evolucao_mensal,
        variacao_mensal=variacao_mensal,
        patrimonio=patrimonio,
        total_prioridades=total_prioridades
    )


# ================= PRIORIDADES =================
@app.route("/prioridades", methods=["GET", "POST"])
def prioridades():

    if "usuario_id" not in session:
        return redirect("/")

    usuario_id = session["usuario_id"]
    conn = sqlite3.connect("financeiro.db")
    cursor = conn.cursor()

    if request.method == "POST":
        nome = request.form["nome"]
        valor = float(request.form["valor"])

        cursor.execute("""
        INSERT INTO prioridades (usuario_id, nome, valor)
        VALUES (?, ?, ?)
        """, (usuario_id, nome, valor))
        conn.commit()

    cursor.execute("""
        SELECT id, nome, valor
        FROM prioridades
        WHERE usuario_id=?
    """, (usuario_id,))

    prioridades_lista = cursor.fetchall()
    total_prioridades = sum(p[2] for p in prioridades_lista)

    conn.close()

    return render_template(
        "prioridades.html",
        nome=session["nome"],
        prioridades=prioridades_lista,
        total_prioridades=total_prioridades
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


if __name__ == "__main__":
    app.run()