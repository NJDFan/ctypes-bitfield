"""
Provide for SparseRanges, which are similar to range (Python2 xrange) objects
except for:
	a) No support for step values
	b) Non-contiguous areas are supported.
	
In keeping with Python convention, everything having to do with range limits
is inclusive on the low end, and exlusive on the high end.
"""

from __future__ import print_function
from warnings import warn
from collections import MutableSet
from bisect import bisect_left, bisect_right

#######################################################################
# Python 2/3 compatibility section
#######################################################################

try:
	basestring
except NameError:
	basestring = str

#######################################################################
# A couple of convenience functions will help keep the code sensible.
#######################################################################

def even(x):
	""""True if x is even."""
	return not (x & 1)
	
def odd(x):
	"""True if x is odd."""
	return (x & 1)

#######################################################################
# Define our classes
#######################################################################

_ATE = (AttributeError, TypeError)

class SparseRange(MutableSet):
	"""A SparseRange is similar to a Python 3 range object but supports
	non-contiguous ranges of data.  For instance.
	
	>>> x = SparseRange(5)
	>>> x.addrange(10, 15)
	>>> x
	SparseRange('0-5, 10-15')
	>>> list(x)
	[0, 1, 2, 3, 4, 10, 11, 12, 13, 14]
	>>> [t in x for t in (3, 8, 12)]
	[True, False, True]
	>>> SparseRange(1, 4) <= x
	True
	>>> SparseRange(3, 8) <= x
	False
	>>> len(x), x.min(), x.max(), x.span()
	(10, 0, 14, 15)
	
	As much as anything, it behaves like a set, and supports all the
	standard MutableSet operations of union (|), difference (-), intersection (&),
	and symmetric_difference (^), against iterables of integers, ranges, or
	other SparseRanges.
	
	>>> x & range(8, 20)
	SparseRange(10, 15)
	>>> x | range(20, 30) | range(100)
	SparseRange(0, 100)
	
	The add and addrange methods, and discard and discardrange methods, are
	also available if you're of a less set-theoretical bent.
	
	Two SparseRanges are equal if they have the same contents.  Ordering is
	not defined on SparseRanges.
	"""
	
	# ._ranges will be kept as a list of integers that should really be
	# treated as pairs.  Each even numbered index indictates the start of
	# a range, each odd numbered index indicates the end of a range.
	# So ._ranges might be [10, 20, 30, 40, 50, 60], indicating a range from
	# 10-20, 30-40, and 50-60.  This is to keep the efficiency high, because
	# we can use binary searches to do a lot automatically.
	#
	# ._ranges can also be considered to be a list of overlapping ranges,
	# starting with implicit infinities.  Like all Python ranges, these are
	# half-open ranges.  So, we have
	#
	#	Index		Range			Included
	#	0			(-inf)-10		False
	#	1			10-20			True
	#	2			20-30			False
	#	3			30-40			True
	#	4			40-50			False
	#	5			50-60			True
	#	6			60-(+inf)		False
	#
	# Searching using bisect_right will provide the half-open semantics discussed,
	# and yield the index number.  Note that in this conception of the _ranges,
	# included = odd(index)
	
	def __init__(self, *args):
		"""
		SparseRange() -> empty SparseRange object
		SparseRange(stop) -> SparseRange object from 0 to stop
		SparseRange(start, stop) -> SparseRange object from start to stop
		SparseRange(str) -> SparseRange object from a string, where the string
			consists of a comma separated mix of single integers or dash-separated
			ranges (where the first number is inclusive and the second exclusive).
			For instance, '10, 11, 15-20' yields a SparseRange containing the
			values [10, 11, 15, 16, 17, 18, 19].
		"""
		
		self._ranges = []
		if args:
			if len(args) == 1 and isinstance(args[0], basestring):
				# Cook down the string.
				for term in args[0].split(','):
					parts = term.split('-')
					if len(parts) == 1:
						self.add(int(parts[0]))
					elif len(parts) == 2:
						self.addrange(int(parts[0]), int(parts[1]))
					else:
						raise ValueError("Bad string section: " + term)
				
			else:
				self.addrange(*args)
			
	def __len__(self):
		return sum(stop - start for start, stop in self.pairs())
		
	def __bool__(self):
		"""Test whether the SparseRange is null (len(self) == 0)."""
		return bool(self._ranges)
	__nonzero__ = __bool__
		
	def __str__(self):
		"""Transform the SparseRange into a comma-separated list of single
		integers and dash-separated ranges.
		"""
		
		def transform_range(start, stop):
			if stop-start == 1:
				return str(start)
			else:
				return str(start) + '-' + str(stop)
				
		return ', '.join(transform_range(*p) for p in self.pairs())
		
	def __repr__(self):
		if not self._ranges:
			return self.__class__.__name__ + '()'
		elif len(self._ranges) == 2:
			return "{0}({1}, {2})".format(self.__class__.__name__, *self._ranges)
		else:
			return self.__class__.__name__ + "('" + str(self) + "')"
			
	def __copy__(self):
		obj = self.__class__()
		obj._ranges = self._ranges[:]
		return obj
	copy = __copy__
	
	@classmethod
	def fromrange(kls, rng):
		"""Translate a range object into a SparseRange."""
		
		try:
			start, stop = self._validate_simple_range(rng)
			return kls(start, stop)
		except AttributeError:							
			# This is a _much_ slower constructor.
			sr = kls()
			for val in rng:
				sr.add(val)
			return sr
		
	@staticmethod
	def _validate_simple_range(rng):
		"""Return a (start, stop) pair from a range or slice object
		with a step of 1.
		
		Raises AttributeError if not a slice with a step of 1.
		"""
		
		# Note, to support slice objects too (not sure why I want to do this
		# but there's something in my head saying to do so) we need to handle
		# cases where any field may be None.
		
		if rng.step not in (1, None):
			raise AttributeError('Bad step value.')
			
		start = rng.start
		if start is None:
			start = 0
		stop = rng.stop
		if stop is None:
			raise ValueError('Ranges must have finite end values.')
			
		return start, stop
		
	#######################################################################
	# Methods for determining whether we contain a value
	#######################################################################
	
	def __contains__(self, n):
		"""Test whether we contain a given number."""
		
		try:
			idx = bisect_right(self._ranges, n)
			return bool(idx & 1)
		except _ATE:
			return False
	
	def _contains_pair(self, start, stop):
		"""Test whether we contain all of a contiguous range."""
		
		# Hunt down the start.  If we're not strictly left of an even-numbered
		# index, then start is in a gap and we're already done.
		idx = bisect_right(self._ranges, start)
		if even(idx):
			return False
			
		# To fit the entire range from start to stop, stop must be in the same
		# section that start is.  That means that stop must also be strictly
		# left of the same index.
		return (stop <= self._ranges[idx])
	
	def isdisjoint(self, val):
		"""Test whether the intersection between self and val is null.
		
		>>> SparseRange('0-10,20-30').isdisjoint(range(10,20))
		True
		>>> SparseRange('0-30').isdisjoint(range(10,20))
		False
		>>> SparseRange(10, 20).isdisjoint(range(0, 100))
		False
		"""
		
		# Try val as a SparseRange
		try:
			return not any(self._intersect_against(*p) for p in val.pairs())
		except AttributeError:
			pass
			
		# Try val as a simple range
		try:
			start, stop = self._validate_simple_range(val)
			return not self._intersect_against(start, stop)
		except AttributeError:
			pass
			
		# Fall back to treating val as an iterable
		return not any(x in self for x in val)
		
	def issubset(self, val):
		"""Test whether every element in self is in val, i.e.
		self is a subset of val.
		
		>>> x = SparseRange('0-10,20-30')
		>>> x.issubset(range(0,30))
		True
		>>> x.issubset(SparseRange(0,25))
		False
		"""
		# Try val as a SparseRange
		try:	
			return all(val._contains_pair(*p) for p in self.pairs())
		except AttributeError:
			pass
			
		# Try val as a simple range
		try:
			start, stop = self._validate_simple_range(val)
			return (start <= self.min()) and (self.max() < stop)
		except AttributeError:
			pass
			
		# Fall back to treating val as an iterable
		return all(x in val for x in self)
	
	def issuperset(self, val):
		"""Test whether every element in val is in self, i.e.
		self is a superset of val.
		
		>>> x = SparseRange('0-10,20-30')
		>>> x.issuperset(SparseRange('5-10,23,25'))
		True
		>>> x.issuperset([5,20,25])
		True
		>>> x.issuperset(range(5,25))
		False
		"""
		# Try val as a SparseRange
		try:	
			return all(self._contains_pair(*p) for p in val.pairs())
		except AttributeError:
			pass
			
		# Try val as a simple range
		try:
			start, stop = self._validate_simple_range(val)
			return self._contains_pair(start, stop)
		except AttributeError:
			pass
			
		# Fall back to treating val as an iterable
		return all(x in self for x in val)
		
	def __le__(self, val):
		try:
			return self.issubset(val)
		except _ATE:
			return NotImplemented
		
	def __ge__(self, val):
		try:
			return self.issuperset(val)
		except _ATE:
			return NotImplemented
		
	def __eq__(self, val):
		"""Test wehether all elements in self are in val, and vice versa.
		
		>>> x = SparseRange(10, 15)
		>>> x == SparseRange(10, 20) - range(15,20)
		True
		>>> x == range(10,15)
		True
		>>> x == [10, 11, 12, 13, 14]
		True
		>>> x == [10, 11, 13, 14]
		False
		>>> x == 5
		False
		"""
		
		# Try val as a SparseRange
		try:
			return self._ranges == val._ranges
		except AttributeError:
			pass
			
		# Try val as a simple range
		try:
			start, stop = self._validate_simple_range(val)
			return self._ranges == [start, stop]
		except AttributeError:
			pass
			
		# Try val as an iterable.
		try:
			if len(val) != len(self):
				return False
			return all(x in self for x in val)
		except _ATE:
			return NotImplemented
			
	def __ne__(self, val):
		return not self.__eq__(val)
		
	def min(self):
		"""The smallest value in the range, or None for a null range.
		
		>>> SparseRange(4, 8).min()
		4
		"""
		try:
			return self._ranges[0]
		except IndexError:
			return None
		
	def max(self):
		"""The largest value in the range, or None for a null range.
		
		>>> SparseRange(4, 8).max()
		7
		"""
		try:
			return self._ranges[-1] - 1
		except IndexError:
			return None
			
	def span(self):
		"""The size of the range from min to max.  If the range is
		contiguous, span() = len().
		
		>>> SparseRange(4, 8).span()
		4
		"""
		try:
			return self._ranges[-1] - self._ranges[0]
		except IndexError:
			return 0
		
	def spanningrange(self):
		"""Create a contiguous SparseRange spanning the entirety of this one, gaps and all.
		
		>>> x = SparseRange('10-20, 30-40, 50-60')
		>>> x.spanningrange()
		SparseRange(10, 60)
		"""
		try:
			return self.__class__(self._ranges[0], self._ranges[-1])
		except IndexError:
			return self.__class__()
			
	def contiguous(self):
		"""Test whether the range is contiguous, i.e. no gaps.
		
		>>> SparseRange('10-20, 30-40, 50-60').contiguous()
		False
		>>> SparseRange('10-20').contiguous()
		True
		>>> SparseRange().contiguous()
		True
		"""
		
		return len(self._ranges) <= 2
		
	#######################################################################
	# Internal methods for adding to the range.
	#######################################################################
	
	def _addrange(self, start, stop):
		"""Add start <= n < stop as an active range.
		
		This handles merging other ranges if necessary.
		"""
		
		# Validate the data
		if start > stop:
			warn('Adding null range because start > stop.')
			return
		elif start == stop:
			warn('Adding null range because start == stop.')
			return
	
		# Thinking about this is hard, so let's have an example case in
		# which self._ranges = [10, 20, 30, 40, 50, 60], which calls out
		# three ranges: 10-20, 30-40, and 50-60.
		
		# bisect_left is our friend here, because if the value already exists
		# then the returned index is that value.
	
		# First, we need to find where our new value goes in _ranges.
		left = bisect_left(self._ranges, start)
		right = bisect_left(self._ranges, stop)
	
		# Thought exercise cases.  Here are what we'll get for left, right given
		# a few different possibilities of start, stop, and the desired _ranges
		#
		#	st,st		=> l,r			=> ranges							(action)
		#	Original state				=> [10, 20, 30, 40, 50, 60]
		#	(5, 6)		=> (0, 0)		=> [5, 6, 10, 20, 30, 40, 50, 60]	0:0 = [5,6]
		#	(5, 10)		=> (0, 0)		=> [5, 20, 30, 40, 50, 60]			0:1 = [5]
		#	(5, 25)		=> (0, 2)		=> [5, 25, 30, 40, 50, 60]			0:2 = [5,25]
		#	(5, 35)		=> (0, 3)		=> [5, 40, 50, 60]					0:3 = [5]
		#	(10, 15)	=> (0, 1)		=> [10, 20, 30, 40, 50, 60]			0:1 = [10]
		#	(10, 20)	=> (0, 1)		=> [10, 20, 30, 40, 50, 60]			0:1 = [10]
		#	(10, 25)	=> (0, 2)		=> [10, 25, 30, 40, 50, 60]			0:2 = [10,25]
		#	(10, 30)	=> (0, 2)		=> [10, 40, 50, 60]					0:3 = [10]
		#	(10, 35)	=> (0, 3)		=> [10, 40, 50, 60]					0:3 = [10]
		#	(15, 20)	=> (1, 1)		=> [10, 20, 30, 40, 50, 60]			1:1 = []
		#	(15, 25)	=> (1, 2)		=> [10, 25, 30, 40, 50, 60]			1:2 = [25]
		#	(15, 30)	=> (1, 2)		=> [10, 40, 50, 60]					1:3 = []
		#	(15, 35)	=> (1, 3)		=> [10, 40, 50, 60]					1:3 = []
		#	(20, 25)	=> (1, 2)		=> [10, 25, 30, 40, 50, 60]			1:2 = [25]
		#	(20, 30)	=> (1, 2)		=> [10, 40, 50, 60]					1:3 = []
		#	(20, 35)	=> (1, 3)		=> [10, 40, 50, 60]					1:3 = []
		#	(55, 65)	=> (5, 6)		=> [10, 20, 30, 40, 50, 65]			5:6 = [65]
		
		set_value = [True, True]
		
		if odd(left):
			# If left is an odd number, then the start is either inside a range,
			# or is equal to the existing stop point of a range.  In either
			# case, there's no reason to replace any value with start.
			set_value[0] = False
		else:
			# If left is an even number, then the start is either outside a
			# range or on the existing start point of a range.
			pass
			
		if odd(right):
			# If right is an odd number then the stop point is either inside a
			# range or the existing stop point of a range.  In either case,
			# there's no reason to replace any value with stop.
			set_value[1] = False 
		else:
			# If right is an even number, then the stop is either outside a
			# range or on the existing start point of a range.
			try:
				if self._ranges[right] == stop:
					right += 1
					set_value[1] = False 
			except IndexError:
				# We're extending the last range; that's fine.
				pass
		
		self._ranges[left:right] = [v for v, c in zip((start, stop), set_value) if c]
		assert even(len(self._ranges)), 'Wound up with odd number in _ranges.'

	def _add_SparseRange(self, rng):
		"""Add (union) a SparseRange to self.
		AttributeError if not a SparseRange.
		"""
		
		# We can optimize this if we're currently empty.
		if not self._ranges:
			self._ranges = list(rng._ranges)
		else:
			# OPTIMIZE: There's probably a faster algorithm here.  This operates
			# in O(n_rng * log n(self)) time because of all the searches, there
			# should be a way to do it in O(n_rng + n_self)
			for start, stop in rng.pairs():
				self._addrange(start, stop)
				
	def _add_rangetype(self, rng):
		"""Add (union) a range to self.
		AttributeError if not a range or slice.
		"""
		
		if len(rng) == 0:
			return
		
		try:
			start, stop = self._validate_simple_range(rng)
			self._addrange(start, stop)
		except AttributeError:
			self._add_iterable(rng)
			
	def _add_iterable(self, iterable):
		"""Add (union) an iterable to self."""
		for x in iterable:
			self.add(x)
			
	#######################################################################
	# Internal methods for removing from the range.
	#######################################################################
	
	def _delrange(self, start, stop):
		"""Remove start <= n < stop as an active range.
		
		This handles merging other ranges if necessary.
		"""
	
		# Validate the data
		if start > stop:
			warn('Deleting null range because start > stop.')
			return
		elif start == stop:
			warn('Deleting null range because start == stop.')
			return
	
		# Thinking about this is hard, so let's have an example case in
		# which self._ranges = [10, 20, 30, 40, 50, 60], which calls out
		# three ranges: 10-20, 30-40, and 50-60.
		
		# bisect_left is our friend here, because if the value already exists
		# then the returned index is that value.
	
		# First, we need to find where our new value goes in _ranges.
		left = bisect_left(self._ranges, start)
		right = bisect_left(self._ranges, stop)
	
		# Thought exercise cases.  Here are what we'll get for left, right given
		# a few different possibilities of start, stop, and the desired _ranges
		#
		#	st,st		=> l,r			=> ranges							(action)
		#	Original state				=> [10, 20, 30, 40, 50, 60]
		#	(5, 6)		=> (0, 0)		=> [10, 20, 30, 40, 50, 60]			0:0 = []
		#	(5, 15)		=> (0, 1)		=> [15, 20, 30, 40, 50, 60]			0:1 = [15]
		#	(5, 25)		=> (0, 2)		=> [30, 40, 50, 60]					0:2 = []
		#	(5, 35)		=> (0, 3)		=> [35, 40, 50, 60]					0:3 = [35]
		#	(10, 15)	=> (0, 1)		=> [15, 20, 30, 40, 50, 60]			0:1 = [15]
		#	(10, 20)	=> (0, 1)		=> [30, 40, 50, 60]					0:2 = []
		#	(10, 25)	=> (0, 2)		=> [30, 40, 50, 60]					0:2 = []
		#	(10, 30)	=> (0, 2)		=> [30, 40, 50, 60]					0:2 = []
		#	(10, 35)	=> (0, 3)		=> [35, 40, 50, 60]					0:3 = [35]
		#	(15, 17)	=> (1, 1)		=> [10, 15, 17, 20, 30, 40, 50, 60]	1:1 = [15, 17]
		#	(15, 25)	=> (1, 2)		=> [10, 15, 30, 40, 50, 60]			1:2 = [15]
		#	(15, 30)	=> (1, 2)		=> [10, 15, 30, 40, 50, 60]			1:2 = [15]
		#	(15, 35)	=> (1, 3)		=> [10, 15, 35, 40, 50, 60]			1:3 = [15, 35]
		#	(20, 25)	=> (1, 2)		=> [10, 20, 30, 40, 50, 60]			2:2 = []
		#	(20, 30)	=> (1, 2)		=> [10, 20, 30, 40, 50, 60]			2:2 = []
		#	(20, 35)	=> (1, 3)		=> [10, 20, 35, 40, 50, 60]			2:3 = [35]
		#	(20, 40)	=> (1, 3)		=> [10, 20, 50, 60]					2:4 = []
		#	(55, 65)	=> (5, 6)		=> [10, 20, 30, 40, 50, 55]			5:6 = [55]
		
		set_value = [True, True]
		
		if odd(left):
			# If left is an odd number, then the start is either inside a range,
			# or is equal to the existing stop point of a range.
			try:
				if self._ranges[left] == start:
					left += 1
					set_value[0] = False
			except IndexError:
				# We're past the last range; there's just nothing to do.
				return
			
		else:
			# If left is an even number, then the start is either outside a
			# range or on the existing start point of a range.  Either way,
			# there's no reason to be adding it into the ranges.
			set_value[0] = False
			
		if odd(right):
			# If right is an odd number then the stop point is either inside a
			# range or the existing stop point of a range.
			try:
				if self._ranges[right] == stop:
					right += 1
					set_value[1] = False 
			except IndexError:
				# We're past the last range; that's fine.
				pass
				
		else:
			# If right is an even number, then the stop is either outside a
			# range or on the existing start point of a range.  In either case,
			# we won't be writing it into the ranges.
			set_value[1] = False 
		
		self._ranges[left:right] = [v for v, c in zip((start, stop), set_value) if c]
		assert even(len(self._ranges)), 'Wound up with odd number in _ranges.'

	def _del_SparseRange(self, rng):
		"""Remove a SparseRange from self.
		Raise AttributeError if rng is not a SparseRange.
		"""
		if not self._ranges:
			return
		for start, stop in rng.pairs():
			# OPTIMIZE: There's probably a faster algorithm here.  This operates
			# in O(n_rng * log n(self)) time because of all the searches, there
			# should be a way to do it in O(n_rng + n_self)
			self._delrange(start, stop)
				
	def _del_rangetype(self, rng):
		"""Remove a range from self.
		AttributeError if not a range or slice.
		"""
		
		if len(rng) == 0:
			return
		
		try:
			start, stop = self._validate_simple_range(rng)
			self._delrange(start, stop)
		except AttributeError:
			self._del_iterable(rng)
				
	def _del_iterable(self, iterable):
		"""Remove an iterable from self."""
		for x in iterable:
			self.discard(x)

	#######################################################################
	# Iterator methods
	#######################################################################
	
	def pairs(self):
		"""Return start, stop pairs for each range contained.
		
		>>> list(SparseRange('10-20,30-40,55').pairs())
		[(10, 20), (30, 40), (55, 56)]
		"""
		it = iter(self._ranges)
		return zip(it, it)
		
	def subranges(self):
		"""Return an iterator over contiguous SparseRange objects for each range contained.
		
		>>> list(SparseRange('10-20,30-33,55').subranges())
		[SparseRange(10, 20), SparseRange(30, 33), SparseRange(55, 56)]
		"""
		return (self.__class__(start, stop) for start, stop in self.pairs())
			
	def __iter__(self):
		"""Return an iterator over all integer values contained.
		
		>>> list(SparseRange('1-10,20,21'))
		[1, 2, 3, 4, 5, 6, 7, 8, 9, 20, 21]
		"""
		return (x for rng in self.pairs() for x in range(*rng))
			
	#######################################################################
	# External methods for adding to the range
	#######################################################################
						
	def add(self, n):
		"""Add a single value to the range."""
		self._addrange(n, n+1)
			
	def addrange(self, *args):
		"""
		sr.addrange(stop) -> Add from 0 to val to the range
		sr.addrange(start, stop) -> Add from start to stop
		"""
		
		if len(args) > 2:
			raise TypeError('Expected at most 2 arguments, got ' + str(len(args)))
		elif len(args) == 2:
			self._addrange(*args)
		elif len(args) == 1:
			self._addrange(0, args[0])
		else:
			raise TypeError('Expected at least 1 argument')

	def __ior__(self, val):
		"""Append val to the range.
		val can be a SparseRange, a range, or an iterable.
		"""
		for fn in (self._add_SparseRange, self._add_rangetype, self._add_iterable):
			try:
				fn(val)
				return self
			except _ATE:
				pass
		return NotImplemented
		
	def __or__(self, val):
		"""Create a new SmartArray with the union of self and val."""
		v = self.copy()
		return v.__ior__(val)
			
	#######################################################################
	# External methods for deleting from the range.
	#######################################################################
	
	def discard(self, n):
		"""Remove a single value from the range.
		
		>>> x = SparseRange(10)
		>>> x.discard(5)
		>>> x
		SparseRange('0-5, 6-10')
		"""
		self._delrange(n, n+1)
		
	def discardrange(self, *args):
		"""
		sr.delrange(stop) -> Delete from 0 to val to the range
		sr.delrange(start, stop) -> Delete from start to stop
		
		
		>>> x = SparseRange(10)
		>>> x.discardrange(6,30)
		>>> x.discardrange(2)
		>>> x
		SparseRange(2, 6)
		"""
		
		if len(args) > 2:
			raise TypeError('Expected at most 2 arguments, got ' + str(len(args)))
		elif len(args) == 2:
			self._delrange(*args)
		elif len(args) == 1:
			self._delrange(0, args[0])
		else:
			raise TypeError('Expected at least 1 argument')
		
	def clear(self):
		"""Clear to a null range."""
		self._ranges = []
		
	def __isub__(self, val):
		"""Remove any overlap with val from the range.
		
		val can be a SparseRange, a range, or an iterable.
		
		>>> x = SparseRange(10)
		>>> x -= SparseRange('5-7,8,100-200')
		>>> x
		SparseRange('0-5, 7, 9')
		"""
		for fn in (self._del_SparseRange, self._del_rangetype, self._del_iterable):
			try:
				fn(val)
				return self
			except _ATE:
				pass
		return NotImplemented
		
	def __sub__(self, val):
		"""Create a new SparseRange with all the values from self that are not in val."""
		v = self.copy()
		return v.__isub__(val)
			
	#######################################################################
	# Finishing out the set logic.
	#######################################################################

	def _intersect_against(self, start, stop):
		"""Create a ._ranges array from self in the range (start, stop)."""
		
		# Find the highest even n (range start) such that
		# self._ranges[n] <= start.
		left = bisect_right(self._ranges, start)
		if odd(left):
			left -= 1
			
		# Find the lowest odd n (range end) such that
		# stop <= self._ranges[n]
		right = bisect_left(self._ranges, stop)
		if even(right):
			right -= 1
		
		# Extract the correct range indices
		if left > right:
			return []
		
		ranges = self._ranges[left:right+1]
		
		# Correct the ends if needed
		if ranges[0] < start:
			ranges[0] = start
		if ranges[-1] > stop:
			ranges[-1] = stop
		
		return ranges
		
	def __and__(self, val):
		"""Create a new SmartRange from the intersection between self and val.
		val can be a SmartRange, a range, or an iterable.
		"""
		
		# Try val as a SparseRange.
		nsa = self.__class__()
		
		try:
			gen = (self._intersect_against(*p) for p in val.pairs())
			nsa._ranges = sum(gen, [])
			return nsa
		except AttributeError:
			pass
			
		# Try val as a simple range.
		try:
			start, stop = self._validate_simple_range(val)
			nsa._ranges = self._intersect_against(start, stop)
			return nsa
		except AttributeError:
			pass
			
		# Try val as an iterable.
		try:
			nsa._add_iterable(x for x in val if x in self)
			return nsa
		except TypeError:
			return NotImplemented
		
	def __xor__(self, val):
		"""Create a new SparseRange with all values in only self or val but not both.
		val can be a SparseRange, a range, or an iterable.
		"""
		return (self | val) - (self & val)

	def split(self, spliton):
		"""
		Return a iterator over SparseRanges, split by either a single integer
		or an iterable of split points.  The list will always be len(spliton)+1
		elements long; null SparseRanges will be returned as necessary.
		
		>>> x = SparseRange('10-20, 30-40, 50-60')
		>>> list(x.split(35))
		[SparseRange('10-20, 30-35'), SparseRange('35-40, 50-60')]
		>>> list(x.split([20, 25, 35, 70]))
		[SparseRange(10, 20), SparseRange(), SparseRange(30, 35), SparseRange('35-40, 50-60'), SparseRange()]
		>>> list(x.split([]))
		[SparseRange('10-20, 30-40, 50-60')]
		"""
		
		try:
			it = iter(spliton)
		except TypeError:
			it = [spliton]
		
		right = self.copy()
		lastpoint = self.min()
		for point in it:
			left = right & range(lastpoint, point)
			right -= left
			yield left
			
		yield right
