"""
Allows for ctypes derived classes, such as Structure and Bitfield, to be
accessed over a remote interface, such as TCP/IP or a VME indirection
scheme.  Effectively, this means turning requests for elements of the
structure into requests for arbitrary byte sequences, fetching them,
and managing the translation.

Protocol Handlers
-----------------

The protocol handler is responsible for transporting arbitrary data.
It is defined by having writeBytes and readBytes methods.

If, for instance, you had a mechanism whereby, over an Ethernet
socket, you could write 8 bytes to address 0x100 as 
``W 0x100 55 45 10 18 26 28 33 47``, then read back four of those
bytes by sending ``R 0x100 4`` and getting back ``55 45 10 18`` (all
of that newline delimited), then your protocol handler would look like so::

    class SerialHandler(object):
        def __init__(self, sock):
            self.sock = sock
            
        def writeBytes(self, addr, data):
            msg = "W " + hex(addr) + ' '.join(str(d) for d in data)
            self.sock.sendall(msg.encode('ascii'))
            
        def readBytes(self, addr, size):
            msg = "R 0x{0:X} {1}".format(addr, size)
            self.sock.sendall(msg.encode('ascii'))
             
            received = []
            while True:
                x = self.sock.recv(4096)
                received.append(x)
                if b'\n' in x:
                    break
                    
            msg = b''.join(received)
            data = bytes(int(b) for b in msg.split(b' '))
            return data

Note that the protocol handler doesn't care about the underlying data
representation; these bytes could be parts of strings, floats, or integers.

The binary data for the readBytes and writeBytes methods is not required to
be mutable; either bytes() or bytearray() data may be provided.

Remote Classes
--------------

Underneath the hood are three very similar classes, the RemoteStruct,
RemoteArray, and RemoteBitfield.  These classes can be called out
directly, or the Remote function (which pretends to be a class initializer)
will create whichever is appropriate.

Whether you instantiate a class, or let the Remote function do it, the
initialization convention will be the same::

    Remote(basis, handler)
    RemoteStruct(basis, handler)
    RemoteArray(basis, handler)
    RemoteBitfield(basis, handler)
    
Where basis is the underlying structure to map (a class, not a instance),
and handler is the protocol handler to use.

The constructors handle nested structure definitions appropriately.  So,
to take the following set of code::

    BF_FLAGS = make_bf('BF_FLAGS', fields = [
            ('en0', c_uint, 1),
            ('_dummy1', c_uint, 3),
            ('en1', c_uint, 1),
            ('_dummy5', c_uint, 3),
            ('val', c_uint, 8),
            ('_dummy16', c_uint, 16)
        ],
        basetype = c_uint32
    ) 

    class SubStructure(Structure):
        _fields_ = [
            ('flags', BF_FLAGS),
            ('_dummy1', c_uint32),
            ('offset', c_int32),
            ('slope', c_float)
        ]

    class FakeCalTable(Structure):
        _fields_ = [
            ('serial', c_uint32),
            ('dash', c_uint32),
            ('_dummy2', c_uint32*2),
            ('chans', SubStructure * 16),
            ('checksum', c_uint32)
        ]
        
    target = Remote(FakeCalTable, handler)
    
The structure built will be::

    target                      RemoteStruct
        .serial                 <data>
        .dash                   <data>
        .chans                  RemoteArray
            [0]                 RemoteStruct
                .flags          RemoteBitfield
                    .en0        <data>
                    .en1        <data>
                    .val        <data>
                .offset         <data>
                .slope          <data>
            [1]                 RemoteStruct
                .flags          RemoteBitfield
                ...

:author: Rob Gaddi, Highland Technology
:date:   03-Jun-2014

""""""
Allows for ctypes derived classes, such as Structure and Bitfield, to be
accessed over a remote interface, such as TCP/IP or a VME indirection
scheme.  Effectively, this means turning requests for elements of the
structure into requests for arbitrary byte sequences, fetching them,
and managing the translation.

Protocol Handlers
-----------------

The protocol handler is responsible for transporting arbitrary data.
It is defined by having writeBytes and readBytes methods.

If, for instance, you had a mechanism whereby, over an Ethernet
socket, you could write 8 bytes to address 0x100 as 
``W 0x100 55 45 10 18 26 28 33 47``, then read back four of those
bytes by sending ``R 0x100 4`` and getting back ``55 45 10 18`` (all
of that newline delimited), then your protocol handler would look like so::

    class SerialHandler(object):
        def __init__(self, sock):
            self.sock = sock
            
        def writeBytes(self, addr, data):
            msg = "W " + hex(addr) + ' '.join(str(d) for d in data)
            self.sock.sendall(msg.encode('ascii'))
            
        def readBytes(self, addr, size):
            msg = "R 0x{0:X} {1}".format(addr, size)
            self.sock.sendall(msg.encode('ascii'))
             
            received = []
            while True:
                x = self.sock.recv(4096)
                received.append(x)
                if b'\n' in x:
                    break
                    
            msg = b''.join(received)
            data = bytes(int(b) for b in msg.split(b' '))
            return data

Note that the protocol handler doesn't care about the underlying data
representation; these bytes could be parts of strings, floats, or integers.

The binary data for the readBytes and writeBytes methods is not required to
be mutable; either bytes() or bytearray() data may be provided.

Remote Classes
--------------

Underneath the hood are three very similar classes, the RemoteStruct,
RemoteArray, and RemoteBitfield.  These classes can be called out
directly, or the Remote function (which pretends to be a class initializer)
will create whichever is appropriate.

Whether you instantiate a class, or let the Remote function do it, the
initialization convention will be the same::

    Remote(basis, handler)
    RemoteStruct(basis, handler)
    RemoteArray(basis, handler)
    RemoteBitfield(basis, handler)
    
Where basis is the underlying structure to map (a class, not a instance),
and handler is the protocol handler to use.

The constructors handle nested structure definitions appropriately.  So,
to take the following set of code::

    BF_FLAGS = make_bf('BF_FLAGS', fields = [
            ('en0', c_uint, 1),
            ('_dummy1', c_uint, 3),
            ('en1', c_uint, 1),
            ('_dummy5', c_uint, 3),
            ('val', c_uint, 8),
            ('_dummy16', c_uint, 16)
        ],
        basetype = c_uint32
    ) 

    class SubStructure(Structure):
        _fields_ = [
            ('flags', BF_FLAGS),
            ('_dummy1', c_uint32),
            ('offset', c_int32),
            ('slope', c_float)
        ]

    class FakeCalTable(Structure):
        _fields_ = [
            ('serial', c_uint32),
            ('dash', c_uint32),
            ('_dummy2', c_uint32*2),
            ('chans', SubStructure * 16),
            ('checksum', c_uint32)
        ]
        
    target = Remote(FakeCalTable, handler)
    
The structure built will be::

    target                      RemoteStruct
        .serial                 <data>
        .dash                   <data>
        .chans                  RemoteArray
            [0]                 RemoteStruct
                .flags          RemoteBitfield
                    .en0        <data>
                    .en1        <data>
                    .val        <data>
                .offset         <data>
                .slope          <data>
            [1]                 RemoteStruct
                .flags          RemoteBitfield
                ...

:author: Rob Gaddi, Highland Technology
:date:   24-Aug-2015

"""

from .remotestruct import *
from .cache import CachedHandler
