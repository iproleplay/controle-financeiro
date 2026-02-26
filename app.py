from flask import Flask
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "teste")

@app.route("/")
def home():
    return "App principal funcionando"

@app.route("/teste-banco")
def teste_banco():
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor

        DATABASE_URL = os.environ.get("DATABASE_URL")

        if not DATABASE_URL:
            return "DATABASE_URL não configurada"

        conn = psycopg2.connect(
            DATABASE_URL,
            cursor_factory=RealDictCursor,
            connect_timeout=5
        )
        conn.close()

        return "Banco conectou com sucesso"

    except Exception as e:
        return f"Erro banco: {e}"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)