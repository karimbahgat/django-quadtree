from django.db import models
from itertools import islice

from django.db import connection

# Create your models here.

DEBUG = False
MAX_ITEMS = 10
MAX_DEPTH = 20

# OPTIMIZATIONS
# X implement own link model instead of a manytomanyfield (Item.nodes), since .add() seems to be very slow
# - OR drop the link table alltogether (Item.nodes), instead storing all node items in a comma-separated string
# X(FAIL): call subnodes directly with Node.objects.filter(parent=...), for faster is_leaf()
# X determine leafnode from itemcount being not None, for much faster is_leaf() [not necessary if storing children string]
# - MAYBE...add dot-separated path column as a way to get both traversal and easy access to parents?

# - MAYBE, make all leaf nodes in-memory pyqtrees, only add branch nodes every time it splits (ie no need to constantly edit node counts and links, only at the end)...
# - MAYBE, allow items to be stored at any level, eg if they span multiple quads (ie items belong to only one node, no need for slow links)...
# - MAYBE, do everything with .raw() sql calls

class QuadTree(models.Model):
    xmin = models.FloatField()
    ymin = models.FloatField()
    xmax = models.FloatField()
    ymax = models.FloatField()
    max_items = models.IntegerField(default=MAX_ITEMS)
    max_depth = models.IntegerField(default=MAX_DEPTH)
    root = models.ForeignKey('Node', on_delete=models.CASCADE, db_index=True, null=True)

    def create_root(self):
        root = Node.objects.create(index=self, depth=0, item_count=0, xmin=self.xmin, ymin=self.ymin, xmax=self.xmax, ymax=self.ymax)
        self.root = root

##    def count(self):
##        return self.nodes...
##        return self.cur.execute('SELECT Count(*) FROM (SELECT DISTINCT item FROM items)').fetchone()[0]

    def depth(self):
        return self.nodes.all().aggregate(Max('depth'))

    # Methods

    def build(self, items, chunksize=1000):
        self.create_root()
        
        # first create all items (efficiently)
##        def iterchunks():
##            i = 0
##            while True:
##                chunk = [Item(item_id=item_id, xmin=bbox[0], ymin=bbox[1], xmax=bbox[2], ymax=bbox[3])
##                         for item_id,bbox in islice(items, i, i+chunksize)]
##                if len(chunk):
##                    yield chunk
##                    i += chunksize
##                else:
##                    break
##        #print('begin chunking')
##        for chunk in iterchunks():
##            #print('chunk create')
##            Item.objects.bulk_create(chunk)
##
##        # then insert them into the tree
##        #print('insert')
##        for item in Item.objects.all():
##            self.root.insert(item)

        # simpler approach
        for item_id,bbox in items:
            item = Item.objects.create(item_id=item_id, xmin=bbox[0], ymin=bbox[1], xmax=bbox[2], ymax=bbox[3])
            self.root.insert(item)

    def intersect(self, bbox):
        # TODO: MAYBE ALLOWS SENDING IN CUSTOM MODEL TO RETRIEVE FROM THOSE
        # query
        x1,y1,x2,y2 = bbox
        #boundscheck = 'NOT ({x1} > xmax OR {x2} < xmin OR {y1} > ymax OR {y2} < ymin)'.format(x1=x1, y1=y1, x2=x2, y2=y2)
        boundscheck = '({x1} < xmax AND {x2} > xmin) AND ({y1} < ymax AND {y2} > ymin)'.format(x1=x1, y1=y1, x2=x2, y2=y2)
        #from django.db import connection
        #res = connection.cursor().execute('''
        res = Item.objects.raw('''
                        WITH nodes AS
                            (SELECT * FROM {nodes_table} WHERE index_id = {index}),
                        traversal AS
                          (SELECT id AS nodeid, depth, CAST(id AS text) AS path
                           FROM nodes
                           WHERE parent_id IS NULL AND {boundscheck}

                           UNION ALL

                           SELECT nodes.id AS nodeid, nodes.depth, CAST(path || '.' || CAST(nodes.id AS text) AS text) AS path
                           FROM nodes
                           INNER JOIN traversal
                           ON traversal.nodeid = nodes.parent_id AND {boundscheck}
                           ),
                        travlinks AS
                            (SELECT links.item_id,traversal.depth,traversal.path
                            FROM {links_table} AS links, traversal
                            WHERE links.node_id = traversal.nodeid)

                       -- Extract
                       SELECT items.id AS id, items.item_id, items.xmin, items.ymin, items.xmax, items.ymax
                       FROM {items_table} AS items
                       INNER JOIN travlinks ON items.id = travlinks.item_id
                       WHERE {boundscheck}
                        '''.format(boundscheck=boundscheck,
                                   index=self.pk,
                                   nodes_table=Node._meta.db_table,
                                   items_table=Item._meta.db_table,
                                   links_table=ItemNodeLink._meta.db_table,
                                   ))
        #print 'len',len(res.fetchall())
        #print res.query
        return res

