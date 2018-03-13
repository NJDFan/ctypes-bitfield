"""
A structure walker for ctypes derived structures, including (and especially) Bitfields.

All the tools here work by mapping a Node onto the underlying object.  Node objects
are grouped into two subclasses: UnboundNode, which points to classes, and
BoundNode, which points to instances.  BoundNodes have an additional .value
property which points to the value in the structure.

This makes it simple to write recursive functions that walk ctypes based data.
For instance, a pared down version of the display function provided here might
be nothing more than::

    def print_structure(node):
        if node.depth == 0:
            print('<root>')
        else:
            print('  ' * node.depth, node.name)
        for child in node:
            print_structure(child)

Alternatively, the walk and walknode functions return Node iterators that wrap
all the recursion up on their own, allowing functions to be written without
recursion::

    def print_structure(obj):
        for node in bitfield.walk.walk(obj):
            if node.depth == 0:
                print('<root>')
            else:
                print('  ' * node.depth, node.name)                

This also allows for functional programming::

    types_used = set(n.type for n in bitfield.walk.walk(obj))
    
    def tightlypacked(st):
        leafsize = sum(n.size for n in bitfield.walk.walk(st) if not len(n))
        return ctypes.sizeof(st) == leafsize

Bitfield Notes
--------------
Given the integration of this package with the bitfield package, the implications
of Nodes walking Bitfields are worth some extra discussion.

For lack of better answer, the offset and size of Bitfield fields are defined to
be in 1/8s of bytes (bits), rather than in integer bytes.  This makes the offset
and size of fields floating point, rather than integer.  Interestingly, because
eighths are binary fractions, the usual floating point caveats about equality
and rounding error don't apply; the floating point representations are exact.

Because the introduction of a floating point number will turn any summing
calculations into floating point there is, I suppose, a concern about hitting
the dynamic range limitations of a double-precision float.  So don't ask for
baseoffsets or sum sizes if the total structure will exceed 2**50 bytes,
slightly over 1 quadrillion.  For that matter, don't declare structures of over
a quadrillion bytes in the first place.  There is no circumstance under which
any good can come of it, and I feel confident that even with Moore's law I'll
be dead and gone before you have that much RAM.

Additional Hooks
----------------
Other classes (RemoteStruct and its friends come to mind) can be hooked to
allow for structure walking functionality for object instances.  To accomplish
this, provide an _unboundreference_(self) method on the object that returns
a reference structure that can be matched to an UnboundNode, in the same way
that type(obj) returns the reference structure for an instance of a real
object.

:author:    Rob Gaddi, Highland Technology
:date:      11-May-2015
"""

from __future__ import print_function

import ctypes
import re
from collections import Sequence
from inspect import isclass
from functools import partial

from . import Bitfield, make_bf

__all__ = [
    'Node', 'BoundNode', 'UnboundNode',
    'display', 'findnode', 'offsetof',
    'walknode', 'walk'
]

bf_pyramid = make_bf('bf_pyramid', [
        ('one', ctypes.c_uint, 6),
        ('_dummy6', ctypes.c_uint, 2),
        ('two', ctypes.c_int, 4),
        ('three', ctypes.c_uint, 2),
        ('_dummyE', ctypes.c_uint, 1),
        ('b', ctypes.c_bool, 1)
    ], ctypes.c_uint32)

class TestStructureInternal(ctypes.Structure):
    _fields_ = [
        ('alpha', ctypes.c_uint32),
        ('bravo', ctypes.c_int32),
        ('charlie', ctypes.c_double),
        ('delta', bf_pyramid)
    ]

class TestStructure(ctypes.Structure):
    _fields_ = [
        ('hawaii', TestStructureInternal),
        ('idaho', ctypes.c_uint32),
        ('wyoming', ctypes.c_uint32),
        ('california', TestStructureInternal*4)
    ]
   
