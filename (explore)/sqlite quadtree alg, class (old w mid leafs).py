
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

        # create branch table
        self.cur.execute('CREATE TABLE nodes (parent INT, depth INT, xmin REAL, ymin REAL, xmax REAL, ymax REAL)')
        #self.cur.execute('CREATE INDEX idx_nodes_parent ON nodes')
        #self.cur.execute('CREATE INDEX idx_nodes_bbox ON nodes')

        # create leaf table
        self.cur.execute('CREATE TABLE items (parent INT, item BLOB, xmin REAL, ymin REAL, xmax REAL, ymax REAL)')
        #self.cur.execute('CREATE INDEX idx_items_parent ON items')
        #self.cur.execute('CREATE INDEX idx_items_bbox ON items')

        # create root node class
        x,y = (xmin+xmax)/2.0, (ymin+ymax)/2.0
        halfwidth = (xmax-xmin)/2.0
        halfheight = (ymax-ymin)/2.0
        parent = None
        depth = 0
        self.root = Node(self, None, parent, depth, x, y, halfwidth, halfheight)

    def __del__(self):
        os.remove(self._addr)

    def __len__(self):
        return self.cur.execute('SELECT Count(oid) FROM items').fetchone()[0]

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
                           SELECT items.oid, items.item, items.xmin, items.ymin, items.xmax, items.ymax, traversal.depth, traversal.path, items.parent
                           FROM items INNER JOIN traversal ON items.parent = traversal.oid
                        '''.format(boundscheck=boundscheck))

        # FIX: SHOULD BE MORE USEFUL RESULTS
        # ...
        
        return res

class Item(object):
    pass
    
class Node(object):
    def __init__(self, index, nodeid, parent=None, depth=None, x=None, y=None, halfwidth=None, halfheight=None):
        self._index = index

        if nodeid is None:
            # nodeid doesnt exist, add it
            xmin, ymin, xmax, ymax = x-halfwidth, y-halfheight, x+halfwidth, y+halfheight
            #print 'bbox', xmin, ymin, xmax, ymax
            self._index.cur.execute('INSERT INTO nodes VALUES (?, ?, ?, ?, ?, ?)', (parent, depth, xmin, ymin, xmax, ymax) )
            # set nodeid based on most recent insertion
            nodeid = self._index.cur.lastrowid

        else:
            # retrieve existing node from table
            parent, depth, xmin, ymin, xmax, ymax = self._index.cur.execute('SELECT * FROM nodes WHERE oid = ?', (nodeid,) ).fetchone()
            x,y = (xmin+xmax)/2.0, (ymin+ymax)/2.0
            halfwidth = (xmax-xmin)/2.0
            halfheight = (ymax-ymin)/2.0

        self.nodeid = nodeid
        self.parent = parent
        self.depth = depth
        self.center = (x, y)
        self.halfwidth = halfwidth
        self.halfheight = halfheight

    def subnodes(self):
        return self._index.cur.execute('SELECT oid, * FROM nodes WHERE parent = ? ORDER BY ymin, xmin', (self.nodeid,) )

    def items(self):
        return self._index.cur.execute('SELECT oid, * FROM items WHERE parent = ?', (self.nodeid,) )

    def is_leaf(self):
        subnodes = list(self.subnodes())
        if len(subnodes) == 0:
            return True

##    def insert(self, item, bbox):
##        # if spans more than one quadrant or is leaf node (has not yet been subdivided)
##        if (bbox[0] <= self.center[0] and bbox[2] >= self.center[0]) or (bbox[1] <= self.center[1] and bbox[3] >= self.center[1]) or self.is_leaf():
##            # add item on the node itself
##            self.add_item(item, bbox)
##            
##            # test if should split
##            items = self.items()
##            if len(items) > self._index.max_items and self.depth < self._index.max_depth:
##                self.split()
##
##        # elif empty branch
##        else:
##            # figure out which subnode to insert into
##            self.insert_into_subnodes(item, bbox)

##    def insert_into_subnodes(self, item, bbox):
##        # try to insert into subnodes
##        subnodes = list(self.subnodes())
##        if bbox[0] <= self.center[0]:
##            if bbox[1] <= self.center[1]:
##                subnodes[0].insert(item, bbox)
##            if bbox[3] >= self.center[1]:
##                subnodes[1].insert(item, bbox)
##        if bbox[2] > self.center[0]:
##            if bbox[1] <= self.center[1]:
##                subnodes[2].insert(item, bbox)
##            if bbox[3] >= self.center[1]:
##                subnodes[3].insert(item, bbox)

    def insert(self, item, bbox):
        #print 'insert',parent
        quad = self.quadrant(bbox)
        # if spans more than one quadrant or is leaf node (has not yet been subdivided)
        is_leaf = self.is_leaf()
        if quad is None or is_leaf:
            # add item on the node itself
            self.add_item(item, bbox)

            if DEBUG:
                print 'insert mid-node (span or leaf)',self.nodeid
            
            # test if should split
            if is_leaf:
                items = list(self.items())
                if len(items) > self._index.max_items and self.depth < self._index.max_depth:
                    self.split()

        # elif has subnodes
        else:
            # figure out which subnode to insert into
            subnodes = list(self.subnodes())
            nodeid = subnodes[quad-1][0]
            node = Node(self._index, nodeid)
            if DEBUG:
                print 'insert into subnode',node.nodeid,node.depth,'---',len(list(node.items())),len(list(node.subnodes()))
            node.insert(item, bbox)
            
##            node.add_item(item, bbox)
##
##            # test if should split
##            if node.is_leaf():
##                items = list(node.items())
##                #print node.nodeid,len(items),self._index.max_items
##                if len(items) > self._index.max_items and node.depth < self._index.max_depth:
##                    node.split()

    def update(self, id, parent):
        self._index.cur.execute('UPDATE items SET parent = ? WHERE oid = ?', (parent, id,) )

    def quadrant(self, bbox):
        # test which quadrant the bbox belongs to
        # return None if spans multiple
        if bbox[0] <= self.center[0]:
            if bbox[1] <= self.center[1]:
                return 1
            if bbox[3] >= self.center[1]:
                return 3
        if bbox[2] > self.center[0]:
            if bbox[1] <= self.center[1]:
                return 2
            if bbox[3] >= self.center[1]:
                return 4

    def split(self):
        halfwidth = self.halfwidth
        halfheight = self.halfheight
        quartwidth = halfwidth/2.0
        quartheight = halfheight/2.0
        x1 = self.center[0] - quartwidth
        x2 = self.center[0] + quartwidth
        y1 = self.center[1] - quartheight
        y2 = self.center[1] + quartheight
        new_depth = self.depth + 1
        parent = self.nodeid

        subnodes = [Node(self._index, None, parent, new_depth, x1, y1, quartwidth, quartheight),
                     Node(self._index, None, parent, new_depth, x2, y1, quartwidth, quartheight),
                     Node(self._index, None, parent, new_depth, x1, y2, quartwidth, quartheight),
                     Node(self._index, None, parent, new_depth, x2, y2, quartwidth, quartheight)]

        if DEBUG:
            print 'split',self.nodeid
            for node in subnodes:
                print 'quad',node.nodeid, node.parent, node.depth

        # for each item, update to new parent
        for itemid,oldparent,item,xmin,ymin,xmax,ymax in self.items():
            bbox = xmin,ymin,xmax,ymax
            quad = self.quadrant(bbox)
            node = subnodes[quad-1]
            node.update(itemid, parent=node.nodeid)

    def add_item(self, item, bbox):
        xmin,ymin,xmax,ymax = bbox
        parent = self.nodeid
        self._index.cur.execute('INSERT INTO items VALUES (?, ?, ?, ?, ?, ?)', (parent, item, xmin, ymin, xmax, ymax) )



if __name__ == '__main__':
    import pythongis as pg

    DEBUG = False
    
    print 'loading'
    d = pg.VectorData(r"C:\Users\kimok\Downloads\ne_10m_admin_1_states_provinces (1)\ne_10m_admin_1_states_provinces.shp")
    items = [(i, f.bbox) for i,f in enumerate(d)]

    print 'building'
    spindex = QuadTree(-180, -90, 180, 90)
    spindex.build(items)

    print 'intersecting'
    matches = spindex.intersect((1,1,20,20))

##    print 'viewing'
##    boxes = pg.VectorData(fields=['path','parent'])
##    res = pg.VectorData()
##    for match in matches:
##        #print match
##        i = match[1]
##        f = d[i]
##        res.add_feature([], f.geometry)
##        x1,y1,x2,y2 = match[2:6] #f.bbox
##        path = match[-2]
##        parent = match[-1]
##        box = {'type':'Polygon', 'coordinates':[[(x1,y1),(x1,y2),(x2,y2),(x2,y1)]]}
##        boxes.add_feature([path,parent], box)
##    m = pg.renderer.Map()
##    m.add_layer(res, fillcolor='red')
##    m.add_layer(boxes, fillcolor=None, outlinecolor='green')
##    m.view()

    # raw
    print 'explore nodes and items'
    quads = pg.VectorData(fields=['nodeid','parent','depth'])
    for row in spindex.cur.execute('select oid,* from nodes'):
        nodeid = row[0]
        parent = row[1]
        depth = row[2]
        x1,y1,x2,y2 = row[-4:]
        box = {'type':'Polygon', 'coordinates':[[(x1,y1),(x1,y2),(x2,y2),(x2,y1)]]}
        quads.add_feature([nodeid,parent,depth], box)
    items = pg.VectorData(fields=['parent','item'])
    for row in spindex.cur.execute('select * from items'):
        parent,item,x1,y1,x2,y2 = row
        box = {'type':'Polygon', 'coordinates':[[(x1,y1),(x1,y2),(x2,y2),(x2,y1)]]}
        items.add_feature([parent,item], box)
    m = pg.renderer.Map()
    #m.add_layer(d, fillcolor='red')
    m.add_layer(items, fillcolor=None, outlinecolor='blue')
    m.add_layer(quads, fillcolor=None, outlinecolor='green',
                ) #text=lambda f: f['nodeid'], textoptions={'textcolor':'green','textsize':6})
    m.view()
        
        




        
