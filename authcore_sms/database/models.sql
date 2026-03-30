CREATE TABLE staff (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id TEXT UNIQUE,
    name TEXT,
    department TEXT,
    designation TEXT,
    mobile TEXT,
    face_registered INTEGER DEFAULT 0
);

CREATE TABLE attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id TEXT,
    name TEXT,
    department TEXT,
    date TEXT,
    time TEXT,
    mode TEXT
);


