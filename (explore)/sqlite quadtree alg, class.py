
import sqlite3
import tempfile
import os


DEBUG = False
MAX_ITEMS = 10
MAX_DEPTH = 20


class QuadTree(object):
    def __init__(self, xmin, ymin, xmax, ymax, max_items=MAX_ITEMS, max_depth=MAX_DEPTH):
        # create db
        self._addr = tempfile.mktemp()
        self.db = sqlite3.connect(self._addr)
        self.db.isolation_level = None
        self.cur = self.db.cursor()

        # params
        self.max_items = max_items
        self.max_depth = max_depth

        # create node table
        self.cur.execute('CREATE TABLE nodes (parent INT, depth INT, count INT, xmin REAL, ymin REAL, xmax REAL, ymax REAL)')
        self.cur.execute('CREATE INDEX idx_nodes_parent ON nodes (parent)')
        #self.cur.execute('CREATE INDEX idx_nodes_bbox ON nodes')

        # create item table
        self.cur.execute('CREATE TABLE items (item BLOB, xmin REAL, ymin REAL, xmax REAL, ymax REAL)')
        #self.cur.execute('CREATE INDEX idx_items_parent ON items')
        #self.cur.execute('CREATE INDEX idx_items_bbox ON items')

        # create link table
        self.cur.execute('CREATE TABLE links (nodeid INT, itemid INT)')
        self.cur.execute('CREATE INDEX idx_links ON links (nodeid, itemid)')

        # create root node class
        x,y = (xmin+xmax)/2.0, (ymin+ymax)/2.0
        halfwidth = (xmax-xmin)/2.0
        halfheight = (ymax-ymin)/2.0
        parent = None
        depth = 0
        count = 0
        self.root = Node(self, None, parent, depth, count, x, y, halfwidth, halfheight)

    def __del__(self):
        os.remove(self._addr)

    def __len__(self):
        return self.count()

    # Diagnostics
    
    def count(self):
        return self.cur.execute('SELECT Count(*) FROM (SELECT DISTINCT item FROM items)').fetchone()[0]

    def depth(self):
        return self.cur.execute('SELECT Max(depth) FROM nodes').fetchone()[0]

    # Methods

    def build(self, items):
        self.cur.execute('BEGIN')
        for item,bbox in items:
            self.root.insert(item, bbox)
        self.cur.execute('COMMIT')

    def intersect(self, bbox):
        # query
        x1,y1,x2,y2 = bbox
        boundscheck = 'NOT ({x1} > xmax OR {x2} < xmin OR {y1} > ymax OR {y2} < ymin)'.format(x1=x1, y1=y1, x2=x2, y2=y2)
        res = self.cur.execute('''WITH traversal AS
                          (SELECT oid, depth, CAST(oid AS text) AS path
                           FROM nodes
                           WHERE parent IS NULL AND {boundscheck}

                           UNION ALL

                           SELECT nodes.oid, nodes.depth, CAST(path || '.' || CAST(nodes.oid AS text) AS text) AS path
                           FROM nodes
                           INNER JOIN traversal
                           ON traversal.oid = nodes.parent AND {boundscheck}
                           )

                           -- Extract
                           SELECT items.oid, items.item, items.xmin, items.ymin, items.xmax, items.ymax, travitems.depth, travitems.path
                           FROM items
                           INNER JOIN (SELECT links.itemid,traversal.depth,traversal.path FROM links,traversal WHERE links.nodeid = traversal.oid) AS travitems ON items.oid = travitems.itemid
                        '''.format(boundscheck=boundscheck))

        # FIX: SHOULD BE MORE USEFUL RESULTS
        # ...
        
        return res
    
    
