import sqlite3

conn = sqlite3.connect('vectorstore/chroma.sqlite3')
rows = conn.execute(
    "SELECT string_value, COUNT(*) FROM embedding_metadata WHERE key='source' GROUP BY string_value"
).fetchall()

for r in rows:
    print(r)