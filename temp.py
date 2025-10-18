import sqlite3

conn = sqlite3.connect('cards.db')
cursor = conn.cursor()
cursor.execute("SELECT * FROM Cards WHERE assetbundleName = 'res001_no022';")
rows = cursor.fetchall()
for row in rows:
    print(row)
conn.close()