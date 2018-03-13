"""
Unit tests for the remotestruct library.

Rob Gaddi, Highland Technology
19-Jun-2014
"""

from bitfield import *
import remotestruct
import unittest

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
	"""The sort of structure that might get addressed through a RemoteStruct."""
	_fields_ = [
		('serial', c_uint32),
		('dash', c_uint32),
		('_dummy2', c_uint32*2),
		('chans', SubStructure * 16),
		('checksum', c_uint32)
	]
		
class RemoteStructTest(unittest.TestCase):
	def setUp(self):
		self.basis = FakeCalTable(
			serial = 1234,
			dash = 1
		)
		self.handler = remotestruct.FakeHandler(self.basis)
		self.uut = remotestruct.Remote(
			basis = FakeCalTable,
			handler = self.handler
		)
	
	def test_simple(self):
		"""Try the simple data field accesses."""
		
		self.assertEqual(self.uut.serial, 1234) 
		self.assertEqual(self.uut.dash, 1) 

		self.uut.serial = 0x9841
		self.uut.dash = 0xBEEF
		self.assertEqual(self.uut.serial, 0x9841) 
		self.assertEqual(self.uut.dash, 0xBEEF) 
		
		self.assertEqual(self.basis.serial, 0x9841)
		self.assertEqual(self.basis.dash, 0xBEEF)
		
	def test_array_self(self):
		"""Try the offset and slope fields of chan."""
		
		self.assertEqual(len(self.uut.chans), 16)
		self.assertIsInstance(self.uut.chans, remotestruct.RemoteArray)
		self.assertIsInstance(self.uut.chans[0], remotestruct.RemoteStruct)
		
		for n, elem in enumerate(self.uut.chans):
			elem.offset = n
			elem.slope = n
			
		for n, elem in enumerate(self.basis.chans):
			self.assertEqual(n, elem.offset)
			self.assertAlmostEqual(n, elem.slope)
		
	def test_bitfield(self):
		"""Try the bitfield members in chan."""
		
		c5 = self.uut.chans[5]
		self.assertIsInstance(c5, remotestruct.RemoteStruct)
		self.assertIsInstance(c5.flags, remotestruct.RemoteBitfield)
		
		# Each update of a single Bitfield field should force
		# a 4-byte read and a 4-byte write.
		c5.flags.en0 = True
		c5.flags.en1 = True
		c5.flags.val = 0x33
		
		self.assertEqual(self.basis.chans[5].flags.base, 0x3311)
		self.assertEqual(self.handler.reads, 3)
		self.assertEqual(self.handler.writes, 3)
		self.assertEqual(self.handler.bytesRead, 3*4)
		self.assertEqual(self.handler.bytesWritten, 3*4)
		
	def test_bitfield_update(self):
		"""Make sure that RemoteBitfield.update is atomic."""
		
		self.uut.chans[0].flags.update(en0 = True, val = 0xCC)
		self.assertEqual(self.basis.chans[0].flags.base, 0xCC01)
		self.assertEqual(self.handler.reads, 1)
		self.assertEqual(self.handler.writes, 1)
		self.assertEqual(self.handler.bytesRead, 4)
		self.assertEqual(self.handler.bytesWritten, 4)
		
	def test_bitfield_keys(self):
		"""Make sure the keys method words."""
		self.assertEqual(self.uut.chans[2].flags.keys(), ['en0', 'en1', 'val'])
		
	def test_struct_failures(self):
		"""
		Make sure that the RemoteStruct asserts AttributeError on
		illegal sets and gets.
		"""
		with self.assertRaises(AttributeError):
			dummy = self.uut.bob
			
		with self.assertRaises(AttributeError):
			self.uut.bob = 0
			
	def test_bitfield_failures(self):
		"""
		Make sure that the RemoteStruct asserts AttributeError on
		illegal gets.
		"""
		
		bf = self.uut.chans[5].flags
		self.assertIsInstance(bf, remotestruct.RemoteBitfield)
		
		with self.assertRaises(AttributeError):
			dummy = bf.bob
	
		
if __name__ == '__main__':
	unittest.main()
