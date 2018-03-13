"""
Caching structures for supporting data prefetch/cache on RemoteStructs.
"""

from time import time

from .sparserange import SparseRange

class CacheLine(object):
	"""Implements a single CacheLine, linebytes (default 32) bytes long.
	
	Data members:
		data
			A fixed length bytearray used to hold the most recent data
			
		last
			The time() the last time the line was updated.
			
		range
			A SparseRange marking the range encompassed by this CacheLine.
			data[n] is the byte at address (range.min + n)
	
	"""
	
	def __init__(self, linebytes=32):
		self.data = bytearray(linebytes)
		self.lastread = self.lastupdate = 0
		self.range = SparseRange()
		
	def invalidate(self):
		"""Mark this line as invalid."""
		self.range.clear()
		
	def hit(self, request):
		"""
		Test whether the request can be	served by this CacheLine.
		
		request
			The address range to search for as a SparseRange
		"""
		return self.range.issuperset(request)

	def offset(self, rng):
		"""Find the offset of rng.min in this CacheLine."""
		return rng.min() - self.range.min()
		
	def update(self, rng, data):
		"""
		Replace the CacheLine with the new range and data.  This
		refreshes read and update timestamps.
		"""
		
		assert rng.span() == len(data)
		self.lastread = self.lastupdate = time()
		self.data = data
		self.range = rng
		
	def write(self, rng, data):
		"""
		Replace part of the CacheLine with new data, keeping the
		same range.  This refreshes no timestamps, since some of the
		other data in the line could be getting old.
		"""
		assert rng.span() == len(data)
		offset = self.offset(rng)
		self.data[offset:offset+len(data)] = data
		
	def read(self, rng):
		"""
		Return data from the CacheLine.  This refreshes the read timestamp.
		"""
		
		self.lastread = time()
		offset = self.offset(rng)
		return self.data[offset:offset+rng.span()]
		
		
class CacheMiss(Exception):
	stat = 'misses'
	
class CacheTimeout(Exception):
	stat = 'timeouts'
		
class Cache(object):
	"""
	
	timeout
		Set to 0 for no caching, None to never time out, or a positive
		number to expire a CacheLine after timeout seconds.  Default
		is None.
	
	Statistics
	----------
	If the Cache object was initialized with stats=True (the default) then the
	Cache will track statistics on number of hits, misses, and timeouts on
	read attempts.
	
	
	"""
	
	def __init__(self, sets=8, linebytes=32, timeout=None, stats=True):
		self.timeout = timeout
		
		# Manage the statistics
		if stats:
			self.log = self._log
		else:
			self.log = lambda x : None
		self.clearstats()
		
		# Configure all the cache line information.
		self._sets = [CacheLine(linebytes) for x in range(sets)]
		self.invalidate()
		
	def clearstats(self):
		"""Clear the cache statistics."""
		self.hits = self.misses = self.timeouts = 0
		
	def invalidate(self):
		for line in self._sets:
			line.invalidate()
		self._lru = self._sets[-1]
		self._lastmiss = SparseRange()
		
	def _log(self, key):
		setattr(self, key, getattr(self, key)+1)
		
	def search(self, rng):
		"""Find the CacheLine for this range or raise an exception."""
		if self.timeout == 0:
			raise CacheMiss()
		
		# While we search through the CacheLines, take the opportunity to
		# update the lru pointer.  Has to happen sometime, right?
		for line in self._sets:
			if line.hit(rng):
				if self.timeout is not None and time() > (line.lastupdate + self.timeout):
					self._lru = line
					raise CacheTimeout()
				return line
				
			if line.lastread < self._lru.lastread:
				self._lru = line
		else:
			raise CacheMiss()
		
	def read(self, rng):
		"""Return the data from the cache or None."""
		try:
			line = self.search(rng)
			self.log('hits')
			return line.read(rng)
		except (CacheMiss, CacheTimeout) as e:
			self._lastmiss = rng
			self.log(e.stat)
			return None

	def update(self, rng, data):
		"""
		Call this to fill a CacheLine with new data after a missed read.
		Returns the newly filled CacheLine.
		"""
		assert rng >= self._lastmiss
		line = self._lru
		self._lru = self._sets[-1]
		self._lastmiss = None
		
		line.update(rng, data)
		return line

	def write(self, rng, data):
		"""If we already have a CacheLine loaded for this range then update
		the data in it.  If not, ignore it.
		"""
		try:
			# Try to save ourselves a search.
			line = self.search(rng)
			line.write(rng, data)
		except (CacheMiss, CacheTimeout):
			pass

