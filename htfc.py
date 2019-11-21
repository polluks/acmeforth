#!/usr/bin/python3

DEBUG = 0

import ctypes
import os
import readline
import sys
import xc

class Word:
	def __init__(self, name, xt, immediate):
		self.name = name
		self.xt = xt
		self.body = None		# points to the first cell to execute as part of the word
		self.body_end = None		# points to the cell after the ; exit
		self.immediate = immediate

	@property
	def xt(self):
		return self.__xt

	@xt.setter
	def xt(self, xt):
		self.__xt = xt
		if xt in xt_words:
			sys.exit("xt " + str(xt) + " used by multiple words")
		xt_words[xt] = self

	def __repr__(self):
		return self.name

words = {}
xt_words = {}
stack_underflow_area = [-1] * 32
stack = stack_underflow_area.copy()
return_stack = []
leave_stack = []
tib_count = 0
latest = None
ip = 0

# Forth variable space.
to_in_addr = 0
state_addr = to_in_addr + 2
base_addr = state_addr + 2
word_addr = base_addr + 2
pictured_numeric_addr = word_addr + 40
tib_addr = pictured_numeric_addr + 70
original_tib_addr = tib_addr
here = tib_addr + 200

class Heap:
	def __init__(self, size):
		self.heap = [None] * size

	def __getitem__(self, i):
		c = self.heap[i]
		return ord(c) if type(c) == type(' ') else c

	def __setitem__(self, i, val):
		self.heap[i] = val

	def __len__(self):
		return len(self.heap)

heap = Heap(65536)
heap[base_addr] = 10

digits = "0123456789abcdefghijklmnopqrstuvwxyz"

def append(val):
	global here
	assert type(val) == type(0) or type(val) == type("") or callable(val) or val == None
	heap[here] = val
	here += 1

def set_state(flag):
	v = 0xff if flag else 0
	heap[state_addr] = v
	heap[state_addr + 1] = v

def BASE():
	stack.append(base_addr)

def STATE():
	stack.append(state_addr)

def TO_IN():
	stack.append(to_in_addr)

def add_word(name, xt, immediate = False):
	words[name] = Word(name, xt, immediate)

def is_number(word):
	base = heap[base_addr]
	assert base
	if word[0] == "#":
		base = 10
		word = word[1:]
		if not word:
			return False
	elif word[0] == "$":
		base = 16
		word = word[1:]
		if not word:
			return False
	elif word[0] == "%":
		base = 2
		word = word[1:]
		if not word:
			return False
	elif len(word) == 3 and word[0] == "'" and word[2] == "'":
		return True
	if word[0] == '-':
		word = word[1:]
		if not word:
			return False
	for d in word.lower():
		if d not in digits:
			return False
		if digits.index(d) >= base:
			return False
	return True

def evaluate_number(word):
	global stack
	number = 0
	base = heap[base_addr]
	if word[0] == "#":
		base = 10
		word = word[1:]
	elif word[0] == "$":
		base = 16
		word = word[1:]
	elif word[0] == "%":
		base = 2
		word = word[1:]
	elif word[0] == "'":
		stack.append(ord(word[1]))
		return
	negate = word[0] == '-'
	if negate:
		word = word[1:]
	for d in word.lower():
		number *= base
		number += digits.index(d)
	if negate:
		number = -number
	stack.append(ctypes.c_short(number).value)

def evaluate(word):
	global stack
	if word.lower() in words:
		word = words[word.lower()]
		word.xt()
		if len(stack) < len(stack_underflow_area):
			print("Stack underflow in '" + word.name + "'")
			stack = stack_underflow_area.copy()
			QUIT()
	else:
		if is_number(word):
			evaluate_number(word)
		else:
			print("Undefined word", word)
			QUIT()

def SOURCE_ID():
	if tib_addr != original_tib_addr:
		stack.append(-1)		# evaluate
	elif INPUT_FILE:
		stack.append(INPUT_FILE)	# file
	else:
		stack.append(0)			# console

def REFILL():
	global INPUT_FILE
	global tib_count

	SOURCE_ID()
	source_id = stack.pop()
	if source_id == -1:	# evaluated string
		stack.append(0)
	elif source_id == 0:	# reading from console
		tib_count = 0
		for c in input():
			heap[tib_addr + tib_count] = c
			tib_count += 1
		heap[to_in_addr] = 0
		stack.append(-1)
	else:
		l = source_id.readline()
		if l:
			l = l.rstrip()
			tib_count = len(l)
			for i in range(tib_count):
				heap[tib_addr + i] = l[i]
			heap[to_in_addr] = 0
			stack.append(-1)
		else:	# EOF
			stack.append(0)
			INPUT_FILE = None