class Node(object):
    def __init__(self, index, nodeid, parent=None, depth=None, count=None, x=None, y=None, halfwidth=None, halfheight=None):
        self._index = index

        if nodeid is None:
            # nodeid doesnt exist, add it
            xmin, ymin, xmax, ymax = x-halfwidth, y-halfheight, x+halfwidth, y+halfheight
            #print 'bbox', xmin, ymin, xmax, ymax
            self._index.cur.execute('INSERT INTO nodes VALUES (?, ?, ?, ?, ?, ?, ?)', (parent, depth, count, xmin, ymin, xmax, ymax) )
            # set nodeid based on most recent insertion
            nodeid = self._index.cur.lastrowid

        else:
            # retrieve existing node from table
            parent, depth, count, xmin, ymin, xmax, ymax = self._index.cur.execute('SELECT * FROM nodes WHERE oid = ?', (nodeid,) ).fetchone()
            x,y = (xmin+xmax)/2.0, (ymin+ymax)/2.0
            halfwidth = (xmax-xmin)/2.0
            halfheight = (ymax-ymin)/2.0

        self.nodeid = nodeid
        self.parent = parent
        self.depth = depth
        self.count = count
        self.center = (x, y)
        self.halfwidth = halfwidth
        self.halfheight = halfheight

    def subnodes(self):
        return self._index.cur.execute('SELECT oid, * FROM nodes WHERE parent = ? ORDER BY ymin, xmin', (self.nodeid,) )

    def items(self):
        return self._index.cur.execute('SELECT items.oid, items.* FROM items INNER JOIN (SELECT itemid FROM links WHERE nodeid = ?) AS nodeitems ON items.oid = nodeitems.itemid', (self.nodeid,) )

    def is_leaf(self):
        subnodes = self._index.cur.execute('SELECT Count(*) FROM nodes WHERE parent = ?', (self.nodeid,) ).fetchone()[0]
        if subnodes == 0:
            return True

    def insert(self, item, bbox):
        #print 'insert',parent
        
        # if is leaf node (has not yet been subdivided)
        if self.is_leaf():
            # add item on the node itself
            self.add_item(item, bbox)

            if DEBUG:
                print 'add to leaf node',self.nodeid
            
            # test if should split
            if self.count > self._index.max_items and self.depth < self._index.max_depth:
                self.split()

        # elif has subnodes
        else:
            # insert into each overlapping subnode
            quads = self.quadrant(bbox)
            subnodes = list(self.subnodes())
            for quad in quads:
                nodeid = subnodes[quad-1][0]
                node = Node(self._index, nodeid)
                if DEBUG:
                    print 'recurse into subnode',node.nodeid,node.depth,'---',len(list(node.items())),len(list(node.subnodes()))
                node.insert(item, bbox)

    def quadrant(self, bbox):
        # test which quadrant the bbox belongs to
        # return None if spans multiple
        quads = []
        if bbox[0] <= self.center[0]:
            if bbox[1] <= self.center[1]:
                quads.append(1)
            if bbox[3] >= self.center[1]:
                quads.append(3)
        if bbox[2] > self.center[0]:
            if bbox[1] <= self.center[1]:
                quads.append(2)
            if bbox[3] >= self.center[1]:
                quads.append(4)
        return quads

    def split(self):
        halfwidth = self.halfwidth
        halfheight = self.halfheight
        quartwidth = halfwidth/2.0
        quartheight = halfheight/2.0
        x1 = self.center[0] - quartwidth
        x2 = self.center[0] + quartwidth
        y1 = self.center[1] - quartheight
        y2 = self.center[1] + quartheight

        # create 4 new subnodes
        parent = self.nodeid
        new_depth = self.depth + 1
        count = 0
        subnodes = [Node(self._index, None, parent, new_depth, count, x1, y1, quartwidth, quartheight),
                     Node(self._index, None, parent, new_depth, count, x2, y1, quartwidth, quartheight),
                     Node(self._index, None, parent, new_depth, count, x1, y2, quartwidth, quartheight),
                     Node(self._index, None, parent, new_depth, count, x2, y2, quartwidth, quartheight)]

        if DEBUG:
            print 'split',self.nodeid
            for node in subnodes:
                print 'quad',node.nodeid, node.parent, node.depth

        # update items so they link to the new subnodes
        for itemid,item,xmin,ymin,xmax,ymax in self.items():
            bbox = xmin,ymin,xmax,ymax
            quads = self.quadrant(bbox)
            for quad in quads:
                newnode = subnodes[quad-1]
                # update count
                self._index.cur.execute('UPDATE nodes SET count = count + 1 WHERE oid = ?', (newnode.nodeid,) )
                newnode.count += 1
                # add link
                self._index.cur.execute('INSERT INTO links VALUES (?, ?)', (newnode.nodeid, itemid) )

        # delete previous links to this node and reset node count
        self._index.cur.execute('DELETE FROM links WHERE oid = ?', (self.nodeid,) )
        self._index.cur.execute('UPDATE nodes SET count = 0 WHERE oid = ?', (self.nodeid,) )

    def add_item(self, item, bbox):
        # add item
        xmin,ymin,xmax,ymax = bbox
        self._index.cur.execute('INSERT INTO items VALUES (?, ?, ?, ?, ?)', (item, xmin, ymin, xmax, ymax) )
        itemid = self._index.cur.lastrowid
        # update count
        self._index.cur.execute('UPDATE nodes SET count = count + 1 WHERE oid = ?', (self.nodeid,) )
        self.count += 1
        # add link
        self._index.cur.execute('INSERT INTO links VALUES (?, ?)', (self.nodeid, itemid) )