class CachedHandler(object):
	"""
	A handler object that caches data requests.  Needs a real handler
	object to communicate with when the cache fails.
	
	CachedHandler provides both caching and prefetching by breaking the world
	into "cache line" sized data blocks (a power of 2).  At initialization time,
	specify the size of a cache line and the number of cache sets to keep.
	
	When data is requested, the cache will be searched for the requested data.
	If it's not found, the CachedHandler will use the real handler to request
	the entire cache line where the requested data can be found, and stores a
	copy of the entire thing, slicing out the requested portion and returning
	it.  The next time data from that cache line is requested, the cached data
	will be returned, rather than having to to through the real handler.
	
	As data is written, any data that is in the cache is also updated.  Data
	writes are not aggregated by the caching logic and always take place
	immediately on the real handler.
	
	As more data is requested, eventually less recently used data in the cache
	will be replaced by newer data.
	
	This makes the number of sets and the cache line size the sort of thing
	you have to mess with until the performance is good enough.  Overly long
	cache lines will cause a lot of unnecessary reads that never get looked at,
	whereas overly short ones will incur too much transaction overhead.  Too
	many cache sets will slow down searching the cache, too few will fail to
	cache enough data.
	
	As a general rule of thumb, a good cache line size will be 2-4 times the
	estimated transaction overhead.
	
	Controlling Cached Data
	=======================
	There are two mechanisms for controlling the caching.  The first is the
	timeout property.  Setting the timeout to the default of None means that
	data is valid forever; i.e. there is no expectation it may ever change
	unexpectedly.  Setting it to a number instead means that data will expire
	after that many seconds.  So a timeout of 1 means that a cache line that
	is 1 second old will no longer be considered valid, and will be fetched
	from the target again if its data is requested.
	
	Setting a timeout of 0 will disable caching.
	
	The other mechanism are the nocache and noprefetch properties, which are
	SparseRange objects.  Adding entries to these ranges using
	addrange(start, stop) will cause those addresses to be handled specially.
	
	An entry in nocache will never be retrieved from the cache when asked for
	specifically.  An entry in noprefetch will have read requests broken up so
	as to skip over that address when it hasn't been expressly asked for.
	
	An example of what might want to be on the nocache list is a register holding
	the latest ADC results.  An example of what might want to be on the noprefetch
	list is a register that causes a FIFO to be read down.
	
	Putting addresses on the nocache list will slow down access to them.  Putting
	addresses on the noprefetch list will slow down access to everything around
	them as well.
	
	The user is responsible for making sure that all addresses on the noprefetch
	list are also on the nocache list.  The easiest way to do this is to start
	by setting up both lists, then saying ch.nocache |= ch.noprefetch.
	"""
	
	def __init__(self, handler, sets=8, linebytes=32, timeout=None, stats=True):
		# Confirm that linebytes is a power of 2.
		if 2**(linebytes.bit_length() - 1) != linebytes:
			raise ValueError('linebytes must be a power of 2.')
		
		self.handler = handler
		self.linebytes = linebytes
		self.cache = Cache(sets, linebytes, timeout, stats)
		
		self.nocache = SparseRange()
		self.noprefetch = SparseRange()
		
	def _rounduptoline(self, val):
		"""Round up to the next higher multiple of linebytes."""
		lb = self.linebytes
		return (val + lb - 1) & -lb
		
	def _rounddowntoline(self, val):
		"""Round down to the next lower multiple of linebytes."""
		return val & -self.linebytes
		
	def _split_cachelines(self, addr, size):
		"""Iterate over ranges guaranteed to not cross a cache-line boundary."""
		full = SparseRange(addr, addr+size)
		
		# Round the min and max up to the next linebytes boundary.
		low = self._rounduptoline(full.min())
		high = self._rounduptoline(full.max())
		
		# Divide it up.
		splitpoints = range(low, high, self.linebytes)
		return (r for r in full.split(splitpoints) if r)
		
	def _read_safely(self, needed, desired, target=None, targetoffset=0):
		"""Return the desired data from the handler in as few reads as possible.
		
		needed is the data range we have to get
		desired is the contiguous range we'd like to pull if possible.  It may
		be modified to reflect the actual range we get.
		
		target is a bytearray we can read into, at least desired bytes long.
		targetoffset is the offset into target to put the new data
		"""		
		
		# Alright, start with the big optimization that catches 99% of cases.
		if needed == desired:
			d = self.handler.readBytes(needed.min(), needed.span())
			if target is not None:
				target[targetoffset:targetoffset+len(d)] = d
			return d
			
		# Ideally, we'd do one big read, but the noprefetch can force us to
		# split around that unless the non-prefetchable thing is actually
		# in the desired data.
		desired -= self.noprefetch
		desired |= needed
		for reg in desired.subranges():
			if reg.isdisjoint(needed):
				desired -= reg
		
		if target is None:
			target = bytearray(desired.span())
		else:
			assert len(target)-targetoffset >= desired.span()
		
		# Go do all the contiguous reads, leaving padding between.		
		baseoffset = desired.min() - targetoffset
		for (start, stop) in desired.pairs():
			offset = start - baseoffset
			d = self.handler.readBytes(start, stop-start)
			target[offset:offset+len(d)] = d
			
		return target
		
	def readBytes(self, addr, size):
		# We need to break the read request up into cacheline aligned requests.
		results = []
		
		for request in self._split_cachelines(addr, size):
			# So, the most likely case is that size is small, and that the
			# entire data is colletively either cacheable or not.
			# Let's optimize for that case.
			
			uncacheable = request & self.nocache
			if request == uncacheable:
				# If the entire request can't be read from cache, there's
				# no reason to mess around writing it in either.
				data = self.handler.readBytes(request.min(), request.span())
				
			else:
				# Check to see whether the data is in the cache.
				data = self.cache.read(request)
				if not data:
					# We've got a cache miss, time to go pull the data for the line
					x = self._rounddowntoline(request.min())
					linerange = SparseRange(x, x+self.linebytes)
					linedata = self._read_safely(
						needed = request,
						desired = linerange
					)
					line = self.cache.update(linerange, linedata)
					data = line.read(request)
					
				elif uncacheable:
					# We got some from the cache, but we need to pick some of
					# the rest up fresh.
					self._read_safely(
						needed = uncacheable,
						desired = uncacheable.spanningrange(),
						target = data,
						targetoffset = uncacheable.min()-request.min()
					)

			results.append(data)
		return bytearray().join(results)
			
	def writeBytes(self, addr, data):
		# We need to break the write request into cacheline aligned requests.
		start = 0
		for request in self._split_cachelines(addr, len(data)):
			d = data[start:start+request.span()]
			self.cache.write(request, d)
			self.handler.writeBytes(request.min(), d)
			
	@property
	def timeout(self):
		return self.cache.timeout
		
	@timeout.setter
	def timeout(self, val):
		self.cache.timeout = val 
		
	def stats(self):
		"""Get the cache statistics as 3-tuple (hit, miss, timeout)."""
		return self.cache.hits, self.cache.misses, self.cache.timeouts
		
	def clearstats(self):
		"""Clear the cache statistics."""
		self.cache.hits = self.cache.misses = self.cache.timeouts = 0
		
	def invalidate(self):
		"""Dump the cache."""
		self.cache.invalidate()
	