class Node(Sequence):
    """Abstract base class for structure walker nodes.
    
    Iterating over a Node will yield Nodes for all the children of this node.
    As a Sequence, len(node) and node[0 <= index < len(node)] are defined.  If
    the underlying object for the Node is a Structure, then node['fieldname']
    is also supported.
    
    Additional relevant fields include:
    
    parent
        The parent node of this node.  The root node has None as a
        parent.
    
    name
        The local name of this node, either an attribute like '.dac' or an array
        reference such as '[0]'
    
    offset
        The local offset of this node from its parent.  node[0] will usually
        have an offset of 0.
    
    type
        The type of this node, suchas ctypes.uint or a class derived from
        Structure.  This is the actual type, not a string representation.

    Children are accessed numerically by indexing the node.  Concrete
    subtypes must implement _getchild, _partialname, and __len__
    
    """
    
    def __init__(self, parent=None, name='', offset=0, **kwargs):
        self.name = name
        self.parent = parent
        self.offset = offset
        self.__dict__.update(kwargs)

    @property
    def parents(self):
        """A list of all the parent nodes of this node, back to the root.
        parents[0] is the root, and parents[-1] is the immediate parent.
        """
        try:
            parents = self.parent.parents
            parents.append(self.parent)
        except AttributeError:
            parents = []
        return parents
        
    def _getchild(self, idx):
        raise NotImplementedError
    
    def pathparts(self):
        """A list of the parts of the path, with the root node returning
        an empty list.
        """
        try:
            parts = self.parent.pathparts()
            parts.append(self.name)
            return parts
        except AttributeError:
            return []
    
    @property
    def root(self):
        """The root node for this node.  If this node is the root node, returns
        itself, otherwise equivalent to parents[0]."""
        try:
            return self.parent.root
        except AttributeError:
            return self
            
    @property
    def path(self):
        """The path to this node from the root node, as a string."""
        return ''.join(self.pathparts())
        
    @property
    def baseoffset(self):
        """The offset of this node from the root node."""
        try:
            return self.parent.baseoffset + self.offset
        except AttributeError:
            return self.offset
        
    @property
    def depth(self):
        """The depth of this node.
        
        The root has a depth of 0, each child of the root a depth of 1, etc.
        This is equivalent to, but slightly more efficient than, len(self.parents)
        """
        try:
            return self.parent.depth + 1
        except AttributeError:
            return 0
            
    @property
    def size(self):
        """The size, in bytes, of the element pointed to."""
        try:
            return self._realsize
        except AttributeError:
            return ctypes.sizeof(self.type)
            
    def __repr__(self):
        return "{0} {1} ({2} @ offset {3})".format(
            type(self).__name__,
            self.path,
            self.type.__name__,
            self.baseoffset
        )
        
#############################################################################
# UnboundNode logic, for walking through classes.
#############################################################################

# UnboundNodes have a few tricks under the hood.  When you create them,
# you need to provide a bunch of things to the constructor.
#
#   name        The displayed name, like '.bob'. or '[2]'
#   type        The class of this node in the structure.
#   offset      The offset of this node from its parent.
#   _getindex   The argument to give the a bound parent object to get this one,
#               such as 'bob' or int(2).

def _createunbound(kls, **info):
    """Create a new UnboundNode representing a given class."""
    
    if issubclass(kls, Bitfield):
        nodetype = UnboundBitfieldNode
    elif hasattr(kls, '_fields_'):
        nodetype = UnboundStructureNode
    elif issubclass(kls, ctypes.Array):
        nodetype = UnboundArrayNode
    else:
        nodetype = UnboundSimpleNode        
    return nodetype(type=kls, **info)
        
class UnboundNode(Node):
    """Represents a node in a ctypes subclass.
    
    There is a type element for each node, but no value."""
    
    def _childfromdict(self, d):
        kls = d.pop('type')
        child = _createunbound(kls, **d)
        child.parent = self
        return child
        
    def __getitem__(self, idx):
        """Children of UnboundNodes are UnboundNodes."""
        childinfo = self._getchild(idx)
        return self._childfromdict(childinfo)
        
class UnboundSimpleNode(UnboundNode):
    def __len__(self):
        return 0
    def _getchild(self, idx):
        raise IndexError('Simple data has no children.')
        
class UnboundStructureNode(UnboundNode):
    def __len__(self):
        return len(self.type._fields_)
    
    def _getchild(self, idx):
        if isinstance(idx, str):
            # Look this up.
            for fieldname, fieldtype, *_ in self.type._fields_:
                if fieldname == idx:
                    break
            else:
                raise KeyError(idx)
        else:
            # Must be an integer then
            fieldname, fieldtype, *_ = self.type._fields_[idx]
            
        return dict(
            name = '.' + fieldname,
            type = fieldtype,
            offset = getattr(self.type, fieldname).offset,
            _getindex = fieldname,
        )
        