######################################
# TESTING

if __name__ == '__main__':
    import pythongis as pg

    DEBUG = False
    PROFILE = True
    
    print 'loading'
    d = pg.VectorData(r"C:\Users\kimok\Downloads\ne_10m_admin_1_states_provinces (1)\ne_10m_admin_1_states_provinces.shp")
    #d = pg.VectorData(r"C:\Users\kimok\Desktop\BIGDATA\gazetteer data\raw\global_settlement_points_v1.01.shp", encoding='latin')
    items = [(i, f.bbox) for i,f in enumerate(d)]

    print 'building'
    spindex = QuadTree(-180, -90, 180, 90)
    if PROFILE:
        import cProfile
        prof = cProfile.Profile()
        prof.enable()
    spindex.build(items)
    if PROFILE:
        print prof.print_stats('cumtime')
        fdsdfd

    print 'building pyqtree comparison, much faster' # MAYBE CONSIDER USING PYQTREE TO CONSTRUCT, THEN DUMP TO SQL FOR STORAGE AND INTERSECT QUERY
    import pyqtree
    pyq = pyqtree.Index(bbox=[-180, -90, 180, 90])
    for i,bbox in items:
        pyq.insert(i, bbox)
    print len(pyq)

    print 'intersecting'
    matches = spindex.intersect((100,1,120,20))

    print 'visualizing'
    boxes = pg.VectorData(fields=['path'])
    res = pg.VectorData()
    for match in matches:
        #print match
        i = match[1]
        f = d[i]
        res.add_feature([], f.geometry)
        x1,y1,x2,y2 = match[2:6] #f.bbox
        path = match[-1]
        box = {'type':'Polygon', 'coordinates':[[(x1,y1),(x1,y2),(x2,y2),(x2,y1)]]}
        boxes.add_feature([path], box)
    m = pg.renderer.Map()
    m.add_layer(res, fillcolor='red')
    m.add_layer(boxes, fillcolor=None, outlinecolor='green')
    m.view()

    # raw
    print 'explore nodes and items'
    quads = pg.VectorData(fields=['nodeid','parent','depth','count'])
    for row in spindex.cur.execute('select oid,* from nodes'):
        nodeid,parent,depth,count,x1,y1,x2,y2 = row
        box = {'type':'Polygon', 'coordinates':[[(x1,y1),(x1,y2),(x2,y2),(x2,y1)]]}
        quads.add_feature([nodeid,parent,depth,count], box)
    items = pg.VectorData(fields=['parent','item'])
    for row in spindex.cur.execute('select * from items'):
        item,x1,y1,x2,y2 = row
        box = {'type':'Polygon', 'coordinates':[[(x1,y1),(x1,y2),(x2,y2),(x2,y1)]]}
        items.add_feature([parent,item], box)
        
    m = pg.renderer.Map()
    #m.add_layer(d, fillcolor='red')
    m.add_layer(items, fillcolor=None, outlinecolor='blue')
    m.add_layer(quads, fillcolor=None, outlinecolor='green',
                ) #text=lambda f: f['nodeid'], textoptions={'textcolor':'green','textsize':6})
    m.view()
        
        




        
