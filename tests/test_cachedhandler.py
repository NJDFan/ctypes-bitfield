"""
Unit tests for the remotestruct cached handler library.

Rob Gaddi, Highland Technology
27-Apr-2015
"""

from random import Random
from remotestruct import Remote, FakeHandler, CachedHandler
from bitfield import *
import unittest
from time import time, sleep

# Let's create a basic package of 4KB of source data just once.
rnd = Random(0)
sourcedata = bytearray(rnd.randint(0, 255) for _ in range(4096))

# And give it some structure.
Data = (c_uint32 * 1024)

class CacheTest(unittest.TestCase):
	sets = 8
	linewords = 32 >> 2
	
	def setUp(self):
		self.basis = Data.from_buffer_copy(sourcedata)
		self.realhandler = FakeHandler(self.basis)
		self.cachehandler = CachedHandler(
			handler = self.realhandler,
			sets=self.sets,
			linebytes=self.linewords * 4,
			timeout=None,
			stats=True
		)
		self.uut = Remote(
			basis = Data,
			handler = self.cachehandler
		)
	
	def fillCache(self):
		"""Fill the cache with data starting at address 0."""
		addr = self.linewords >> 1
		for _ in range(self.sets):
			self.assertReadData(addr)
			addr += self.linewords
	
	def assertCacheStats(self, hits, misses, timeouts=0):
		fmt = '(hits={0}, misses={1}, timeouts={2})'.format
		desired = (hits, misses, timeouts)
		actual = self.cachehandler.stats()
		if desired != actual:
			self.fail(fmt(*desired) + ' != ' + fmt(*actual))
			
	def assertHandlerStats(self, **kwargs):
		for k, v in kwargs.items():
			self.assertEqual(getattr(self.realhandler, k), v)
	
	def assertReadData(self, addr):
		"""Confirm the address read at word addr is the same through both
		the CachedHandler and in the underlying data.
		"""
		u, b = self.uut[addr], self.basis[addr]
		if u != b:
			self.fail("0x{0:08X} != 0x{1:08X} @ address {2}".format(u, b, addr))
	
	def test_random(self):
		"""Confirm random access to the data always yields correct results."""
		for _ in range(1000):
			self.assertReadData(rnd.randrange(0, len(self.basis)))
	
	def test_prefetch(self):
		"""Confirm the cache is prefetching correctly."""
		self.fillCache()
		
		# Each read should have been a cache miss, and so we should have
		# prefetched enough to fill the entire cache.
		self.assertCacheStats(0, self.sets)
		self.assertHandlerStats(reads=self.sets, bytesRead=self.sets * self.linewords * 4)
	
		# Now run the line backwards through all the data that should have been
		# cached.  None of this should require new fetches.
		for addr in range(self.sets * self.linewords - 1, -1, -1):
			self.assertReadData(addr)
			
		# Each read should have been a cache hit, so no real transactions should
		# have occured.
		self.assertCacheStats(self.sets * self.linewords, self.sets)
		self.assertHandlerStats(reads=self.sets, bytesRead=self.sets * self.linewords * 4)
		
	def test_lru(self):
		"""Confirm the cache expires lines in order of least recently used."""
		
		# Ensure that address 0 is in the LRU section.
		self.fillCache()
		self.assertEqual(self.uut[0], self.basis[0])
		self.cachehandler.clearstats()
		
		# Expire all the other sets.
		for addr in range(self.sets*self.linewords, (self.sets*2-1)*self.linewords, self.linewords):
			self.assertReadData(addr)
		
		self.assertCacheStats(0, self.sets-1)
		
		# We should still have the first line in the cache.
		self.assertReadData(0)
		self.assertReadData(self.linewords-1)
		self.assertCacheStats(2, self.sets-1)
		
	def test_writes(self):
		"""Confirm that writes post immediately and are reflected in the cache."""
		
		self.assertReadData(0)
		
		addr = self.linewords >> 1
		self.uut[addr] = 0
		self.assertEqual(self.basis[addr], 0)
		self.assertReadData(addr)
		self.assertCacheStats(1, 1)
		
	def test_timeout(self):
		"""Make sure that the timeouts work."""
		
		# Start the attempt with a 0.5 second timeout.  Guard all the logic with
		# time checks to make sure we understand what we're doing.  If we
		# run out of time, keep doubling until we can make it.
		timeout = 0.5
		
		for attempt in range(10):
			# Fill the cache
			now = time()
			self.cachehandler.timeout = timeout
			self.fillCache()
			self.assertCacheStats(0, self.sets, 0)
			self.cachehandler.clearstats()
			
			# We should be able to read everything in the cache before it expires.
			for addr in range(self.sets*self.linewords):
				self.assertReadData(addr)
			if time() > now + timeout:
				timeout *= 2
				continue
			self.assertCacheStats(self.sets*self.linewords, 0, 0)
			self.cachehandler.clearstats()
			
			# Wait out the timeout.
			sleep(timeout)
			
			# Try reading everything again.  We should get one timeout per
			# cache set, and the rest should read from the prefetches.
			for addr in range(self.sets*self.linewords):
				self.assertReadData(addr)
			self.assertCacheStats((self.sets-1)*self.linewords, 0, self.sets)
			
			# And we're done.
			break
			
		else:
			raise RuntimeError('Unable to complete test in time.')
		
if __name__ == '__main__':
	unittest.main()

	
