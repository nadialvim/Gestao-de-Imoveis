import requests
from flask import (Blueprint, current_app, flash, redirect, render_template,
                   request, session, url_for)

bp = Blueprint("auth", __name__)


@bp.before_app_request
def exigir_login():
    if current_app.config.get("LOGIN_DISABLED"):
        return None
    if request.endpoint in (None, "auth.login", "static"):
        return None
    if not session.get("usuario"):
        return redirect(url_for("auth.login"))
    return None


def _autenticar(email, senha):
    """Valida e-mail/senha no Supabase Auth. Retorna o e-mail ou None."""
    base = current_app.config["SUPABASE_URL"].rstrip("/")
    key = current_app.config["SUPABASE_ANON_KEY"]
    if not base or not key:
        flash("Supabase não configurado (SUPABASE_URL / SUPABASE_ANON_KEY).", "danger")
        return None
    try:
        resp = requests.post(
            f"{base}/auth/v1/token?grant_type=password",
            headers={"apikey": key, "Content-Type": "application/json"},
            json={"email": email, "password": senha},
            timeout=10,
        )
    except requests.RequestException:
        flash("Não foi possível contatar o serviço de login.", "danger")
        return None
    if resp.status_code == 200:
        return resp.json().get("user", {}).get("email", email)

    try:
        corpo = resp.json()
    except ValueError:
        corpo = {}
    codigo = corpo.get("error_code") or corpo.get("code") or ""
    texto = str(corpo.get("msg") or corpo.get("message")
                or corpo.get("error_description") or "")
    current_app.logger.warning("Login recusado pelo Supabase: status=%s codigo=%s msg=%s",
                               resp.status_code, codigo, texto)

    if codigo == "email_not_confirmed":
        flash("E-mail ainda não confirmado no Supabase (Authentication > Users).", "danger")
    elif "api key" in texto.lower() or codigo in ("invalid_api_key", "no_api_key"):
        flash("Chave do Supabase inválida: confira SUPABASE_PUBLISHABLE_KEY e SUPABASE_URL "
              "(devem ser do mesmo projeto).", "danger")
    elif resp.status_code >= 500 or resp.status_code == 404:
        flash("Serviço de login indisponível ou SUPABASE_URL incorreta.", "danger")
    else:
        flash("E-mail ou senha inválidos.", "danger")
    return None


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = _autenticar(
            request.form.get("email", "").strip(), request.form.get("senha", "")
        )
        if usuario:
            session.clear()
            session["usuario"] = usuario
            session.permanent = True
            return redirect(url_for("main.dashboard"))
    return render_template("login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
