from flask import Flask, render_template, request, g, redirect, url_for
from flask import make_response
from flask_sqlalchemy import SQLAlchemy
from uuid import uuid4

import random

from datetime import datetime

from flask_oidc import OpenIDConnect
from okta import UsersClient

from config import login_token, def_user, org_url

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:////tmp/pda.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db  = SQLAlchemy(app)

app.config["OIDC_CLIENT_SECRETS"] = "client_secrets.json"
app.config["OIDC_COOKIE_SECURE"] = False
app.config["OIDC_CALLBACK_ROUTE"] = "/oidc/callback"
app.config["OIDC_SCOPES"] = ["openid", "email", "profile"]
app.config["SECRET_KEY"] = "abcd"
app.config["OIDC_ID_TOKEN_COOKIE_NAME"] = "oidc_token"

oidc = OpenIDConnect(app)
okta_client = UsersClient(org_url, login_token)

# Deletes the database. Mostly for testing
def delete_it():
    db.reflect()
    db.drop_all()

# Creates a couple entries in the database for testing.
def create_it():
    db.create_all()

    for i in range(5):
        j = Journal(name=str(i),desc="My {} item".format(i),user=def_user)

        for k in range(random.randint(0,10)):
            p = Entry(title="Head {}".format(k+1), body="Oh man {}".format(k))
            j.entries.append(p)
        db.session.add(j)
    db.session.commit()

# OIDC to get the user that is logged in
@app.before_request
def before_request():
    if oidc.user_loggedin:
        g.user = okta_client.get_user(oidc.user_getfield("sub"))
    else:
        g.user = None

# Catch 404 errors
@app.errorhandler(404)
def pnf(e):
    return redirect(url_for(".page_not_found"))

# Model that represents a journal. A journal is comprised of entries
class Journal(db.Model):
    # ID is uuid to be random
    id  = db.Column('id',db.Text(length=36), default=lambda: str(uuid4()), primary_key=True,unique=True)

    # Name of Journal, A Brief description, owner of journal
    name  = db.Column(db.String(80), nullable=False)
    desc  = db.Column(db.String(280), nullable=True)
    user  = db.Column(db.String(280), nullable=False)

    def __repr__(self):
        return "<Journal {}>".format(self.name)

class Entry(db.Model):
    id    = db.Column('id',db.Text(length=36), default=lambda: str(uuid4()), primary_key=True,unique=True)

    # Title of entry, body of text, date created
    title = db.Column(db.String(80), nullable=True)
    body  = db.Column(db.Text, nullable=False)
    date  = db.Column(db.DateTime, nullable=True,default=datetime.utcnow)


    # Link to corresponding journal. "Needed" for ownership check
    journal_id = db.Column(db.Text, db.ForeignKey("journal.id"),
                           nullable=False)

    journal    = db.relationship("Journal",
                    backref=db.backref("entries",lazy=True))


# Following is a ton of different getters for journals and entries. Basically,
# you can get journal(s), entry(s) or the objects that jinja needs
def get_journal(journal_id):
    journal = Journal.query.filter_by(id=journal_id).first()
    return journal

def get_journals(user_id):
    journals = Journal.query.filter_by(user=user_id).all()
    return journals

def get_journal_obj(js):
    obj = [{"link":j.id, "name":j.name, "desc":j.desc} for j in js]
    return obj

def get_entries(journal_id):
    journal = Journal.query.filter_by(id=journal_id).first()
    return journal.entries

def get_entries_obj(es):
    obj = []
    for entry in es:
        data = {
            "title": entry.title,
            "body":  entry.body,
            "date":  entry.date.strftime("%B %d, %Y at %-I:%M %p"),
            "link":  entry.id
        }
        obj.append(data)
    return obj

def get_entry(entry_id):
    entry = Entry.query.filter_by(id=entry_id).first()
    return entry

def get_entry_obj(entry_id):
    entry = get_entry(entry_id)
    if not entry: return None
    obj = {
        "title": entry.title,
        "body":  entry.body,
        "date":  entry.date.strftime("%B %d, %Y at %-I:%M %p"),
        "link":  entry.id,
        "jid":   entry.journal_id
    }
    return obj


# Url for 404 errors
@app.route("/404")
def page_not_found():
    return render_template("error.html"), 404

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/dashboard")
@oidc.require_login
def dashboard():
    return render_template("dashboard.html")

@app.route("/journals")
@oidc.require_login
def journals():
    user_id = oidc.user_getfield("sub")

    journals = get_journals( user_id )
    journals = get_journal_obj( journals )
    return render_template("journals.html",ls=journals)

def check_user(ident, is_j=True):
    # Get unique user id
    user_id = oidc.user_getfield("sub")

    if not user_id: return True

    # Check if using journal id or a entry id
    if is_j:
        journal = get_journal(ident)
    else:
        entry   = get_entry(ident)

        if not entry: return True

        journal  = get_journal(entry.journal_id)

    if not journal: return True

    if user_id == journal.user:
        return False

    return True

@app.route("/journal/<ident>")
@oidc.require_login
def journal(ident):

    if check_user(ident): return redirect(url_for(".page_not_found"))

    journal = get_journal(ident)
    entries = get_entries(ident)
    entries = get_entries_obj(entries)
    return render_template("journal.html",es=entries,j=journal)

@app.route("/entry/<ident>")
@oidc.require_login
def entry(ident):
    if check_user(ident, False): return redirect(url_for(".page_not_found"))

    ent = get_entry_obj(ident)
    return render_template("entry.html",entry=ent)

@app.route("/login")
@oidc.require_login
def login():
    return redirect(url_for(".dashboard"))

@app.route("/logout")
def logout():
    oidc.logout()
    return redirect(url_for(".index"))


@app.route("/newjournal",methods=["GET","POST"])
@oidc.require_login
def newjournal():
    if request.method == "GET":
        return render_template("form.html",url="/newjournal",data_type="Journal")
    user_id = oidc.user_getfield("sub")

    values = request.form
    j = Journal(name=values["title"],desc=values["body_text"],user=user_id)
    db.session.add(j)
    db.session.commit()
    return redirect(url_for('.journal', ident=j.id))

@app.route("/newentry/<ident>",methods=["GET","POST"])
@oidc.require_login
def newentry(ident):

    if check_user(ident): return redirect(url_for(".page_not_found"))

    if request.method == "GET":
        return render_template("form.html",url="/newentry/"+ident,data_type="Entry")
    user_id = oidc.user_getfield("sub")

    values = request.form
    e = Entry(title=values["title"],body=values["body_text"], journal_id=ident)
    db.session.add(e)
    db.session.commit()
    return redirect(url_for('.entry', ident=e.id))

if __name__ == "__main__":
    app.run(debug=True)
