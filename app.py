from flask import Flask, g, render_template, request, redirect, url_for, session, jsonify, flash
import sqlite3, os
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data.db"
SECRET_KEY = os.environ.get("CC_SECRET", "dev-secret-key")

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = SECRET_KEY
app.config['DATABASE'] = str(DB_PATH)
@app.context_processor
def inject_now():
    return {'now': datetime.now}

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
    schema_file = BASE_DIR / 'schema.sql'
    if not schema_file.exists():
        raise FileNotFoundError("schema.sql not found in project directory.")
    with open(schema_file, 'r') as f:
        schema = f.read()
    db = get_db()
    db.executescript(schema)
    db.commit()


@app.route('/init')
def init():
    init_db()
    session.clear()
    return "Database initialized. Go to /"


@app.route('/join', methods=['GET', 'POST'])
def join():
    if request.method == 'POST':
        user_name = request.form.get('user_name', '').strip()
        group_code = request.form.get('group_code', '').strip().lower()

        # Check for empty name
        if not user_name:
            flash("Please enter your name.", "error")
            return render_template('join.html', user_name=user_name)

        # Check for correct group code
        if group_code != "saywards":
            flash("Incorrect group code. Please try again.", "error")
            return render_template('join.html', user_name=user_name)

        # Successful login
        session['user_name'] = user_name
        return redirect(url_for('cottages'))

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
    cottages = db.execute("SELECT * FROM cottages ORDER BY votes DESC").fetchall()
    return render_template('list.html', cottages=cottages)


@app.route('/cottage/<int:cottage_id>', methods=['GET', 'POST'])
def cottage_detail(cottage_id):
    db = get_db()
    if request.method == 'POST':
        author = session.get('user_name', 'Guest')
        text = request.form.get('comment', '').strip()
        if text:
            db.execute("INSERT INTO comments (cottage_id, author, text) VALUES (?, ?, ?)",
                       (cottage_id, author, text))
            db.commit()
            flash('Comment posted')
        return redirect(url_for('cottage_detail', cottage_id=cottage_id))

    cottage = db.execute("SELECT * FROM cottages WHERE id = ?", (cottage_id,)).fetchone()
    if not cottage:
        return "Not found", 404

    comments = db.execute(
        "SELECT * FROM comments WHERE cottage_id = ? ORDER BY created_at DESC", (cottage_id,)
    ).fetchall()

    votes = db.execute(
        "SELECT id, user_name, voted_at FROM votes WHERE cottage_id = ? ORDER BY voted_at DESC", (cottage_id,)
    ).fetchall()

    return render_template('details.html', c=cottage, comments=comments, votes=votes)


@app.route('/add', methods=['GET', 'POST'])
def add_cottage():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        location = request.form.get('location', '').strip()
        price = request.form.get('price', '').strip()
        beds = int(request.form.get('beds') or 1)
        dogs = 1 if request.form.get('dogs', '') == 'yes' else 0
        image = request.form.get('image', '').strip()
        url = request.form.get('url', '').strip()
        description = request.form.get('description', '').strip()
        submitted_by = session.get('user_name', 'Guest')
        
        # Get the new boolean fields
        hottub = int(request.form.get('hottub', '0'))
        secure_garden = int(request.form.get('secure_garden', '0'))
        ev_charging = int(request.form.get('ev_charging', '0'))
        parking = int(request.form.get('parking', '0'))
        log_burner = int(request.form.get('log_burner', '0'))
        high_chair = int(request.form.get('high_chair', '0'))
        cot = int(request.form.get('cot', '0'))
        
        db = get_db()
        db.execute(
            "INSERT INTO cottages (name, location, price, beds, dogs_allowed, image, url, description, "
            "submitted_by, hottub, secure_garden, ev_charging, parking, log_burner, high_chair, cot) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, location, price, beds, dogs, image, url, description, submitted_by, 
             hottub, secure_garden, ev_charging, parking, log_burner, high_chair, cot)
        )
        db.commit()
        flash('Cottage suggestion added')
        return redirect(url_for('cottages'))
    return render_template('add.html')


@app.route('/vote/<int:cottage_id>', methods=['POST'])
def vote(cottage_id):
    db = get_db()
    voted = session.get('voted', [])

    if cottage_id in voted:
        row = db.execute("SELECT votes FROM cottages WHERE id = ?", (cottage_id,)).fetchone()
        return jsonify({'status': 'already voted', 'votes': row['votes']}), 400

    # Update cottage vote count
    db.execute("UPDATE cottages SET votes = votes + 1 WHERE id = ?", (cottage_id,))
    db.commit()

    # Record who voted and when
    user_name = session.get('user_name', 'Guest')
    voted_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.execute(
        "INSERT INTO votes (cottage_id, user_name, voted_at) VALUES (?, ?, ?)",
        (cottage_id, user_name, voted_at)
    )
    db.commit()

    # Fetch new vote count
    row = db.execute("SELECT votes FROM cottages WHERE id = ?", (cottage_id,)).fetchone()
    new_count = row['votes']

    # Track in session
    voted.append(cottage_id)
    session['voted'] = voted

    return jsonify({'status': 'ok', 'votes': new_count})