def parse(delimiter):
	if type(delimiter) == type(' '):
		delimiter = ord(delimiter)

	# skips leading whitespace
	while heap[to_in_addr] < tib_count:
		if chr(heap[tib_addr + heap[to_in_addr]]).isspace():
			heap[to_in_addr] += 1
		else:
			break

	# reads the word
	word = ""
	while heap[to_in_addr] < tib_count:
		c = heap[tib_addr + heap[to_in_addr]]
		heap[to_in_addr] += 1
		if delimiter == ord(' ') and chr(c).isspace():
			break
		elif c == delimiter:
			break
		word += chr(c)

	return word

def read_word():
	while True:
		return parse(' ')
		if word:
			return word
		REFILL()
		stack.pop()

def CREATE():
	global latest
	latest = read_word().lower()
	previous_word = None
	if latest in words:
		previous_word = words[latest]
		SOURCE_ID()
		if stack.pop() == 0:
			print("redefined " + previous_word.name)
	words[latest] = Word(latest, lambda l=here : stack.append(l), False)
	words[latest].body = here
	words[latest].body_end = here
	return previous_word

def VARIABLE():
	CREATE()
	stack.append(0)
	COMMA()
	words[latest].body_end = here

def compile(word):
	global stack
	if word.lower() in words:
		word = word.lower()
		if words[word].immediate:
			words[word].xt()
		else:
			append(words[word].xt)
	else:
		if is_number(word):
			evaluate_number(word)
			if stack[-1] & 0xff00:
				append(words["lit"].xt)
				COMMA()
			else:
				append(words["litc"].xt)
				C_COMMA()
		else:
			sys.exit("unknown word '" + word + "'")

def interpret_tib():
	while heap[to_in_addr] <= tib_count:
		word = read_word()
		if not word:
			return
		if heap[state_addr]:
			if DEBUG:
				print("COMPILE", word)
			compile(word)
		else:
			if DEBUG:
				print("EVALUATE", word)
			evaluate(word)
		if DEBUG:
			print("stack", stack[len(stack_underflow_area):])

def C_STORE():
	dst = stack[-1]
	v = stack[-2]
	heap[dst] = v & 0xff
	TWODROP()

def STORE():
	dst = stack[-1]
	v = stack[-2]
	if type(v) == type(0):
		heap[dst] = v & 0xff
		heap[dst + 1] = v >> 8
	elif callable(v) or v == None:
		heap[dst] = v
		heap[dst + 1] = None
	else:
		assert False
	TWODROP()

def PLUSSTORE():
	heap[stack.pop()] += stack.pop()

def docol(ip_):
	global ip
	return_stack.append(ip)
	ip = ip_
	while ip:
		code = heap[ip]
		ip += 1
		if callable(code):
			if DEBUG:
				print("exec", code, ip)
			code()
			if DEBUG:
				print(stack[len(stack_underflow_area):], ip)
		else:
			stack.append(code)

def DEPTH():
	stack.append(len(stack) - len(stack_underflow_area))

compiling_word = None

def COLON():
	global compiling_word
	old_word = CREATE()
	compiling_word = words[latest]
	words[latest] = old_word
	compiling_word.xt = lambda ip = compiling_word.body : docol(ip)
	set_state(True)

def SEMICOLON():
	global compiling_word
	append(words["exit"].xt)
	set_state(False)
	if compiling_word:
		words[latest] = compiling_word
		compiling_word.body_end = here
		compiling_word = None

def DROP():
	stack.pop()

def TWODROP():
	stack.pop()
	stack.pop()

def DUP():
	stack.append(stack[-1])

def TWODUP():
	stack.append(stack[-2])
	stack.append(stack[-2])

def OVER():
	stack.append(stack[-2])

def PICK():
	stack.append(stack[-stack.pop()-1])

def ROLL():
	stack.append(stack.pop(-stack.pop()-1))

def ROT():
	stack.append(2)
	ROLL()

def SWAP():
	stack.append(1)
	ROLL()

def BRANCH():
	global ip
	ip = heap[ip] + (heap[ip + 1] << 8)

def ZBRANCH():
	global ip
	if stack.pop():
		ip += 2
	else:
		BRANCH()

def ELSE():
	append(words["branch"].xt)
	stack.append(0)
	COMMA()
	heap[stack[-1]] = here & 0xff
	heap[stack[-1] + 1] = here >> 8
	stack[-1] = here - 2

