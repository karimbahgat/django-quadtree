
import sqlite3

db = sqlite3.connect(':memory:')
cur = db.cursor()

# create test data (four quadrants, plus child inside topleft?)
cur.execute('CREATE TABLE test (nodeid INT, parent INT, x1 REAL, y1 REAL, x2 REAL, y2 REAL)')
cur.execute('''INSERT INTO test VALUES
            (1, NULL, -180, -90, 0, 0),
            (2, NULL, 0, -90, 180, 0),
            (3, NULL, 0, 0, 180, 90),
            (4, NULL, -180, 0, 0, 90),
            (5, 1, -180, -90, -90, 0),
            (6, 5, -180, -90, -90, 0),
            (7, 3, 0, 0, 90, 45)
            ''')

# get hierarchy recursively
res = cur.execute('''WITH CTE AS
                  (SELECT nodeid, 0 AS level, CAST(nodeid AS text) AS path
                   FROM test AS t1
                   WHERE parent IS NULL

                   UNION ALL

                   SELECT t2.nodeid, level+1, CAST((path || '.' || CAST(t2.nodeid AS text)) AS text) AS path
                   FROM test AS t2
                   INNER JOIN CTE AS items
                   ON items.nodeid = t2.parent
                   )

                   -- Extract
                   SELECT nodeid, level, path
                   FROM CTE
                   ORDER BY path
                ''')
for r in res:
    print r