class UnboundArrayNode(UnboundNode):
    def __len__(self):
        return self.type._length_
        
    def _getchild(self, idx):
        try:
            if idx >= len(self):
                raise IndexError
        except TypeError:
            raise TypeError('Array must have an integer index.')
        basetype = self.type._type_
        return dict(
            name = '[{0}]'.format(idx),
            type = basetype,
            offset = ctypes.sizeof(basetype) * idx,
            _getindex = idx,
        )
        
class UnboundBitfieldNode(UnboundNode):
    def __init__(self, *args, **kwargs):
        super(UnboundBitfieldNode, self).__init__(*args, **kwargs)
        
        # For bitfields we need to be extra clever figuring out the sizes
        # and offsets, since ctypes mangles that information.
        offset = 0
        fl = self._fieldlist = []
        for name, type, bits in self.type._fields_[1][1]._fields_:
            if not name.startswith('_'):
                fl.append( (name, type, bits/8.0, offset/8.0) )
            offset += bits
        
    def __len__(self):
        return len(self._fieldlist)
        
    def _getchild(self, idx):
        if isinstance(idx, str):
            # Look this up.
            for fieldname, fieldtype, size, offset in self._fieldlist:
                if fieldname == idx:
                    break
            else:
                raise KeyError(idx)
        else:
            # Must be an integer then
            fieldname, fieldtype, size, offset = self._fieldlist[idx]
            
        return dict(
            name = '.' + fieldname,
            type = fieldtype,
            offset = offset,
            _realsize = size,
            _getindex = fieldname,
        )
        
#############################################################################
# BoundNode logic, for walking through instances.
#############################################################################
       
# When creating BoundNodes, the three things you need are:
#   unbound => _unbound     An UnboundNode that points to the class of our object
#   valueget => _valueget   A function of no argument that returns our object
#   valueset => _valueset   An optional function of one arguement that sets our object
       
def _createbound(obj):
    """Create a new BoundNode representing a given object."""
    # Start by allowing objects to define custom unbound reference hooks
    try:
        kls = obj._unboundreference_()
    except AttributeError:
        kls = type(obj)
    
    unbound = _createunbound(kls)
    def valueget():
        return obj
    for t in (BoundBitfieldNode, BoundStructureNode, BoundArrayNode):
        if isinstance(unbound, t._unboundtype):
            kls = t
            break
    else:
        kls = BoundSimpleNode
    
    child = kls(unbound, valueget)
    return child
        
class BoundNode(Node):
    """Represents a node in a ctypes instance.
    
    Each BoundNode is connected to an UnboundNode to allow the walking
    of the underlying structure, but also has a value property that ties
    it to a value in the instance."""
    
    def __init__(self, unbound, valueget, valueset=None):
        self._unbound = unbound
        self._valueget = valueget
        self._valueset = valueset
    
    def _childgetter():
        raise NotImplementedError
    
    def _childfromdict(self, d):
        kls = d.pop('type')
        unbound = _createunbound(kls, **d)
        valueget = partial(self._childgetter(), d['_getindex'])
        valueset = partial(self._childsetter(), d['_getindex'])
        
        for t in (BoundBitfieldNode, BoundStructureNode, BoundArrayNode):
            if isinstance(unbound, t._unboundtype):
                kls = t
                break
        else:
            kls = BoundSimpleNode
        
        child = kls(unbound, valueget, valueset)
        child.parent = self
        return child
    
    def __getitem__(self, idx):
        """Children of BoundNodes are BoundNodes."""
        childinfo = self._unbound._getchild(idx)
        return self._childfromdict(childinfo)
    
    @property
    def value(self):
        return self._valueget()
    
    @value.setter
    def value(self, val):
        self._valueset(val)
    
    # Passthroughs to the unbound underneath
    def __len__(self):
        return self._unbound.__len__()
    
    @property
    def type(self):
        return self._unbound.type
    
    @property
    def offset(self):
        return self._unbound.offset
    
    @property
    def name(self):
        return self._unbound.name
    
class BoundSimpleNode(BoundNode):
    _unboundtype = UnboundSimpleNode
    
    def _childgetter(self):
        raise AttributeError
    def _childsetter(self):
        raise AttributeError
    