class Item(models.Model):
    item_id = models.IntegerField() # this is the supplied item id/object, and may or may not be unique
    xmin = models.FloatField()
    ymin = models.FloatField()
    xmax = models.FloatField()
    ymax = models.FloatField()
    #nodes = models.ManyToManyField('Node', related_name='items')

class ItemNodeLink(models.Model):
    node = models.ForeignKey('Node', on_delete=models.CASCADE, related_name='links', db_index=True)
    item = models.ForeignKey('Item', on_delete=models.CASCADE, related_name='links', db_index=True)

##    @staticmethod
##    def raw_create(node, item):
##        res = connection.cursor().execute('''
##                                            insert into {table}
##                                            values (null, %s, %s)
##                                        '''.format(table=ItemNodeLink._meta.db_table),
##                                          (item.pk, node.pk),
##                                          )

##    @staticmethod
##    def raw_bulk_create(node, items):
##        nodeid = node.pk
##        connection.cursor().executemany('''
##                                            insert into {table} (node_id, item_id)
##                                            values (?, ?)
##                                        '''.format(table=ItemNodeLink._meta.db_table),
##                                          [(nodeid, item.pk) for item in items],
##                                          )

class Node(models.Model):
    index = models.ForeignKey('QuadTree', on_delete=models.CASCADE, related_name='nodes')
    parent = models.ForeignKey('Node', on_delete=models.CASCADE, related_name='child_nodes', db_index=True, null=True, blank=True)
    depth = models.IntegerField()
    item_count = models.IntegerField(default=0, null=True, blank=True) # None means branch, 0 means isleaf (default when creating new node)
    xmin = models.FloatField()
    ymin = models.FloatField()
    xmax = models.FloatField()
    ymax = models.FloatField()

    def __init__(self, *args, **kwargs):
        super(Node, self).__init__(*args, **kwargs)
        self.halfwidth = (self.xmax - self.xmin) / 2.0
        self.halfheight = (self.ymax - self.ymin) / 2.0
        self.center = (self.xmin + self.halfwidth, self.ymin + self.halfheight)
        
            # retrieve existing node from table
##            parent, depth, count, xmin, ymin, xmax, ymax = self._index.cur.execute('SELECT * FROM nodes WHERE oid = ?', (nodeid,) ).fetchone()
##            x,y = (xmin+xmax)/2.0, (ymin+ymax)/2.0
##            halfwidth = (xmax-xmin)/2.0
##            halfheight = (ymax-ymin)/2.0

    def subnodes(self):
        #return self.child_nodes.all().order_by('ymin', 'xmin')
        #return Node.objects.filter(parent=self.pk).order_by('ymin', 'xmin')
        res = connection.cursor().execute('''
                                            select id,index_id,parent_id,depth,item_count,xmin,ymin,xmax,ymax
                                            from {table}
                                            where parent_id = {nodeid}
                                            order by ymin,xmin
                                        '''.format(table=Node._meta.db_table, nodeid=self.pk),
                                          )
        res = [Node(*row) for row in res]
        return res

    def getlinks(self):
        #itemlinks = self.links.all() 
        #itemlinks = ItemNodeLink.objects.filter(node=self)
        res = connection.cursor().execute('''
                                            select id,node_id,item_id
                                            from {table}
                                            where node_id = {nodeid}
                                        '''.format(table=ItemNodeLink._meta.db_table, nodeid=self.pk),
                                          )
        itemlinks = [ItemNodeLink(*row) for row in res]
        return itemlinks

    def clearlinks(self):
        connection.cursor().execute('''
                                            delete from {table}
                                            where node_id = {nodeid}
                                        '''.format(table=ItemNodeLink._meta.db_table, nodeid=self.pk),
                                          )

    def getitems(self):
        res = connection.cursor().execute('''SELECT items.id, items.xmin, items.ymin, items.xmax, items.ymax
                                            FROM {itemtable} AS items
                                            INNER JOIN {linktable} AS links
                                            ON links.node_id = {nodeid}
                                            AND items.id = links.item_id'''.format(itemtable=Item._meta.db_table,
                                                                                  linktable=ItemNodeLink._meta.db_table,
                                                                                  nodeid=self.pk,) )
        items = [Item(*row) for row in res]
        return items

    def is_leaf(self):
        if self.item_count is None:
            return False
        else:
            return True
