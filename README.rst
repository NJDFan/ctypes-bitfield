===============
ctypes-bitfield
===============

The ctypes-bitfield library consists of two modules, `bitfield` and `remotestruct`.

`bitfield` provides a mechanism for creating ctypes compatible
implementations of registers made up of bitfields.

`remotestruct` allows for ctypes derived classes, such as Structure and Bitfield, to be
accessed over a remote interface, such as TCP/IP or a VME indirection
scheme.

bitfield
--------

`bitfield` provides a mechanism for creating ctypes compatible
implementations of registers made up of bitfields.  The base
ctypes library already provides much of this functionality, but the
bitfield builder implementation wraps it up for simpler usage and avoids some
of the quirky behaviors.

Normally the underlying register type would be a fixed size integer, a 
c_uint16 or c_uint64 or the like.  However, a somewhat strange example usage
would look something like this::

    >>> from bitfield import *
    >>> IEEE754 = make_bf('IEEE754', [
    ...     ('mantissa', c_uint, 23),
    ...     ('exponent', c_uint, 8),
    ...     ('sign', c_uint, 1)
    ... ], basetype=c_float, doc='Bitfields of an IEEE754 single precision float.')
    >>> x = IEEE754()
    >>> x.keys()
    ['mantissa', 'exponent', 'sign']
    >>> x.base = 5.0
    >>> list(x.items()) #doctest: +ELLIPSIS
    [('mantissa', 2097152...), ('exponent', 129...), ('sign', 0...)]
    >>> x.sign = 1
    >>> x.base
    -5.0
    >>> x.exponent -= 2
    >>> x.base
    -1.25
    >>> x.update(sign = 0, mantissa = 0)
    >>> x.base
    1.0
    
Bitfield objects are derived from ctypes.Union.  Because of this derivation,
these classes can be stacked into ctypes.Structures, which means they can
work directly on memory mapped data.  If the memory-mapped data is volatile, 
such as hardware registers, then the fact that the update() method operates
on the entire register in one write, rather than one write per field, may
be of use.

remotestruct
------------
`remotestruct` allows for ctypes derived classes, such as Structure and 
Bitfield, to be accessed over a remote interface, such as TCP/IP or a VME 
indirection scheme.  Effectively, this means turning requests for elements 
of the structure into requests for arbitrary byte sequences, fetching them, 
and managing the translation.

If, for instance, you had a mechanism whereby, over an Ethernet socket, you 
could write 8 bytes to address 0x100 as ``W 0x100 55 45 10 18 26 28 33 47``, 
then read back four of those bytes by sending ``R 0x100 4`` and getting back 
``55 45 10 18`` (all of that newline delimited), then you would write a 
protocol handler::

    >>> class SerialHandler(object):
    ...    def __init__(self, sock):
    ...        self.sock = sock
    ...        
    ...    def writeBytes(self, addr, data):
    ...        msg = "W " + hex(addr) + ' '.join(str(d) for d in data)
    ...        self.sock.sendall(msg.encode('ascii'))
    ...        
    ...    def readBytes(self, addr, size):
    ...        msg = "R 0x{0:X} {1}".format(addr, size)
    ...        self.sock.sendall(msg.encode('ascii'))
    ...         
    ...        received = []
    ...        while True:
    ...            x = self.sock.recv(4096)
    ...            received.append(x)
    ...            if b'\n' in x:
    ...                break
    ...                
    ...        msg = b''.join(received)
    ...        data = bytes(int(b) for b in msg.split(b' '))
    ...        return data

    >>> class DataStructure(Structure):
    ...     _fields_ = [
    ...         ('flags', c_uint32),
    ...         ('_dummy1', c_uint32),
    ...         ('offset', c_int32),
    ...         ('slope', c_float)
    ...     ]
    
    >>> sock = socket.create_connection(('1.2.3.4', 80))
    >>> handler = SerialHandler(sock)
    >>> rs = remotestruct.Remote(DataStructure, handler)
    >>> rs.flags
    5
    >>> rs.flags = 183
    >>> rs.flags
    183

CachedHandler
=============
RemoteStructs can suffer from performance issues over slow transports; fetching
data that you know hasn't changed over and over again just because it was easier
to write the code that way.  The solution to this is to wrap the handler in a
CachedHandler, which provides a flexible caching mechanism to prevent pulling
known data.  The CachedHandler will, rather than pulling only the data requested,
prefetch an entire aligned "cache line" of data based on the presumption that
the next data you'll need is likely to be physically near to the data you're 
currently asking for.  So with the default 32 byte cacheline, a request for the
2 bytes at address 40-41 will request all bytes 32-63, and store them in one of
the cache sets (default 8).  This data will remain cached until it either times
out or the cache set is overwritten by a new cacheline.

Repeating the previous example with a CachedHandler would add::

    >>> sock = socket.create_connection(('1.2.3.4', 80))
    >>> basehandler = SerialHandler(sock)
    >>> cachedhandler = CachedHandler(
    ...     handler=basehandler,
    ...     timeout=2.5
    ... )
    >>> rs = remotestruct.Remote(DataStructure, cachedhandler)
    >>> rs.flags
    5
    >>> rs.flags = 183
    >>> rs.flags
    183

The CachedHandler is most useful with a timeout, which dictates how old data
in the cache can be before it expires; in the example above the timeout is set
to 2.5 seconds.  A timeout of None means that data will never expire; a timeout
of 0 means that data is always expired, effectively disabling the cache.

The CachedHandler has many options to control the number of cache sets and the
length of cache lines which you can easily spend your life tuning to try to get
the "perfect" cache settings.  Don't do this.  The CachedHandler can be
initialized with stats=True, which will make the cache keep statistics on hits,
misses and timeouts.  If the cache is getting too many timeouts then you're 
grabbing more data than you can use and should turn the cache line length down.
If you're getting too many misses then more cache sets or longer cache lines
will be your solution, depending on your data access patterns.

The CachedHandler also has nocache and noprefetch options to fine-tune control
performance; this can be essential to prevent destructive register accesses.

Changelog
---------

0.3.3
    Updated collections.MutableSet to collections.abc.MutableSet to avoid
    deprecation.
    
0.3.2
    Fixed problem with the CachedHandler sometimes getting bytes instead of
    bytearray.

0.3.1
    Fixed some packaging problems.

0.3.0
    Turned the .items iterator into a list.  It's never going to be so long
    that the overhead is a problem, and it makes interactive use from the
    command line so much easier.
    
    Added the CachedHandler, and moved bitfield and remotestruct from being
    single modules to being full packages.

Works under Python 2.7+ and 3.2+

:author:    Rob Gaddi, Highland Technology, Inc.
:date:      28-May-2020
:version:   0.3.3