class BoundStructureNode(BoundNode):
    _unboundtype = UnboundStructureNode
    
    def _childgetter(self):
        return partial(getattr, self.value)
    def _childsetter(self):
        return partial(setattr, self.value)
        
class BoundArrayNode(BoundNode):
    _unboundtype = UnboundArrayNode
    
    def _childgetter(self):
        return self.value.__getitem__
    def _childsetter(self):
        return self.value.__setitem__
    
class BoundBitfieldNode(BoundStructureNode):
    _unboundtype = UnboundBitfieldNode
    
#############################################################################
# Structure walker/printers.  These make good demonstrations of function.
#############################################################################

def findnode(obj, path=''):
    """Returns a Node pointing to obj.
    
    If obj is a ctypes-derived class, an UnboundNode is returned.  If obj is
    an instance of such a class, then a BoundNode will be returned.
    
    If the optional path is provided, it is a string to look up searching
    down the original source node, such as '.overhead.window[2].page'
    """
    if isclass(obj):
        node = _createunbound(obj)
    else:
        node = _createbound(obj)
    
    # And walk it down.
    pathparts = re.split(r'\]?(?:[[.]|$)', path)
    for part in pathparts:
        if not part:    continue
        try:
            idx = int(part)
            node = node[idx]
        except ValueError:
            node = node[part]
    return node

def offsetof(obj, path):
    """Calculate the byte offset of a given path into a ctypes-derived class.
    
    path is a string to search, such as  '.overhead.window[2].page'
    """
    node = findnode(obj, path)
    return node.baseoffset

def display(obj, skiphidden=True, **printargs):
    """Print a view of obj, where obj is either a ctypes-derived class or an
    instance of such a class.  Any additional keyword arguments are passed
    directly to the print function.
    
    This is mostly useful to introspect structures from an interactive session.
    """
    
    top = findnode(obj)

    #-------------------------------------------------------------------
    # Iterate through the entire structure turning all the nodes into
    # tuples of strings for display.
    
    maxhex = len(hex(ctypes.sizeof(top.type))) - 2
    def addrformat(addr):
        if isinstance(addr, int):
            return "0x{0:0{1}X}".format(addr, maxhex)
        else:
            intpart = int(addr)
            fracbits = int((addr - intpart) * 8)
            return "0x{0:0{1}X}'{2}".format(intpart, maxhex, fracbits)
    
    def formatval(here):
        if isinstance(here, BoundSimpleNode):
            return "{0}({1})".format(here.type.__name__, here.value)
        else:
            return str(here.value)

    if isinstance(top, UnboundNode):
        headers = ['Path', 'Addr', 'Type']
        results = [
            (('  ' * n.depth) + n.name, addrformat(n.baseoffset), n.type.__name__)
                for n in walknode(top, skiphidden)
        ]
    else:
        headers = ['Path', 'Addr', 'Value']
        results = [
            (('  ' * n.depth) + n.name, addrformat(n.baseoffset), formatval(n))
                for n in walknode(top, skiphidden)
        ]
        
    #-------------------------------------------------------------------
    # Determine the maximum width of the text in each column, make the
    # column always that wide.
        
    widths = [
        max(max(len(d[col]) for d in results), len(h))
            for col, h in enumerate(headers)
    ]
    
    #-------------------------------------------------------------------
    # Print out the tabular data.
    
    def lp(args):
        print(*args, **printargs)
        
    lp(d.center(w) for d, w in zip(headers, widths))
    lp('-' * w for w in widths)
    for r in results:
        lp(d.ljust(w) for d, w in zip(r, widths))

def walknode(top, skiphidden=True):
    """Returns a recursive iterator over all Nodes under top.
    
    If skiphidden is True (the default) then structure branches starting with
    an underscore will be ignored.
    """
    if skiphidden and top.name.startswith('._'):
        return
        
    yield top
    for child in top:
        for c in walknode(child):
            yield c

def walk(obj, path='', skiphidden=True):
    """Returns a recursive iterator over all Nodes starting from
    findnode(obj, path).
    
    If skiphidden is True (the default) then structure branches starting with
    an underscore will be ignored.
    """
    
    node = findnode(obj, path)
    return walknode(node, skiphidden)
