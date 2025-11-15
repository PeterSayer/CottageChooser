from flask import Flask, g, render_template, request, redirect, url_for, session, jsonify, flash
from markupsafe import Markup
import sqlite3, os
import bleach
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent

# Configure allowed HTML tags and attributes for descriptions
ALLOWED_TAGS = ['p', 'br', 'strong', 'em', 'u', 'ol', 'ul', 'li', 'h1', 'h2', 'h3', 'h4', 'blockquote']
ALLOWED_ATTRIBUTES = {}  # No attributes allowed for security
DB_PATH = BASE_DIR / "data.db"
SECRET_KEY = os.environ.get("CC_SECRET", "dev-secret-key")

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = SECRET_KEY
app.config['DATABASE'] = str(DB_PATH)
# Admin configuration: allow an admin override controlled by env var
# CC_ALLOW_ADMIN_OVERRIDE: 'True'/'1'/'yes' to enable
# CC_ADMIN_USERS: comma-separated list of admin usernames (defaults to 'admin')
app.config['ALLOW_ADMIN_OVERRIDE'] = os.environ.get('CC_ALLOW_ADMIN_OVERRIDE', 'false').lower() in ('1', 'true', 'yes')
app.config['ADMIN_USERS'] = [u.strip() for u in os.environ.get('CC_ADMIN_USERS', 'admin').split(',') if u.strip()]


def sanitize_html(text):
    """Clean and sanitize HTML input"""
    cleaned = bleach.clean(text or '', 
                         tags=ALLOWED_TAGS,
                         attributes=ALLOWED_ATTRIBUTES,
                         strip=True)
    return cleaned


@app.context_processor
def inject_now():
    # expose current time and admin info to templates
    return {
        'now': datetime.now,
        'allow_admin_override': app.config.get('ALLOW_ADMIN_OVERRIDE', False),
        'admin_users': app.config.get('ADMIN_USERS', [])
    }

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(app.config['DATABASE'])
        db.row_factory = sqlite3.Row
    return db

@app.route('/reviews/<int:cottage_id>')
def reviews(cottage_id):
    db = get_db()
    cottage = db.execute(
        'SELECT * FROM cottages WHERE id = ?',
        (cottage_id,)
    ).fetchone()
    if cottage is None:
        return redirect(url_for('cottages'))
    return render_template('reviews.html', cottage=cottage)

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


