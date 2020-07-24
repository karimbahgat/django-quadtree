
from django.forms import ModelForm

from .models import QuadTree, Node

class QuadTreeForm(ModelForm):
    class Meta:
        model = QuadTree
        exclude = []

class NodeForm(ModelForm):
    class Meta:
        model = Node
        exclude = []        
