"""
A ctypes compatible bitfield implementation.

This module provides the make_bf function, which generates bitfield
classes derived from ctypes.Union.  Because of this derivation, these
classes can be stacked into ctypes.Structures, which means they can
work directly against memory mapped data.

bitfield imports * from ctypes, therefore importing * from bitfield
will also import * from ctypes.  This can be very handy, in that it
brings in all the underlying types that you're going to need anyhow.

Works under Python 2.7+ and 3.2+

Rob Gaddi, Highland Technology, Inc.
08-May-2014

"""

from __future__ import print_function
from ctypes import *
        
#######################################################################
# Define our class member functions out here, they need to be manually
# pulled in at class creation time.
#######################################################################
        
class Bitfield(object):
    """
    Bitfield classes are a mixin to a Structure.  This class is primarily
    so as to allow other code to make explicit queries of isinstance(x, Bitfield).
    """
    _anonymous_ = ('_b',)
        
    def __iter__(self):
        """Return an iterator over the field names."""
        subfields = (t[0] for t in self._b._fields_)
        return (f for f in subfields if not f.startswith('_'))

    def keys(self):
        """Return a list of the field names."""
        return list(iter(self))

    def clone(self):
        """Return a new bitfield with the same value.
        
        The returned value is a copy, and so is no longer linked to the
        original bitfield.  This is important when the original is located
        at anything other than normal memory, with accesses to it either
        slow or having side effects.  Creating a clone, and working
        against that clone, means that only one read will occur.
        
        """
        temp = self.__class__()
        temp.base = self.base
        return temp
        
    def items(self):
        """
        Returns an iterator over the named bitfields in the structure as
        2-tuples of (key, value).  Uses a clone so as to only read from
        the underlying data once.
        
        """
        temp = self.clone()
        return [(f, getattr(temp, f)) for f in iter(self)]
        
    def update(self, E=None, **F):
        '''
        D.update([E, ]**F) -> None
        Update the bitfield from dict/iterable E and F.
        If E present and has a .keys() method, does:   for k in E: D.k = E[k]
        If E present and lacks .keys() method, does:   for (k, v) in E: D.k = v
        In either case, this is followed by:           for k in F: D.k = F[k]
        
        The entire update is applied in a single read and a single write, 
        in case the target is a memory-mapped register.  The read and write
        are independent, rather than an atomic RMW cycle.
        
        '''
        
        temp = self.clone()
        if E:
            try:
                for k in E.keys():
                    setattr(temp, k, E[k])
            except (AttributeError, ValueError):
                for k, v in E:
                    setattr(temp, k, v)
                    
        for k, v in F.items():
            setattr(temp, k, v)
            
        self.base = temp.base
        
    def __repr__(self):
        """Provide a good looking view for interactive use."""
        return "{0}({1})".format(
            self.__class__.__name__,
            ', '.join("{0}={1}".format(k, v) for k, v in self.items())
        )

#######################################################################
# Template bits for automatic docstring creation.
#######################################################################

_docstring_template = """
Bitfield subdivisions of a {name}.

Base type is {base}.
Subfields are:
"""

_docstring_field_template = '    {name:{nw}} - {n} bit {base} \n'

#######################################################################
# Exported functions.
#######################################################################

def make_bf(name, fields, basetype=c_uint32, doc=None):
    """
    Create a new Bitfield class, correctly assigning the anonymous
    fields from the Union in order to get the desired behavior.
    
    Parameters::
    
        name
            The name of the class.  This is similar to the namedtuple
            recipe, in that you'll generally pass the same name here as
            a string that you do in defining the class itself.
            
        fields
            A list of fields.  Fields are in order from the LSB of the
            underlying register, and must be 3-tuples of the form::
            
                ('fieldname', fieldtype, bits),
                ('such_as', c_uint, 5),
                ('this', c_int, 3)
                
            fieldtypes should be either c_uint, c_int, or c_bool.  make_bf
            takes care of any sizing requirements appropriately.
                
        basetype
            The type of the underlying register.  This should usually be an
            explicit size variant of c_uint, such as a c_uint32.
            
        doc
            The optional docstring for the newly created class.
    
    """
    # We need to hack on the fields array to get our integer sizes correct.
    unsigned_types = [c_uint8, c_uint16, c_uint32, c_uint64]
    signed_types = [c_int8, c_int16, c_int32, c_int64]
    
    unsigned    = next(t for t in unsigned_types if sizeof(t) >= sizeof(basetype))
    signed      = next(t for t in signed_types if sizeof(t) >= sizeof(basetype))
    
    def fixed_type(t):
        if t in unsigned_types:
            return unsigned
        elif t in signed_types:
            return signed
        elif t is c_bool:
            return unsigned
        else:
            try:
                raise TypeError("Field of type {0} not allowed, only integer and boolean types.".format(t.__name__))
            except AttributeError:
                raise TypeError("{0!r} not a class.".format(t))
    
    fields = [ (name, fixed_type(cls), size) for (name, cls, size) in fields ]

    # Define the underlying bitfield type
    bitfield = type(name + '_bitfield', (LittleEndianStructure, ), {})
    bitfield._fields_ = fields
    bitfield._pack_ = 1
    
    # Set up the docstring
    if doc is None:
        doc = _docstring_template.format(
            name = name,
            base = basetype.__name__
        )
        namewidth = max(len(t[0]) for t in fields)
        doc += ''.join(
            _docstring_field_template.format(
                name = t[0],
                nw = namewidth,
                base = t[1].__name__,
                n = t[2]
            ) for t in fields
        )

    # Set up the union
    d = {
        '_fields_' : [('base', basetype), ('_b', bitfield)],
        '__doc__' : doc
    }
    return type(name, (Union, Bitfield), d)

def print_fields(bf, *args, **kwargs):
    """
    Print all the fields of a Bitfield object to stdout.  This is
    primarly a diagnostic aid during debugging.
    """
    
    vals = {k: hex(v) for k, v in bf.items()}
    print(bf.base, vals, *args, **kwargs)
