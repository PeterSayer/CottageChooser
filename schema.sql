CREATE TABLE IF NOT EXISTS cottages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  location TEXT,
  price TEXT,
  beds INTEGER DEFAULT 1,
  dogs_allowed INTEGER DEFAULT 0,
  image TEXT,
  description TEXT,
  submitted_by TEXT,
  votes INTEGER DEFAULT 0,
  created_at DATETIME DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS comments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cottage_id INTEGER NOT NULL,
  author TEXT,
  text TEXT,
  created_at DATETIME DEFAULT (datetime('now')),
  FOREIGN KEY (cottage_id) REFERENCES cottages(id)
);