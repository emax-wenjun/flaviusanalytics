DROP TABLE IF EXISTS user;

CREATE TABLE county (
  countyname TEXT PRIMARY KEY,
  candidate1 INTEGER NOT NULL,
  candidate2 INTEGER NOT NULL,
  candidate3 INTEGER NOT NULL,
  totalvotes INTEGER NOT NULL,
  percentin INTEGER NOT NULL,
  votesleft TEXT
);