from flask import Flask, g, render_template, request, redirect, url_for, session, jsonify, flash
import sqlite3, os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data.db"
SECRET_KEY = os.environ.get("CC_SECRET", "dev-secret-key")

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = SECRET_KEY
app.config['DATABASE'] = str(DB_PATH)

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(app.config['DATABASE'])
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    schema = open(BASE_DIR / 'schema.sql').read()
    db = get_db()
    db.executescript(schema)
    db.commit()

@app.route('/init')
def init():
    init_db()
    return "Database initialized. Go to /"

@app.route('/join', methods=['GET','POST'])
def join():
    if request.method == 'POST':
        code = request.form.get('code','').strip()
        name = request.form.get('name','').strip() or 'Guest'
        session['group_code'] = code or 'default'
        session['user_name'] = name
        flash('Joined group as ' + name)
        return redirect(url_for('cottages'))  # Go to main page after login
    
    # Show the join/login screen template
    return render_template('join.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('join'))

@app.route('/')
def index():
    return redirect(url_for('join'))


@app.route('/cottages')
def cottages():
    db = get_db()
    cur = db.execute("SELECT * FROM cottages ORDER BY votes DESC")
    rows = cur.fetchall()
    return render_template('list.html', cottages=rows)

@app.route('/cottage/<int:cottage_id>', methods=['GET','POST'])
def cottage_detail(cottage_id):
    db = get_db()
    if request.method == 'POST':
        author = session.get('user_name','Guest')
        text = request.form.get('comment','').strip()
        if text:
            db.execute("INSERT INTO comments (cottage_id, author, text) VALUES (?,?,?)",
                       (cottage_id, author, text))
            db.commit()
            flash('Comment posted')
        return redirect(url_for('cottage_detail', cottage_id=cottage_id))
    cur = db.execute("SELECT * FROM cottages WHERE id = ?", (cottage_id,))
    cottage = cur.fetchone()
    if not cottage:
        return "Not found", 404
    comments = db.execute("SELECT * FROM comments WHERE cottage_id = ? ORDER BY created_at DESC", (cottage_id,)).fetchall()
    return render_template('details.html', c=cottage, comments=comments)

@app.route('/add', methods=['GET','POST'])
def add_cottage():
    if request.method == 'POST':
        name = request.form.get('name','').strip()
        location = request.form.get('location','').strip()
        price = request.form.get('price','').strip()
        beds = int(request.form.get('beds') or 1)
        dogs = 1 if request.form.get('dogs','') == 'yes' else 0
        image = request.form.get('image','').strip()
        description = request.form.get('description','').strip()
        submitted_by = session.get('user_name','Guest')
        db = get_db()
        db.execute("INSERT INTO cottages (name, location, price, beds, dogs_allowed, image, description, submitted_by) VALUES (?,?,?,?,?,?,?,?)",
                   (name, location, price, beds, dogs, image, description, submitted_by))
        db.commit()
        flash('Cottage suggestion added')
        return redirect(url_for('cottages'))
    return render_template('add.html')

@app.route('/vote/<int:cottage_id>', methods=['POST'])
def vote(cottage_id):
    db = get_db()
    voted = session.get('voted', [])

    if cottage_id in voted:
        # Fetch current votes so UI can still display correct number
        row = db.execute("SELECT votes FROM cottages WHERE id = ?", (cottage_id,)).fetchone()
        return jsonify({'status': 'already voted', 'votes': row['votes']}), 400

    # Perform update
    db.execute("UPDATE cottages SET votes = votes + 1 WHERE id = ?", (cottage_id,))
    db.commit()

    # Fetch new vote count
    row = db.execute("SELECT votes FROM cottages WHERE id = ?", (cottage_id,)).fetchone()
    new_count = row['votes']

    # Track in session
    voted.append(cottage_id)
    session['voted'] = voted

    return jsonify({'status': 'ok', 'vote': new_count})


@app.route('/results')
def results():
    db = get_db()
    rows = db.execute("SELECT * FROM cottages ORDER BY votes DESC").fetchall()
    top = rows[0] if rows else None
    return render_template('results.html', cottages=rows, top=top)

if __name__ == '__main__':
    if not os.path.exists(app.config['DATABASE']):
        with app.app_context():
            init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
