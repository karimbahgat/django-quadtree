
import sqlite3

db = sqlite3.connect(':memory:')
cur = db.cursor()

# create test data (four quadrants, plus child inside topleft?)
cur.execute('CREATE TABLE tree (parent INT, xmin REAL, ymin REAL, xmax REAL, ymax REAL)')
cur.execute('''INSERT INTO tree VALUES
            (NULL, -180, -90, 0, 0),
            (NULL, 0, -90, 180, 0),
            (NULL, 0, 0, 180, 90),
            (NULL, -180, 0, 0, 90),
            (1, -180, -90, -90, 0),
            (5, -180, -90, -90, 0),
            (3, 170, 80, 180, 90)
            ''')

# get hierarchy recursively
x1,y1,x2,y2 = (-1000,-1000, -1, 100)
x1,y1,x2,y2 = (-1000,-1000, 1000, 1000)
boundscheck = 'NOT ({x1} > xmax OR {x2} < xmin OR {y1} > ymax OR {y2} < ymin)'.format(x1=x1, y1=y1, x2=x2, y2=y2)
res = cur.execute('''WITH CTE AS
                  (SELECT oid, 0 AS level, CAST(oid AS text) AS path
                   FROM tree AS t1
                   WHERE parent IS NULL AND {boundscheck}

                   UNION ALL

                   SELECT t2.oid, level+1, CAST(path || '.' || CAST(t2.oid AS text) AS text) AS path
                   FROM tree AS t2
                   INNER JOIN CTE AS matches
                   ON matches.oid = t2.parent AND {boundscheck}
                   )

                   -- Extract
                   SELECT oid, level, path
                   FROM CTE
                   ORDER BY path
                '''.format(boundscheck=boundscheck))
for r in res:
    print r
