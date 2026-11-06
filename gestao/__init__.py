import os
import secrets
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flask import Flask, abort, request, session
from sqlalchemy.pool import NullPool

from .extensions import db


def normalizar_db_url(uri):
    """Ajusta a URL do Postgres: esquema 'postgresql://' e remove parâmetros
    que o psycopg2 não aceita (ex.: 'supa=...' da integração Supabase/Vercel)."""
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    partes = urlsplit(uri)
    if partes.query:
        query = [(k, v) for k, v in parse_qsl(partes.query) if k != "supa"]
        uri = urlunsplit(partes._replace(query=urlencode(query)))
    return uri


def create_app(config=None):
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:  # pragma: no cover
        pass

    app = Flask(__name__)
    uri = (os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
           or "sqlite:///local.db")
    uri = normalizar_db_url(uri)

    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-insecure"),
        SQLALCHEMY_DATABASE_URI=uri,
        SUPABASE_URL=os.environ.get("SUPABASE_URL", ""),
        SUPABASE_ANON_KEY=(os.environ.get("SUPABASE_ANON_KEY")
                           or os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")),
        PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 7,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=bool(os.environ.get("VERCEL")),
        LOGIN_DISABLED=False,
    )
    if config:
        app.config.update(config)

    if os.environ.get("VERCEL") and app.config["SECRET_KEY"] == "dev-insecure":
        raise RuntimeError("Defina SECRET_KEY nas variáveis de ambiente da Vercel.")

    if os.environ.get("VERCEL") and not app.config["SQLALCHEMY_DATABASE_URI"].startswith(
            "postgresql"):
        raise RuntimeError("Defina DATABASE_URL (string do Transaction pooler do Supabase, "
                           "porta 6543) nas variáveis de ambiente da Vercel.")

    # Serverless: sem pool persistente de conexões (usa o pooler do Supabase).
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"poolclass": NullPool}

    db.init_app(app)

    from . import models  # noqa: F401
    from .auth import bp as auth_bp
    from .crud import bp as crud_bp
    from .routes.main import bp as main_bp
    from .formatting import register_filters

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(crud_bp)
    register_filters(app)

    def csrf_token():
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_hex(16)
        return session["_csrf"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def csrf_protect():
        if request.method == "POST" and not app.config.get("TESTING"):
            sent = request.form.get("_csrf", "")
            if not secrets.compare_digest(session.get("_csrf", ""), sent):
                abort(400)

    return app