def THEN():
	heap[stack[-1]] = here & 0xff
	heap[stack[-1] + 1] = here >> 8
	stack.pop()

def ZERO_LT():
	stack[-1] = -1 if stack[-1] < 0 else 0

def NEGATE():
	INVERT()
	ONEPLUS()

def QUIT():
	global tib_addr
	return_stack.clear()
	tib_addr = original_tib_addr

	while True:
		REFILL()
		stack.pop()
		interpret_tib()
		SOURCE_ID()
		if stack.pop() == 0:
			print(" compiled" if heap[state_addr] else " ok")

def I():
	stack.append(return_stack[-2])

def J():
	stack.append(return_stack[-4])

def DO():
	append(words["(do)"].xt)
	stack.append(here)

def _DO():
	TO_R() # index
	TO_R() # limit

def _QUESTION_DO():
	global ip
	TWODUP()
	EQUALS()
	if stack.pop():
		# Don't enter loop.
		TWODROP()
		BRANCH()
	else:
		# Enter loop.
		_DO()
		ip += 2

def QUESTION_DO():
	append(words["(?do)"].xt)
	leave_stack.append(here)
	stack.append(0)
	COMMA()
	stack.append(here)

def resolve_leaves():
	while leave_stack:
		assert stack
		# The additional -1 is for ?DO, which has a cell between (?DO) and the loop body.
		if leave_stack[-1] < stack[-1] - 2:
			break
		dst = leave_stack.pop()
		heap[dst] = here & 0xff
		heap[dst + 1] = here >> 8

def LOOP():
	append(words["(loop)"].xt)
	DUP()
	COMMA()
	resolve_leaves()
	stack.pop()

def _LOOP():
	global ip
	return_stack[-2] = ctypes.c_short(return_stack[-2] + 1).value
	if return_stack[-2] == return_stack[-1]:
		return_stack.pop()
		return_stack.pop()
		ip += 2
	else:
		ip = heap[ip] + (heap[ip + 1] << 8)

def LEAVE():
	UNLOOP()
	append(words["branch"].xt)
	leave_stack.append(here)
	stack.append(0)
	COMMA()

def UNLOOP():
	append(words["r>"].xt)
	append(words["r>"].xt)
	append(words["2drop"].xt)

# forth-standard.org
def WITHIN(): # ( test lower upper -- flag )
	OVER()
	MINUS()
	TO_R()
	MINUS()
	R_TO()
	U_LESS()

def PLUSLOOP():
	append(words["(+loop)"].xt)
	DUP()
	COMMA()
	resolve_leaves()
	stack.pop()

def _PLUSLOOP():
	global ip
	increment = stack.pop()
	if not increment:
		ip = heap[ip] + (heap[ip + 1] << 8)
		return
	pre_increment = return_stack[-2]
	return_stack[-2] = ctypes.c_short(return_stack[-2] + increment).value
	post_increment = return_stack[-2]
	test_value = return_stack[-1] - 1
	stack.append(test_value)
	if increment > 0:
		stack.append(pre_increment)
		stack.append(post_increment)
	else:
		stack.append(post_increment)
		stack.append(pre_increment)
	# crossed limit?
	WITHIN()
	if stack.pop():
		# yes, exit loop
		return_stack.pop()
		return_stack.pop()
		ip += 2
	else:
		# no, iterate
		ip = heap[ip] + (heap[ip + 1] << 8)

def CR():
	print()

def ALLOT():
	global here
	diff_in_address_units = stack.pop()
	here += diff_in_address_units
	words[latest].body_end += diff_in_address_units

def SLITERAL():
	global ip
	stack.append(ip + 1)
	stack.append(heap[ip])
	ip += heap[ip] + 1

def S_QUOTE():
	s = ""
	while heap[to_in_addr] < tib_count:
		c = heap[tib_addr + heap[to_in_addr]]
		heap[to_in_addr] += 1
		if c == ord('"'):
			break
		s += chr(c)
	append(words["sliteral"].xt)
	append(len(s))
	for c in s:
		append(c)

