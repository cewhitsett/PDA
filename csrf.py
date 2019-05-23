from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "<a href='http://127.0.0.1:5000/logout'>Free Money</a>"

if __name__ == "__main__":
    app.run(port=8080)