@app.route('/rate/<int:cottage_id>', methods=['POST'])
def rate_cottage(cottage_id):
    """Submit or update a rating for a cottage (0-10)"""
    current_user = session.get('user_name')
    if not current_user:
        return jsonify({'ok': False, 'message': 'Please log in to rate.'}), 401

    try:
        rating = int(request.form.get('rating', 0))
        if rating < 0 or rating > 10:
            return jsonify({'ok': False, 'message': 'Rating must be 0-10.'}), 400
    except ValueError:
        return jsonify({'ok': False, 'message': 'Invalid rating value.'}), 400

    db = get_db()
    
    # Check if cottage exists
    cottage = db.execute("SELECT id FROM cottages WHERE id = ?", (cottage_id,)).fetchone()
    if not cottage:
        return jsonify({'ok': False, 'message': 'Cottage not found.'}), 404

    # Insert or replace rating (UNIQUE constraint on cottage_id, user_name)
    db.execute(
        """INSERT INTO ratings (cottage_id, user_name, rating, rated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(cottage_id, user_name) 
           DO UPDATE SET rating=excluded.rating, rated_at=excluded.rated_at""",
        (cottage_id, current_user, rating, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    )
    db.commit()

    # Fetch updated stats
    stats = db.execute(
        "SELECT COUNT(*) as count, AVG(rating) as avg, SUM(rating) as total FROM ratings WHERE cottage_id = ?",
        (cottage_id,)
    ).fetchone()

    return jsonify({
        'ok': True,
        'rating': rating,
        'count': stats['count'],
        'average': round(stats['avg'], 1) if stats['avg'] else 0,
        'total': stats['total'] or 0
    })


@app.route('/rating/delete/<int:cottage_id>', methods=['POST'])
def delete_rating(cottage_id):
    """Delete user's own rating for a cottage"""
    current_user = session.get('user_name')
    if not current_user:
        return jsonify({'ok': False, 'message': 'Not logged in.'}), 401

    db = get_db()
    result = db.execute(
        "DELETE FROM ratings WHERE cottage_id = ? AND user_name = ?",
        (cottage_id, current_user)
    )
    db.commit()

    if result.rowcount == 0:
        return jsonify({'ok': False, 'message': 'No rating found to delete.'}), 404

    # Fetch updated stats
    stats = db.execute(
        "SELECT COUNT(*) as count, AVG(rating) as avg, SUM(rating) as total FROM ratings WHERE cottage_id = ?",
        (cottage_id,)
    ).fetchone()

    return jsonify({
        'ok': True,
        'count': stats['count'],
        'average': round(stats['avg'], 1) if stats['avg'] else 0,
        'total': stats['total'] or 0
    })


@app.route('/ratings/<int:cottage_id>')
def cottage_ratings(cottage_id):
    """Show all ratings for a cottage (admin) or just user's own rating"""
    current_user = session.get('user_name')
    if not current_user:
        flash('Please log in to view ratings.')
        return redirect(url_for('join'))

    db = get_db()
    cottage = db.execute("SELECT * FROM cottages WHERE id = ?", (cottage_id,)).fetchone()
    if not cottage:
        flash('Cottage not found.')
        return redirect(url_for('cottages'))

    # Get user's own rating
    my_rating = db.execute(
        "SELECT rating, rated_at FROM ratings WHERE cottage_id = ? AND user_name = ?",
        (cottage_id, current_user)
    ).fetchone()

    # Get aggregate stats
    stats = db.execute(
        "SELECT COUNT(*) as count, AVG(rating) as avg, SUM(rating) as total FROM ratings WHERE cottage_id = ?",
        (cottage_id,)
    ).fetchone()

    # Admins can see all ratings
    all_ratings = []
    if is_admin():
        all_ratings = db.execute(
            "SELECT user_name, rating, rated_at FROM ratings WHERE cottage_id = ? ORDER BY rated_at DESC",
            (cottage_id,)
        ).fetchall()

    return render_template(
        'ratings.html',
        cottage=cottage,
        my_rating=dict(my_rating) if my_rating else None,
        stats=dict(stats),
        all_ratings=[dict(r) for r in all_ratings],
        is_admin=is_admin()
    )

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
    rows = db.execute("SELECT * FROM cottages ORDER BY votes DESC").fetchall()
    cottages_list = [dict(r) for r in rows]
    
    # Add rating stats to each cottage
    for c in cottages_list:
        stats = db.execute(
            "SELECT COUNT(*) as count, AVG(rating) as avg, SUM(rating) as total FROM ratings WHERE cottage_id = ?",
            (c['id'],)
        ).fetchone()
        c['rating_count'] = stats['count']
        c['rating_avg'] = round(stats['avg'], 1) if stats['avg'] else 0
        c['rating_total'] = stats['total'] or 0
        
        # Get current user's rating if logged in
        if session.get('user_name'):
            my_rating = db.execute(
                "SELECT rating FROM ratings WHERE cottage_id = ? AND user_name = ?",
                (c['id'], session['user_name'])
            ).fetchone()
            c['my_rating'] = my_rating['rating'] if my_rating else None
        else:
            c['my_rating'] = None
    
    return render_template('list.html', cottages=cottages_list)


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
    # Require a logged-in user (no anonymous/Guest votes)
    current_user = session.get('user_name')
    if not current_user:
        return jsonify({'status': 'not_logged_in', 'message': 'Please join the voting group to vote.'}), 401

    # Check if this user already has a vote recorded (one vote per user across all cottages)
    existing = db.execute("SELECT id, cottage_id FROM votes WHERE user_name = ?", (current_user,)).fetchone()
    if existing:
        # If they already voted for this cottage, return appropriate message
        if existing['cottage_id'] == cottage_id:
            row = db.execute("SELECT votes FROM cottages WHERE id = ?", (cottage_id,)).fetchone()
            return jsonify({'status': 'already_voted', 'votes': row['votes']}), 400
        else:
            # They voted for a different cottage - instruct them to delete first
            return jsonify({'status': 'already_voted_elsewhere', 'cottage_id': existing['cottage_id'], 'vote_id': existing['id']}), 400

    # Proceed to record the vote
    try:
        db.execute("UPDATE cottages SET votes = votes + 1 WHERE id = ?", (cottage_id,))
        voted_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.execute("INSERT INTO votes (cottage_id, user_name, voted_at) VALUES (?, ?, ?)",
                   (cottage_id, current_user, voted_at))
        db.commit()
    except sqlite3.IntegrityError:
        # Unique constraint on user_name prevented duplicate voting
        row = db.execute("SELECT votes FROM cottages WHERE id = ?", (cottage_id,)).fetchone()
        return jsonify({'status': 'already_voted', 'votes': row['votes']}), 400

    # Fetch new vote count
    row = db.execute("SELECT votes FROM cottages WHERE id = ?", (cottage_id,)).fetchone()
    new_count = row['votes']

    # Update session list for faster client-side feedback (optional)
    voted = session.get('voted', [])
    if cottage_id not in voted:
        voted.append(cottage_id)
        session['voted'] = voted

    return jsonify({'status': 'ok', 'votes': new_count})


@app.route('/edit/<int:cottage_id>', methods=['GET', 'POST'])
def edit_cottage(cottage_id):
    db = get_db()
    # Ensure only the user who submitted the cottage can edit it
    row = db.execute("SELECT submitted_by FROM cottages WHERE id = ?", (cottage_id,)).fetchone()
    if not row:
        flash('Cottage not found')
        return redirect(url_for('cottages'))
    current_user = session.get('user_name', 'Guest')
    if row['submitted_by'] != current_user:
        flash('Not authorized to edit this cottage')
        return redirect(url_for('cottage_detail', cottage_id=cottage_id))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        location = request.form.get('location', '').strip()
        price = request.form.get('price', '').strip()
        beds = int(request.form.get('beds') or 1)
        dogs = 1 if request.form.get('dogs', '') == 'yes' else 0
        image = request.form.get('image', '').strip()
        url = request.form.get('url', '').strip()
        description = request.form.get('description', '').strip()
        
        # Sanitize HTML content
        description = sanitize_html(description)
        
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
    # Only the user who submitted the cottage can delete it
    row = db.execute("SELECT submitted_by FROM cottages WHERE id = ?", (cottage_id,)).fetchone()
    if not row:
        flash('Cottage not found')
        return redirect(url_for('cottages'))
    current_user = session.get('user_name', 'Guest')
    # allow admin override if enabled in config
    is_admin = app.config.get('ALLOW_ADMIN_OVERRIDE', False) and current_user in app.config.get('ADMIN_USERS', [])
    if row['submitted_by'] != current_user and not is_admin:
        flash('Not authorized to delete this cottage')
        return redirect(url_for('cottage_detail', cottage_id=cottage_id))

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
    # find cottage_id and author for redirect and permission check
    row = db.execute("SELECT cottage_id, author FROM comments WHERE id = ?", (comment_id,)).fetchone()
    if not row:
        flash('Comment not found')
        return redirect(url_for('cottages'))
    cottage_id = row['cottage_id']
    comment_author = row['author']
    current_user = session.get('user_name', 'Guest')
    if comment_author != current_user:
        flash('Not authorized to edit this comment')
        return redirect(url_for('cottage_detail', cottage_id=cottage_id))

    if text:
        # Keep the author as the original author
        db.execute("UPDATE comments SET text = ? WHERE id = ?", (text, comment_id))
        db.commit()
        flash('Comment updated')
    return redirect(url_for('cottage_detail', cottage_id=cottage_id))


@app.route('/comment/delete/<int:comment_id>', methods=['POST'])
def delete_comment(comment_id):
    db = get_db()
    row = db.execute("SELECT cottage_id, author FROM comments WHERE id = ?", (comment_id,)).fetchone()
    if not row:
        flash('Comment not found')
        return redirect(url_for('cottages'))
    cottage_id = row['cottage_id']
    comment_author = row['author']
    current_user = session.get('user_name', 'Guest')
    is_admin = app.config.get('ALLOW_ADMIN_OVERRIDE', False) and current_user in app.config.get('ADMIN_USERS', [])
    if comment_author != current_user and not is_admin:
        flash('Not authorized to delete this comment')
        return redirect(url_for('cottage_detail', cottage_id=cottage_id))

    db.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    db.commit()
    flash('Comment deleted')
    return redirect(url_for('cottage_detail', cottage_id=cottage_id))


@app.post("/vote/delete/<int:vote_id>")
def delete_vote(vote_id):
    if not session.get("user_name"):
        return jsonify({"ok": False, "message": "Not logged in"}), 403

    db = get_db()
    row = db.execute("SELECT id, user_name, cottage_id FROM votes WHERE id = ?", (vote_id,)).fetchone()
    if not row:
        return jsonify({"ok": False, "message": "Vote not found"}), 404

    # Use the same admin check everywhere
    if (_norm(row["user_name"]) != _norm(session.get("user_name"))) and (not is_admin()):
        return jsonify({"ok": False, "message": "Not permitted"}), 403

    # If you denormalize votes into cottages.votes, keep this; otherwise remove it.
    db.execute("UPDATE cottages SET votes = CASE WHEN votes > 0 THEN votes - 1 ELSE 0 END WHERE id = ?", (row["cottage_id"],))
    db.execute("DELETE FROM votes WHERE id = ?", (vote_id,))
    db.commit()

    return jsonify({"ok": True, "cottage_id": row["cottage_id"], "vote_id": vote_id})


# Normalize and centralize admin logic
def _norm(name: str) -> str:
    return (name or "").strip().casefold()

def get_admins():
    # CC_ADMINS env var: "Alice,Bob"
    env_list = [_norm(u) for u in os.environ.get("CC_ADMINS", "").split(",") if u.strip()]
    cfg_list = [_norm(u) for u in app.config.get("ADMIN_USERS", [])]
    return set(env_list + cfg_list)

def is_admin():
    return _norm(session.get("user_name")) in get_admins()

@app.context_processor
def inject_admin_flags():
    # Makes `is_admin` available in all templates
    return {"is_admin": is_admin()}

@app.route('/results')
def results():
    db = get_db()
    rows = db.execute('SELECT * FROM cottages ORDER BY votes DESC, name ASC').fetchall()
    cottages = [dict(r) for r in rows]

    # Add rating stats to each cottage
    for c in cottages:
        stats = db.execute(
            "SELECT COUNT(*) as count, AVG(rating) as avg, SUM(rating) as total FROM ratings WHERE cottage_id = ?",
            (c['id'],)
        ).fetchone()
        c['rating_count'] = stats['count']
        c['rating_avg'] = round(stats['avg'], 1) if stats['avg'] else 0
        c['rating_total'] = stats['total'] or 0

    total_votes = db.execute('SELECT COUNT(*) AS c FROM votes').fetchone()['c']

    my_vote = None
    if session.get('user_name'):
        rv = db.execute('SELECT id, cottage_id FROM votes WHERE user_name=?', (session['user_name'],)).fetchone()
        if rv:
            my_vote = dict(rv)

    vote_rows = db.execute('SELECT id, cottage_id, user_name FROM votes').fetchall()
    votes_by_cottage = {}
    for r in vote_rows:
        d = dict(r)
        votes_by_cottage.setdefault(d['cottage_id'], []).append(d)

    return render_template(
        'results.html',
        cottages=cottages,
        total_votes=total_votes,
        my_vote=my_vote,
        is_admin=is_admin(),
        votes_by_cottage=votes_by_cottage
    )

@app.route('/compare')
def compare():
    db = get_db()
    rows = db.execute("SELECT * FROM cottages ORDER BY name").fetchall()
    cottages = [dict(r) for r in rows]
    
    # Add rating stats to each cottage
    for c in cottages:
        stats = db.execute(
            "SELECT COUNT(*) as count, AVG(rating) as avg, SUM(rating) as total FROM ratings WHERE cottage_id = ?",
            (c['id'],)
        ).fetchone()
        c['rating_count'] = stats['count']
        c['rating_avg'] = round(stats['avg'], 1) if stats['avg'] else 0
        c['rating_total'] = stats['total'] or 0
    
    return render_template('compare.html', cottages=cottages)

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


@app.route('/presentation')
def view_presentation():
    # Get a list of slide images from the static/slides directory
    slides_dir = os.path.join(app.static_folder, 'slides')
    if os.path.exists(slides_dir):
        slides = sorted([f for f in os.listdir(slides_dir) if f.endswith('.png') or f.endswith('.jpg')])
        slide_paths = [url_for('static', filename=f'slides/{slide}') for slide in slides]
    else:
        slide_paths = []
    
    return render_template('presentation.html', 
                         slides=slide_paths,
                         total_slides=len(slide_paths),
                         pptx_url=url_for('static', filename='presentation.pptx'))


@app.route("/guide")
def user_guide():
    return render_template("user_guide.html")


@app.route("/support")
def tech_support():
    return render_template("tech_support.html")


if __name__ == '__main__':
    if not os.path.exists(app.config['DATABASE']):
        with app.app_context():
            init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