def S_BACKSLASH_QUOTE():
	s = ""
	while heap[to_in_addr] < tib_count:
		c = heap[tib_addr + heap[to_in_addr]]
		heap[to_in_addr] += 1
		if c == ord('\\'):
			c = heap[tib_addr + heap[to_in_addr]]
			heap[to_in_addr] += 1
			l = []
			if 	c == ord('a'): l = [7]
			elif 	c == ord('b'): l = [8]
			elif 	c == ord('e'): l = [27]
			elif 	c == ord('f'): l = [12]
			elif 	c == ord('l'): l = [10]
			elif 	c == ord('m'): l = [13, 10]
			elif 	c == ord('n'): s += os.linesep
			elif 	c == ord('q'): l = [34]
			elif 	c == ord('r'): l = [13]
			elif 	c == ord('t'): l = [9]
			elif 	c == ord('v'): l = [11]
			elif 	c == ord('z'): l = [0]
			elif 	c == ord('"'): l = [34]
			elif 	c == ord('\\'): l = [92]
			elif 	c == ord('x'):
				msd = digits.index(chr(heap[tib_addr + heap[to_in_addr]]).lower())
				heap[to_in_addr] += 1
				lsd = digits.index(chr(heap[tib_addr + heap[to_in_addr]]).lower())
				heap[to_in_addr] += 1
				s += chr(msd * 16 + lsd)
			for c in l:
				s += chr(c)
		elif c == ord('"'):
			break
		else:
			s += chr(c)

	append(words["sliteral"].xt)
	append(len(s))
	for c in s:
		append(c)

def C_QUOTE():
	S_QUOTE()
	append(words["drop"].xt)
	append(words["1-"].xt)

def FETCH():
	v = heap[stack[-1]]
	if type(v) == type(0):
		v += heap[stack[-1] + 1] << 8
	stack[-1] = v

def C_FETCH():
	stack[-1] = heap[stack[-1]]

def TO_R():
	return_stack.append(stack.pop())

def R_TO():
	stack.append(return_stack.pop())

def R_FETCH():
	stack.append(return_stack[-1])

def TWO_R_FETCH():
	R_TO()
	R_TO()
	TWODUP()
	TO_R()
	TO_R()
	SWAP()

def TWO_TO_R():
	SWAP()
	TO_R()
	TO_R()

def TWO_R_TO():
	R_TO()
	R_TO()
	SWAP()

def TYPE():
	l = heap[stack[-2] : stack[-2] + stack[-1]]
	for i in range(len(l)):
		if type(l[i]) == int:
			l[i] = chr(l[i])
	print("".join(l), end='', flush=True)
	TWODROP()

def EXIT():
	global ip
	if return_stack:
		ip = return_stack.pop()
	else:
		ip = None

def LPAREN():
	while True:
		while heap[to_in_addr] < tib_count:
			if heap[tib_addr + heap[to_in_addr]] == ord(')'):
				heap[to_in_addr] += 1
				return
			heap[to_in_addr] += 1
		REFILL()
		stack.pop()

def EQUALS():
	stack[-2] = -1 if stack[-1] == stack[-2] else 0
	stack.pop()

def ONEPLUS():
	l = ctypes.c_short(stack[-1])
	l.value += 1
	stack[-1] = l.value

def ONEMINUS():
	l = ctypes.c_short(stack[-1])
	l.value -= 1
	stack[-1] = l.value

def PLUS():
	l = ctypes.c_short(stack[-2])
	l.value += stack[-1]
	stack.pop()
	stack[-1] = l.value

def MINUS():
	l = ctypes.c_short(stack[-2])
	l.value -= stack[-1]
	stack.pop()
	stack[-1] = l.value

def ABS():
	l = ctypes.c_short(stack[-1])
	l.value = abs(l.value)
	stack[-1] = l.value

def ZEQUAL():
	stack[-1] = 0 if stack[-1] else -1

def AND():
	stack[-2] &= stack[-1]
	stack.pop()

def OR():
	stack[-2] |= stack[-1]
	stack.pop()

def XOR():
	stack[-2] ^= stack[-1]
	stack.pop()

def RSHIFT():
	l = ctypes.c_ushort(stack[-2])
	l.value >>= stack[-1]
	stack.pop()
	stack[-1] = l.value

def LSHIFT():
	l = ctypes.c_short(stack[-2])
	l.value <<= stack[-1]
	stack[-2] = l.value
	stack.pop()

def INVERT():
	stack[-1] = ~stack[-1]

def CONSTANT():
	CREATE()
	v = stack.pop()
	words[latest].xt = lambda : stack.append(v)
	words[latest].constant_value = v

def TWOMUL():
	stack.append(1)
	LSHIFT()

def TWODIV():
	stack[-1] >>= 1

