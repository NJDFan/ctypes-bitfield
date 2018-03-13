"""
Unit tests for the bitfield library.

Rob Gaddi, Highland Technology
19-Jun-2014
"""

from bitfield import *
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

BF_IEEE754 = make_bf('BF_IEEE754', fields = [
		('mantissa', c_uint, 23),
		('exponent', c_uint, 8),
		('sign', c_uint, 1)
	], basetype=c_float, doc='Bitfields of an IEEE754 single precision float.'
)

BF_SHORT = make_bf('BF_SHORT', fields = [
		('lsn', c_int, 4),
		('_dummy4', c_uint, 2),
		('span', c_uint, 8),
		('_dummy15', c_uint, 1),
		('msb', c_bool, 1)
	], basetype = c_uint16
)

class BitfieldTest(unittest.TestCase):
	def testSizes(self):
		"""Everything is the correct size."""
		tests = [
			(BF_FLAGS, 4),
			(BF_IEEE754, 4),
			(BF_SHORT, 2)
		]
		
		for cls, size in tests:
			self.assertEqual(sizeof(cls), size)
			x = cls()
			self.assertEqual(sizeof(x), size)

	def testShortSet(self):
		"""Setting fields on the 16-bit register."""
		
		x = BF_SHORT(msb = 1)
		self.assertEqual(x.base, 0x8000)
		x.update(msb = 0, lsn = -1)
		self.assertEqual(x.base, 0x000F)
		x.update(lsn = 0, span = 0x0F)
		self.assertEqual(x.base, 0x03C0)
		
	def testShortGet(self):
		"""Retreving fields on the 16-bit register."""
		
		x = BF_SHORT()
		x.base = 0x1234
		self.assertFalse(x.msb)
		self.assertEqual(x.span, (0x1234 & 0x3FC0) >> 6)
		self.assertEqual(x.lsn, 4)
		
	def testFloatSet(self):
		"""Setting fields on the float32 register."""
		
		x = BF_IEEE754(exponent = 127)
		self.assertEqual(x.base, 1.0)
		
		x = BF_IEEE754(exponent = 125)
		self.assertEqual(x.base, 0.25)
		x.sign = True
		self.assertEqual(x.base, -0.25)
		x.mantissa = (1 << 22)
		self.assertEqual(x.base, -0.375)
		
	def testFloatGet(self):
		"""Retreving fields on the float32 register."""
		
		x = BF_IEEE754()
		x.base = 0.375
		self.assertFalse(x.sign)
		self.assertEqual(x.mantissa, (1 << 22))
		self.assertEqual(x.exponent, 125)
		
		x.base *= 4
		self.assertFalse(x.sign)
		self.assertEqual(x.mantissa, (1 << 22))
		self.assertEqual(x.exponent, 127)
		
		x.base *= -1
		self.assertTrue(x.sign)
		self.assertEqual(x.mantissa, (1 << 22))
		self.assertEqual(x.exponent, 127)
		
	def testLongSet(self):
		"""Setting fields on the 32-bit register."""
		
		x = BF_FLAGS(en0 = 1)
		self.assertEqual(x.base, 0x00000001)
		x.en1 = True
		self.assertEqual(x.base, 0x00000011)
		x.en0 = False
		self.assertEqual(x.base, 0x00000010)
		x.val = 0xBB
		self.assertEqual(x.base, 0x0000BB10)
		
	def testLongGet(self):
		"""Retreving fields on the 32-bit register."""
		x = BF_FLAGS(0x12345678)
		
		self.assertFalse(x.en0)
		self.assertTrue(x.en1)
		self.assertEqual(x.val, 0x56)
		
class MethodTester(unittest.TestCase):
	def setUp(self):
		self.floating = BF_IEEE754(base = 0.375)
		self.flags = BF_FLAGS(en1 = True, val = 42)
		
	def testKeys(self):
		"""Check the .keys method."""
		self.assertEqual(self.floating.keys(), ['mantissa', 'exponent', 'sign'])
		self.assertEqual(self.flags.keys(), ['en0', 'en1', 'val'])
		
	def testItems(self):
		"""Check the .items method."""
		self.assertEqual(self.floating.items(),
			[	('mantissa', (1 << 22)),
				('exponent', 125),
				('sign', False),
			]
		)
		self.assertEqual(self.flags.items(),
			[	('en0', False),
				('en1', True),
				('val', 42)
			]
		)
		
	def testDir(self):
		"""Check the __dir__ method."""
		for bf in (self.floating, self.flags):
			d = dir(bf)
			self.assertIsInstance(d, list)
			for k in bf.keys():
				self.assertIn(k, d)
				
	def testClone(self):
		"""Check the .clone() method."""
		f = self.floating.clone()
		self.assertIsNot(f, self.floating)
		self.assertEqual(f.items(), self.floating.items())
		self.assertEqual(f.base, self.floating.base)
		
	def testUpdate(self):
		"""Check the .update() method."""
		self.floating.update(sign = True, exponent = self.floating.exponent-1)
		self.assertEqual(self.floating.base, 0.375 / -2)
		
		self.flags.update(val = 41)
		self.assertFalse(self.flags.en0)
		self.assertTrue(self.flags.en1)
		self.assertEqual(self.flags.val, 41)
		
if __name__ == '__main__':
	unittest.main()