##        subnodes = Node.objects.filter(parent=self.pk).count()
##        #subnodes = self.nodes.all().count()
##        if subnodes == 0:
##            return True

    def insert(self, item):
        #print 'insert',parent
        
        # if is leaf node (has not yet been subdivided)
        if self.is_leaf():
            # link item to the node itself
            self.add_item(item)
            self.save(update_fields=['item_count'])

            if DEBUG:
                pass#print 'add to leaf node',self.nodeid
            
            # test if should split
            if self.item_count > self.index.max_items and self.depth < self.index.max_depth:
                self.split()

        # elif has subnodes
        else:
            # insert into each overlapping subnode
            bbox = item.xmin,item.ymin,item.xmax,item.ymax
            quads = self.quadrants(bbox)
            subnodes = list(self.subnodes())
            for quad in quads:
                node = subnodes[quad-1]
                if DEBUG:
                    pass#print 'recurse into subnode',node.nodeid,node.depth,'---',len(list(node.items())),len(list(node.subnodes()))
                node.insert(item)

    def quadrants(self, bbox):
        # test which quadrant(s) a bbox belongs to
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
        #print('split')
        quartwidth = self.halfwidth/2.0
        quartheight = self.halfheight/2.0
        x1 = self.center[0] - quartwidth
        x2 = self.center[0] + quartwidth
        y1 = self.center[1] - quartheight
        y2 = self.center[1] + quartheight

        # create 4 new subnodes
        parent = self
        new_depth = self.depth + 1
        count = 0
        subnodes = [Node.objects.create(index=self.index, parent=parent, depth=new_depth, item_count=count, xmin=x1-quartwidth, ymin=y1-quartheight, xmax=x1+quartwidth, ymax=y1+quartheight),
                     Node.objects.create(index=self.index, parent=parent, depth=new_depth, item_count=count, xmin=x2-quartwidth, ymin=y1-quartheight, xmax=x2+quartwidth, ymax=y1+quartheight),
                     Node.objects.create(index=self.index, parent=parent, depth=new_depth, item_count=count, xmin=x1-quartwidth, ymin=y2-quartheight, xmax=x1+quartwidth, ymax=y2+quartheight),
                     Node.objects.create(index=self.index, parent=parent, depth=new_depth, item_count=count, xmin=x2-quartwidth, ymin=y2-quartheight, xmax=x2+quartwidth, ymax=y2+quartheight)]
        #Node.objects.bulk_create(subnodes)
        #for node in subnodes:
        #    node.save()

##        if DEBUG:
##            print 'split',self.nodeid
##            for node in subnodes:
##                passprint 'quad',node.nodeid, node.parent, node.depth

        # delete previous links to this node and reset node count
        #itemlinks = ItemNodeLink.objects.filter(node=self)
        #itemlinks = self.links.all()
        #itemlinks = self.getlinks()
        #items = [link.item for link in itemlinks] # get items before deleting the links
        items = self.getitems()
        #temlinks.delete()
        self.clearlinks()
        #items = list(self.items.all()) # get items before deleting the links
        #self.items.clear()
        self.item_count = None # setting to None makes it no longer a leaf node
        self.save(update_fields=['item_count'])

        # BULK: update items so they link to the new subnodes
        # group items by quad/subnode
        quaditems = {1:[], 2:[], 3:[], 4:[]}
        for item in items:
            #print('adding into subquads',item)
            bbox = item.xmin,item.ymin,item.xmax,item.ymax
            quads = self.quadrants(bbox)
            for quad in quads:
                quaditems[quad].append(item)
        # for each quad/subnode, bulk insert new links and update count
        newlinks = []
        for quad,quaditems in quaditems.items():
            #print('link to new subnodes',quad,len(quaditems))
            newnode = subnodes[quad-1]
            newlinks += [ItemNodeLink(item=item, node=newnode) for item in quaditems]
            #ItemNodeLink.objects.bulk_create(newlinks)
            #ItemNodeLink.raw_bulk_create(newnode, quaditems)
            newnode.item_count = len(quaditems)
            newnode.save(update_fields=['item_count'])
        ItemNodeLink.objects.bulk_create(newlinks)

        # ONE-BY-ONE SLOW: update items so they link to the new subnodes
##        for item in items:
##            #print('adding into subquads',item)
##            bbox = item.xmin,item.ymin,item.xmax,item.ymax
##            quads = self.quadrants(bbox)
##            for quad in quads:
##                newnode = subnodes[quad-1]
##                newnode.add_item(item)
##        #Node.objects.bulk_update(subnodes)
##        for node in subnodes:
##            node.save(update_fields=['item_count'])

    def add_item(self, item):
        # add link
        #self.items.add(item)
        #ItemNodeLink.objects.create(item=item, node=self)
        #ItemNodeLink.raw_create(item, self)
        res = connection.cursor().execute('''
                                            insert into {table} (item_id, node_id)
                                            values (%s, %s)
                                        '''.format(table=ItemNodeLink._meta.db_table),
                                          (item.pk, self.pk),
                                          )
        # update count
        if self.item_count is None:
            self.item_count = 1 # from 0 to 1
        else:
            self.item_count += 1