def U_LESS():
	if stack[-1] < 0:
		stack[-1] += 2 ** 16
	if stack[-2] < 0:
		stack[-2] += 2 ** 16
	stack[-2] = -1 if stack[-2] < stack[-1] else 0
	stack.pop()

def LESS_THAN():
	stack[-2] = -1 if stack[-2] < stack[-1] else 0
	stack.pop()

def GREATER_THAN():
	stack[-2] = -1 if stack[-2] > stack[-1] else 0
	stack.pop()

def MULTIPLY():
	v = ctypes.c_short(stack[-2])
	v.value *= stack[-1]
	stack.pop()
	stack[-1] = v.value

def M_MULTIPLY():
	s = stack[-2] * stack[-1]
	stack[-1] = ctypes.c_short(s >> 16).value
	stack[-2] = ctypes.c_short(s).value

def UM_MULTIPLY():
	s = ctypes.c_ushort(stack[-2]).value * ctypes.c_ushort(stack[-1]).value
	stack[-1] = ctypes.c_short(s >> 16).value
	stack[-2] = ctypes.c_short(s).value

def TUCK(): # ( b a -- a b a )
	SWAP()
	OVER()

def UM_MOD(): # ( lsw msw divisor -- rem quot )
	lsw = stack[-3]
	msw = stack[-2]
	n = (ctypes.c_ushort(msw).value << 16) | ctypes.c_ushort(lsw).value
	d = ctypes.c_ushort(stack[-1]).value
	stack[-3] = ctypes.c_ushort(n % stack[-1]).value
	stack[-2] = ctypes.c_short(n // d).value
	stack.pop()

def M_PLUS(): # ( d1 u -- d2 )
	lsw = stack[-3]
	msw = stack[-2]
	n = (msw << 16) | ctypes.c_ushort(lsw).value
	n += stack[-1]
	stack[-3] = ctypes.c_short(n).value
	stack[-2] = ctypes.c_short(n >> 16).value
	stack.pop()

# from FIG UK
def D_NEGATE():
	INVERT()
	TO_R()
	INVERT()
	R_TO()
	stack.append(1)
	M_PLUS()

# from Gforth
def FM_MOD(): # ( d n -- rem quot )
	# dup >r
	DUP()
	TO_R()
	# dup 0< if negate >r dnegate r> then
	DUP()
	ZERO_LT()
	if stack.pop():
		NEGATE()
		TO_R()
		D_NEGATE()
		R_TO()
	# over 0< if tuck + swap then
	OVER()
	ZERO_LT()
	if stack.pop():
		TUCK()
		PLUS()
		SWAP()
	# um/mod
	UM_MOD()
	# r> 0< if swap negate swap then
	R_TO()
	ZERO_LT()
	if stack.pop():
		SWAP()
		NEGATE()
		SWAP()

# from FIG UK : ?dnegate 0< if dnegate then ;
def Q_D_NEGATE():
	ZERO_LT()
	if stack.pop():
		D_NEGATE()

def POSTPONE():
	name = read_word().lower()
	if words[name].immediate:
		# Compiles the word instead of executing it immediately.
		append(words[name].xt)
	else:
		# Instead of compiling the word, compile code that compiles the word.
		append(words["litc"].xt)
		append(words[name].xt)
		append(words["compile,"].xt)

def HERE():
	stack.append(here)

def COMMA():
	global ip
	v = stack.pop()
	append(v & 0xff)
	append(v >> 8)

def C_COMMA():
	append(stack.pop() & 0xff)

def WHILE():
	append(words["0branch"].xt)
	orig = here
	stack.insert(-1, orig)
	append(None)
	append(None)

def REPEAT():
	append(words["branch"].xt)
	COMMA()
	orig = stack.pop()
	heap[orig] = here & 0xff
	heap[orig + 1] = here >> 8

def UNTIL():
	append(words["0branch"].xt)
	COMMA()

def AGAIN():
	append(words["branch"].xt)
	COMMA()

def CHAR():
	w = read_word()
	stack.append(ord(w[0]))

def COMPILE_CHAR():
	w = read_word()
	append(LITC)
	append(ord(w[0]))

def TICK():
	w = read_word().lower()
	xt = words[w].xt
	stack.append(xt)

def COMPILE_TICK():
	TICK()
	LITERAL()

def IMMEDIATE():
	words[latest].immediate = True

def FIND(): # ( c-addr -- c-addr 0 | xt 1 | xt -1 )
	wordname = ""
	addr = stack[-1]
	for i in range(heap[addr]):
		wordname += chr(heap[addr + i + 1]).lower()
	if wordname in words:
		word = words[wordname]
		stack[-1] = word.xt
		stack.append(1 if word.immediate else -1)
	else:
		stack.append(0)

def EXECUTE():
	stack.pop()()

def LIT():
	global ip
	stack.append(heap[ip] + (heap[ip + 1] << 8))
	ip += 2

def LITC():
	global ip
	stack.append(heap[ip])
	ip += 1

def RECURSE():
	append(compiling_word.xt)

def DOES_TO():
	def dodoes(code, data):
		stack.append(data)
		docol(code)
	w = compiling_word if compiling_word else words[latest]
	words[latest].xt = lambda code=ip, data=w.body : dodoes(code, data)
	EXIT()

def TO_BODY(): # ( xt -- a-addr )
	for word in words.values():
		assert word
		if word.xt == stack[-1]:
			stack[-1] = word.body
			return
	assert False

def EVALUATE(): # ( c-addr u -- )
	global tib_addr
	global tib_count

	# Stash tib_addr, tib_count, >in
	orig_tib = tib_addr
	orig_tib_count = tib_count
	orig_to_in = heap[to_in_addr]

	# Set temporary tib_addr, tib_count, >in
	heap[to_in_addr] = 0
	tib_count = stack.pop()
	tib_addr = stack.pop()

	# Evaluate until tib is consumed
	while True:
		word = parse(' ')
		if not word:
			break
		if heap[state_addr]:
			compile(word)
		else:
			evaluate(word)

	# Restore tib_addr, tib_count, >in
	heap[to_in_addr] = orig_to_in
	tib_count = orig_tib_count
	tib_addr = orig_tib

def SOURCE(): # ( -- c-addr u )
	stack.append(tib_addr)
	stack.append(tib_count)

def WORD():
	w = parse(stack.pop())
	l = len(w)
	heap[word_addr] = l
	for i in range(l):
		heap[word_addr + i + 1] = w[i]
	stack.append(word_addr)

def format_append(ch):
	global format_addr
	heap[format_addr] = ch
	format_addr += 1

def LT_HASH():
	global format_addr
	format_addr = here

def HOLD(): # ( char -- )
	format_append(stack.pop())

def SIGN(): # ( i -- )
	if stack.pop() < 0:
		format_append('-')

def HASH(): # ( ud1 -- ud2 )
	d = ctypes.c_uint(stack[-1] << 16)
	d.value += ctypes.c_ushort(stack[-2]).value
	format_append(digits[d.value % heap[base_addr]].upper())
	d.value //= heap[base_addr]
	stack[-2] = d.value & 0xffff
	stack[-1] = d.value >> 16

def HASH_S(): # ( ud1 -- ud2 )
	HASH()
	while stack[-1] or stack[-2]:
		HASH()

def RT_HASH(): # ( xd -- c-addr u )
	global format_addr
	TWODROP()
	stack.append(pictured_numeric_addr)
	stack.append(format_addr - here)
	dst = pictured_numeric_addr
	format_addr -= 1
	while format_addr >= here:
		heap[dst] = heap[format_addr]
		dst += 1
		format_addr -= 1

def TO_NUMBER(): # ( ud1 c-addr1 u1 -- ud2 c-addr2 u2 )
	while stack[-1]:
		c = chr(heap[stack[-2]]).lower()
		if c not in digits:
			break
		i = digits.index(c)
		if i == -1 or i >= heap[base_addr]:
			break

		# Accumulate i to ud.
		ud = ctypes.c_uint(stack[-3])
		ud.value <<= 16
		ud.value += ctypes.c_ushort(stack[-4]).value
		ud.value *= heap[base_addr]
		ud.value += i
		stack[-4] = ctypes.c_short(ud.value & 0xffff).value
		stack[-3] = ctypes.c_short(ud.value >> 16).value

		ONEMINUS()
		SWAP()
		ONEPLUS()
		SWAP()

def FILL(): # ( c-addr u char -- )
	while stack[-2]:
		heap[stack[-3]] = stack[-1]
		stack[-2] -= 1
		stack[-3] += 1
	TWODROP()
	DROP()

def MOVE(): # ( src dst u -- )
	tmp = heap[stack[-3] : stack[-3] + stack[-1]]
	for i in range(len(tmp)):
		heap[stack[-2] + i] = tmp[i]
	TWODROP()
	DROP()

def DOT_QUOTE():
	S_QUOTE()
	append(words["type"].xt)

def SPACE():
	print(" ", end='')

def SPACES():
	for i in range(stack.pop()):
		SPACE()

def EMIT():
	print(chr(stack.pop()), end='')

def DABS():
	d = ctypes.c_int(stack[-1])
	d.value <<= 16
	d.value |= ctypes.c_ushort(stack[-2]).value
	d.value = abs(d.value)
	stack[-1] = d.value >> 16
	stack[-2] = d.value & 0xffff

def ACCEPT(): # ( c-addr n1 -- n2 )
	s = input()
	l = min(len(s), stack[-1])
	for i in range(l):
		heap[stack[-2] + i] = s[i]
	stack.pop()
	stack[-1] = l

def DOT_LPAREN():
	print(parse(')'), end='')

def COLON_NONAME():
	global compiling_word
	global latest
	latest = None
	ip = here
	compiling_word = Word(latest, lambda ip=ip : docol(ip), False)
	stack.append(compiling_word.xt)
	compiling_word.ip = ip
	set_state(True)

def U_GT():
	lhs = ctypes.c_ushort(stack[-2])
	rhs = ctypes.c_ushort(stack[-1])
	stack[-2] = -1 if lhs.value > rhs.value else 0
	stack.pop()

def UNUSED():
	stack.append(ctypes.c_short(len(heap) - here).value)

def MARKER():
	old_words = words.copy()
	old_here = here
	CREATE()
	def restore():
		global here
		global words
		here = old_here
		words = old_words
	words[latest].xt = restore

def COMPILE_COMMA():
	append(stack.pop())

def TO():
	TICK()
	TO_BODY()
	if heap[state_addr]:
		stack.append(LIT)
		COMPILE_COMMA()
		COMMA()
		stack.append(words["!"].xt)
		COMPILE_COMMA()
	else:
		STORE()

def _OF():
	global ip
	OVER()
	EQUALS()
	if stack.pop():
		DROP()
		ip += 2
	else:
		BRANCH()

def LITERAL():
	append(lambda xt=stack.pop() : stack.append(xt))

def PARSE():
	delim = stack.pop()
	stack.append(tib_addr + heap[to_in_addr])
	stack.append(0)
	while True:
		if heap[to_in_addr] == tib_count:
			return
		if heap[tib_addr + heap[to_in_addr]] == delim:
			heap[to_in_addr] += 1
			return
		heap[to_in_addr] += 1
		ONEPLUS()

def WORDS():
	print("Host:")
	l = []
	for k in words.keys():
		l.append(str(k))
	l.sort()
	print(" ".join(l))

	print("\nTarget:", )
	l = []
	for k in xc.code_words.keys():
		l.append(str(k))
	l.sort()
	print(" ".join(l))

def COMPILE():
	name = parse(' ')
	outfile = parse(' ')
	print("compile", name, "to", outfile, "...")
	xc.compile(xt_words, heap, words[name], outfile)
	print("ok")

def COLON_CODE():
	word_name = parse(' ')
	code = ""
	prev_to_in = heap[to_in_addr]
	while True:
		w = parse(' ')
		if w:
			if w.lower() == ";code":
				xc.code_words[word_name] = code
				return
			code += "".join(heap[tib_addr + prev_to_in : tib_addr + heap[to_in_addr]])
			prev_to_in = heap[to_in_addr]
		else:
			code += "\n"
			prev_to_in = 0
			REFILL()
			assert stack.pop()

add_word("refill", REFILL)
add_word("variable", VARIABLE)
add_word("!", STORE)
add_word("+!", PLUSSTORE)
add_word(":", COLON)
add_word(";", SEMICOLON, True)
add_word("depth", DEPTH)
add_word("dup", DUP)
add_word("2dup", TWODUP)
add_word("over", OVER)
add_word("rot", ROT)
add_word("swap", SWAP)
add_word("drop", DROP)
add_word("2drop", TWODROP)
add_word("0<", ZERO_LT)
add_word("0branch", ZBRANCH)
add_word("branch", BRANCH)
add_word("negate", NEGATE)
add_word("else", ELSE, True)
add_word("then", THEN, True)
add_word("cr", CR)
add_word("i", I)
add_word("j", J)
add_word("=", EQUALS)
add_word("0=", ZEQUAL)
add_word('s"', S_QUOTE, True)
add_word('s\\"', S_BACKSLASH_QUOTE, True)
add_word('c"', C_QUOTE, True)
add_word("do", DO, True)
add_word("(do)", _DO)
add_word("loop", LOOP, True)
add_word("(loop)", _LOOP)
add_word("+loop", PLUSLOOP, True)
add_word("(+loop)", _PLUSLOOP)
add_word("exit", EXIT)
add_word("type", TYPE)
add_word("source", SOURCE)
add_word("@", FETCH)
add_word("1+", ONEPLUS)
add_word("1-", ONEMINUS)
add_word("+", PLUS)
add_word("-", MINUS)
add_word("abs", ABS)
add_word("quit", QUIT)
add_word("create", CREATE)
add_word("allot", ALLOT)
add_word("sliteral", SLITERAL)
add_word("leave", LEAVE, True)
add_word("unloop", UNLOOP, True)
add_word(">r", TO_R)
add_word("r>", R_TO)
add_word("r@", R_FETCH)
add_word(">in", TO_IN)
add_word("(", LPAREN, True)
add_word("and", AND)
add_word("or", OR)
add_word("xor", XOR)
add_word("lshift", LSHIFT)
add_word("rshift", RSHIFT)
add_word("2*", TWOMUL)
add_word("2/", TWODIV)
add_word("invert", INVERT)
add_word("constant", CONSTANT)
add_word("<", LESS_THAN)
add_word(">", GREATER_THAN)
add_word("u<", U_LESS)
add_word("*", MULTIPLY)
add_word("m*", M_MULTIPLY)
add_word("um*", UM_MULTIPLY)
add_word("fm/mod", FM_MOD)
add_word("um/mod", UM_MOD)
add_word("tuck", TUCK)
add_word("literal", LITERAL, True)
add_word("postpone", POSTPONE, True)
add_word("here", HERE)
add_word(",", COMMA)
add_word("c,", C_COMMA)
add_word("char+", lambda : ONEPLUS())	# Using lambda to separate xt's for the cross compiler.
add_word("c@", C_FETCH)
add_word("c!", C_STORE)
add_word("while", WHILE, True)
add_word("repeat", REPEAT, True)
add_word("until", UNTIL, True)
add_word("again", AGAIN, True)
add_word("char", CHAR)
add_word("[char]", COMPILE_CHAR, True)
add_word("'", TICK)
add_word("execute", EXECUTE)
add_word("[']", COMPILE_TICK, True)
add_word("immediate", IMMEDIATE)
add_word("find", FIND)
add_word("lit", LIT)
add_word("litc", LITC)
add_word("state", STATE)
add_word("recurse", RECURSE, True)
add_word("within", WITHIN)
add_word("does>", DOES_TO)
add_word(">body", TO_BODY)
add_word("evaluate", EVALUATE)
add_word("word", WORD)
add_word("<#", LT_HASH)
add_word("hold", HOLD)
add_word("sign", SIGN)
add_word("#", HASH)
add_word("#s", HASH_S)
add_word("#>", RT_HASH)
add_word("base", BASE)
add_word(">number", TO_NUMBER)
add_word("fill", FILL)
add_word("move", MOVE)
add_word('."', DOT_QUOTE, True)
add_word("spaces", SPACES)
add_word("space", SPACE)
add_word("emit", EMIT)
add_word("dabs", DABS)
add_word("accept", ACCEPT)
add_word(".(", DOT_LPAREN, True)
add_word(":noname", COLON_NONAME)
add_word("u>", U_GT)
add_word("roll", ROLL)
add_word("pick", PICK)
add_word("2>r", TWO_TO_R)
add_word("2r>", TWO_R_TO)
add_word("2r@", TWO_R_FETCH)
add_word("unused", UNUSED)
add_word("marker", MARKER)
add_word("?do", QUESTION_DO, True)
add_word("(?do)", _QUESTION_DO)
add_word("to", TO, True)
add_word("(of)", _OF)
add_word("parse", PARSE)
add_word("source-id", SOURCE_ID)
add_word("bye", lambda:sys.exit(0))
add_word("words", WORDS)
add_word(":code", COLON_CODE)
add_word("compile,", COMPILE_COMMA)
add_word("compile", COMPILE)

def evaluate_file(filename):
	global INPUT_FILE
	INPUT_FILE = open(filename, mode='r')

	while True:
		REFILL()
		if stack.pop() == 0:
			return
		interpret_tib()

__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
evaluate_file(os.path.join(__location__, "src/words.fs"))

if len(sys.argv) > 1:
	args = sys.argv[1:]
	for infile in args:
		evaluate_file(infile)
else:
	print("Hack n' Trade Forth Compiler v0.0.1 :: Copyright (C) 2019 Johan Kotlinski")
	try:
		QUIT()
	except EOFError:
		pass
