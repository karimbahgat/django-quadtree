from django.test import TestCase
from djquadtree.models import QuadTree, Node, Item, ItemNodeLink

# Create your tests here.
class BasicTestCase(TestCase):
    
    def test_example(self):
        import pythongis as pg

        DEBUG = False
        PROFILE = True
        
        print 'loading'
        d = pg.VectorData(r"C:\Users\kimok\Downloads\ne_10m_admin_1_states_provinces (1)\ne_10m_admin_1_states_provinces.shp")
        #d = pg.VectorData(r"C:\Users\kimok\Desktop\BIGDATA\gazetteer data\raw\global_settlement_points_v1.01.shp", encoding='latin')
        d = d.select(lambda f: f.id < 1000)
        items = [(f.id, f.bbox) for f in d] # items = [(i+1, f.bbox) for i,f in enumerate(d)]
        print len(items)

        #####################

        # build
        print 'building'
        spindex = QuadTree(xmin=-180, ymin=-90, xmax=180, ymax=90)
        spindex.save()
        if PROFILE:
            import cProfile
            prof = cProfile.Profile()
            prof.enable()
        spindex.build(items)
        if PROFILE:
            print prof.print_stats('cumtime')
            #fdsdfd

        print 'items',Item.objects.all().count()
        print 'nodes',Node.objects.all().count()
        print 'links',ItemNodeLink.objects.all().count()

        # visualize
        m = pg.renderer.Map()

        # quad structure
        print 'explore nodes and items'
        quads = pg.VectorData(fields=['nodeid','parent','depth','count'])
        for node in spindex.nodes.all():
            x1,y1,x2,y2 = node.xmin,node.ymin,node.xmax,node.ymax
            box = {'type':'Polygon', 'coordinates':[[(x1,y1),(x1,y2),(x2,y2),(x2,y1)]]}
            quads.add_feature([node.pk,node.parent,node.depth,node.item_count], box)
        items = pg.VectorData(fields=['item'])
        for item in Item.objects.all():
            x1,y1,x2,y2 = item.xmin,item.ymin,item.xmax,item.ymax
            box = {'type':'Polygon', 'coordinates':[[(x1,y1),(x1,y2),(x2,y2),(x2,y1)]]}
            items.add_feature([item], box)

        print(quads)

        m.add_layer(d, fillcolor='red')
        m.add_layer(items, fillcolor=None, outlinecolor='blue')
        m.add_layer(quads, fillcolor=None, outlinecolor='green',
                    ) #text=lambda f: f['nodeid'], textoptions={'textcolor':'green','textsize':6})
        m.render_all()
        m.view()

        ###################

        # intersection
        print 'intersecting'
        testbox = (0,0,90,45)
        #testbox = (100,1,120,20)
        #testbox = (100,15,105,20)
        if PROFILE:
            import cProfile
            prof = cProfile.Profile()
            prof.enable()
        matches = spindex.intersect(testbox)
        if PROFILE:
            print prof.print_stats('cumtime')
            #fdsdfds

        # visualize
        m = pg.renderer.Map()

        # result item boxes
        boxes = pg.VectorData()
        res = pg.VectorData()
        for match in matches:
            #print match
            #oid,itemid,x1,y1,x2,y2,depth,path = match
            oid,itemid,x1,y1,x2,y2 = [getattr(match,k) for k in 'pk,item_id,xmin,ymin,xmax,ymax'.split(',')]
            f = d[itemid]
            res.add_feature([], f.geometry)
            box = {'type':'Polygon', 'coordinates':[[(x1,y1),(x1,y2),(x2,y2),(x2,y1)]]}
            boxes.add_feature([], box)
        m.add_layer(res, fillcolor='red')
        m.add_layer(boxes, fillcolor=None, outlinecolor='green')

        # result node boxes
    ##    nodematches = spindex.intersect_nodes(testbox)
    ##    nodedata = pg.VectorData(fields=['path','count'])
    ##    for node in nodematches:
    ##        #print match
    ##        count = node[-3]
    ##        x1,y1,x2,y2 = node[1:5] #f.bbox
    ##        path = node[-1]
    ##        box = {'type':'Polygon', 'coordinates':[[(x1,y1),(x1,y2),(x2,y2),(x2,y1)]]}
    ##        nodedata.add_feature([path,count], box)
    ##    m.add_layer(nodedata, fillcolor=None, outlinecolor='blue')

        # testbox
        testboxdata = pg.VectorData()
        x1,y1,x2,y2 = testbox
        geoj = {'type':'Polygon', 'coordinates':[[(x1,y1),(x1,y2),(x2,y2),(x2,y1)]]}
        testboxdata.add_feature([], geoj)
        m.add_layer(testboxdata, fillcolor=None, outlinecolor='black', outlinewidth='3px')
        
        m.render_all()
        m.view()


            