@app.route('/edit/<int:cottage_id>', methods=['GET', 'POST'])
def edit_cottage(cottage_id):
    db = get_db()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        location = request.form.get('location', '').strip()
        price = request.form.get('price', '').strip()
        beds = int(request.form.get('beds') or 1)
        dogs = 1 if request.form.get('dogs', '') == 'yes' else 0
        image = request.form.get('image', '').strip()
        url = request.form.get('url', '').strip()
        description = request.form.get('description', '').strip()
        
        # Get the boolean fields
        hottub = int(request.form.get('hottub', '0'))
        secure_garden = int(request.form.get('secure_garden', '0'))
        ev_charging = int(request.form.get('ev_charging', '0'))
        parking = int(request.form.get('parking', '0'))
        log_burner = int(request.form.get('log_burner', '0'))
        high_chair = int(request.form.get('high_chair', '0'))
        cot = int(request.form.get('cot', '0'))
        
        db.execute(
            """UPDATE cottages SET 
                name=?, location=?, price=?, beds=?, dogs_allowed=?, 
                image=?, url=?, description=?, hottub=?, secure_garden=?,
                ev_charging=?, parking=?, log_burner=?, high_chair=?, cot=?
                WHERE id=?""",
            (name, location, price, beds, dogs, image, url, description,
             hottub, secure_garden, ev_charging, parking, log_burner, 
             high_chair, cot, cottage_id)
        )
        db.commit()
        flash('Cottage details updated')
        return redirect(url_for('cottage_detail', cottage_id=cottage_id))

    cottage = db.execute("SELECT * FROM cottages WHERE id = ?", (cottage_id,)).fetchone()
    if not cottage:
        return "Not found", 404
    return render_template('edit.html', cottage=cottage)


@app.route('/delete/<int:cottage_id>', methods=['POST'])
def delete_cottage(cottage_id):
    db = get_db()
    # Remove related data first
    db.execute("DELETE FROM comments WHERE cottage_id = ?", (cottage_id,))
    db.execute("DELETE FROM votes WHERE cottage_id = ?", (cottage_id,))
    # Remove the cottage itself
    db.execute("DELETE FROM cottages WHERE id = ?", (cottage_id,))
    db.commit()
    flash('Cottage deleted')
    return redirect(url_for('cottages'))


# --- Comment edit/delete routes ---
@app.route('/comment/edit/<int:comment_id>', methods=['POST'])
def edit_comment(comment_id):
    db = get_db()
    text = request.form.get('text', '').strip()
    # find cottage_id for redirect
    row = db.execute("SELECT cottage_id FROM comments WHERE id = ?", (comment_id,)).fetchone()
    if not row:
        flash('Comment not found')
        return redirect(url_for('cottages'))
    cottage_id = row['cottage_id']
    if text:
        author = session.get('user_name', 'Guest')
        db.execute("UPDATE comments SET text = ?, author = ? WHERE id = ?", (text, author, comment_id))
        db.commit()
        flash('Comment updated')
    return redirect(url_for('cottage_detail', cottage_id=cottage_id))


@app.route('/comment/delete/<int:comment_id>', methods=['POST'])
def delete_comment(comment_id):
    db = get_db()
    row = db.execute("SELECT cottage_id FROM comments WHERE id = ?", (comment_id,)).fetchone()
    if not row:
        flash('Comment not found')
        return redirect(url_for('cottages'))
    cottage_id = row['cottage_id']
    db.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    db.commit()
    flash('Comment deleted')
    return redirect(url_for('cottage_detail', cottage_id=cottage_id))


@app.route('/vote/delete/<int:vote_id>', methods=['POST'])
def delete_vote(vote_id):
    db = get_db()
    row = db.execute("SELECT cottage_id FROM votes WHERE id = ?", (vote_id,)).fetchone()
    if not row:
        flash('Vote not found')
        return redirect(url_for('results'))
    cottage_id = row['cottage_id']
    db.execute("DELETE FROM votes WHERE id = ?", (vote_id,))
    # decrement cottage vote count but not below zero
    db.execute("UPDATE cottages SET votes = CASE WHEN votes > 0 THEN votes - 1 ELSE 0 END WHERE id = ?", (cottage_id,))
    db.commit()
    flash('Vote deleted')
    return redirect(url_for('results'))

@app.route('/results')
def results():
    db = get_db()
    cottages = db.execute("SELECT * FROM cottages ORDER BY votes DESC").fetchall()

    cottages_with_votes = []
    for c in cottages:
        voters = db.execute(
            "SELECT id, user_name, voted_at FROM votes WHERE cottage_id = ? ORDER BY voted_at DESC", (c['id'],)
        ).fetchall()
        cottages_with_votes.append(dict(c))
        cottages_with_votes[-1]['voters'] = voters

    # Determine leader
    top = None
    top_votes = 0
    if cottages_with_votes:
        leader = max(cottages_with_votes, key=lambda x: x['votes'])
        top = leader['name']
        top_votes = leader['votes']

    return render_template(
        'results.html',
        cottages=cottages_with_votes,
        top=top,
        top_votes=top_votes
    )
@app.route('/results_data')
def results_data():
    db = get_db()
    cottages = db.execute("SELECT * FROM cottages ORDER BY votes DESC").fetchall()
    cottages_list = []
    for c in cottages:
   

        voters_raw = db.execute(
        "SELECT user_name, voted_at FROM votes WHERE cottage_id = ?",
        (c['id'],)
        ).fetchall()

    voters = []
    for v in voters_raw:
    # Convert the string from SQLite to datetime
        voted_at_dt = datetime.strptime(v['voted_at'], '%Y-%m-%d %H:%M:%S')
        voters.append({
        'user_name': v['user_name'],
        'voted_at': voted_at_dt
    })

        
        cottages_list.append({
            'id': c['id'],
            'name': c['name'],
            'votes': c['votes'],
            'voters': [{'user_name': v['user_name'], 'voted_at': v['voted_at']} for v in voters]
        })
    top = cottages_list[0]['name'] if cottages_list else None
    top_votes = cottages_list[0]['votes'] if cottages_list else 0
    return jsonify({'top': top, 'top_votes': top_votes, 'cottages': cottages_list})


if __name__ == '__main__':
    if not os.path.exists(app.config['DATABASE']):
        with app.app_context():
            init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
