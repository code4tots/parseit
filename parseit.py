import re

class Token(object):
	def __init__(self,token,string,start,end):
		self.token = token                            # string containing this token
		self.string = string                          # entire string being processed
		self.start = start                            # position of string where this token begins
		self.end = end                                # position of string where this token ends
		                                              # so token == string[start:end]
		a = string.rfind('\n',0,start)+1
		b = string.find('\n',end)
		if b == 0: b = len(string)
		
		self.line = string[a:b]                        # line where this token is found
		self.line_number = string.count('\n',0,start)  # line number
		self.column_number = start - a + 1             # column number
	
	def __repr__(self):
		return '(%s,%s,%s)'%(self.token,self.start,self.end)
	
	def __str__(self):
		return self.token

class ParseException(Exception):
	def __init__(self,token,message):
		self.token = token                              # token in code where parse error occurred
		self.message = message                          # message describing the error
		super(ParseException,self).__init__(
			'%s on line %s, column %s: %r\n%s\n%s' %(
				message,token.line_number,token.column_number,token,
				token.line,
				' '*(token.column_number-1)+'*'))

class TokenStream(object):
	def __init__(self,token_generator):
		self.token_list = list(token_generator)
		self.position = 0

	def peek(self):
		return self.token_list[min(self.position,len(self.token_list)-1)]
	
	def save(self):
		return self.position
	
	def load(self,position):
		self.position = position
	
	def next(self):
		return self.__next__()
	
	def __next__(self):
		self.position += 1
		return self.token_list[self.position-1]

class Lexer(object):
	ignore_regex = re.compile(r'(?:(?:\s+)|(?:\#[^\n]*))*')
	err_regex = re.compile(r'\S+')
	def __init__(self,keywords,symbols):
		self.keywords = keywords                        # all keywords and symbols must be known before
		self.symbols = symbols                          # the lexer can be constructed
		self.token_types = {
			'int' : r'\d+(?!\.)',
			'float' : r'\d+\.\d*',
			'keyword' : '|'.join(keyword+r'(?!\w)' for keyword in keywords),
			'name' : ''.join(r'(?!'+keyword+r'(?!\w))' for keyword in keywords)+r'(?!r\"|r\'|\d)\w+',
			'str' : '|'.join('(?:'+s+')' for s in (
				r'\"(?:[^"]|(?:\\\"))*\"',
				r"\'(?:[^']|(?:\\\'))*\'",
				r'r\"[^"]*\"',
				r"r\'[^']*\'")),
			'symbol' : '|'.join('(?:'+re.escape(symbol)+')' for symbol in reversed(sorted(symbols)))}
		for token_type, regex_string in self.token_types.items():
			self.token_types[token_type] = re.compile(regex_string)
	
	def __call__(self,string):
		return TokenStream(self._lex(string))
	
	def _lex(self,string):
		ignore_regex = self.ignore_regex
		i = 0
		while True:
			i = ignore_regex.match(string,i).end()
			if i >= len(string): break
			
			for type_, regex in token_types.items():
				m = regex.match(string,i)
				if m:
					i = m.end()
					yield Token(type_,string,m.group(),m.start(),i)
					break
			else:
				m = self.err_regex.match(string,i)
				t = Token('err',string,m.group(),m.start(),m.end())
				raise ParseException(t,'unrecognized token')
		yield Token('eof',string,'',len(string),len(string))

class Ast(object):
	def __init__(self,**kwargs):
		for key, value in kwargs.items():
			setattr(self,key,value)

class Parser(object):
	def __call__(self,stream):
		if isinstance(stream,str):
			raise ParseException(
				'Parser.__call__ is for parsing TokenStream instances. '
				'If you wish to parse a string, use the parse_string method')
		save = stream.save()
		result = self._parse(stream)
		if result is None:
			stream.load(save)
		return result
	
	def parse_string(self,string):
		keywords = set()
		symbols = set()
		for parser in self.descendants():
			if isinstance(parser,Keyword):
				keywords.add(parser.keyword)
			elif isinstance(parser,Symbol):
				symbols.add(parser.symbol)
		lexer = Lexer(keywords,symbols)
		return self(lexer(string))
	
	def descendants(self,seen=None):
		if seen is None:
			seen = set()
		
		if self in seen:
			return seen
		
		seen.add(self)
		for parser in self.children:
			self.descendants(seen)
		
		return seen
		
	def __or__(self,other):
		return Or(self,other)
	
	def on_success(self,action):
		return OnSuccess(self,action)
	
	def on_failure(self,action):
		return OnFailure(self,action)
	
	def on_result(self,action):
		return Action(self,action)

class TokenSatisfying(Parser):
	def __init__(self,condition):
		self.children = ()
		self.condition = condition
	
	def _parse(self,stream):
		if self.condition(stream.peek()):
			return next(stream)
 
class TokenOfType(TokenSatisfying):
	def __init__(self,type_):
		super(TokenOfType,self).__init__(lambda t : t.type_ == type_)

class TokenMatching(TokenSatisfying):
	def __init__(self,token):
		super(TokenMatching,self).__init__(lambda t : t.token == token)

class Symbol(TokenMatching):
	def __init__(self,symbol):
		super(Symbol,self).__init__(symbol)
		self.symbol = symbol

class Keyword(TokenMatching):
	def __init__(self,keyword):
		super(Keyword,self).__init__(keyword)
		self.keyword = keyword
 
class Action(Parser):
	def __init__(self,parser,action):
		self.children = (parser,)
		self.parser = parser
		self.action = action
	
	def _parse(self,stream):
		return self.action(self.parser(stream))

OnSuccess = lambda parser, action : Action(parser,lambda result : action(result) if result is not None else None)
OnFailure = lambda parser, action : Action(parser,lambda result : action(result) if result is None else result)

class Proxy(Parser):
	def __init__(self,parser=None):
		self.parser = parser
	
	@property
	def children(self):
		return (self.parser,) if self.parser is not None else ()
	
	def _parse(self,stream):
		return self.parser(stream)

class Or(Parser):
	def __init__(self,*parsers):
		self.children = tuple(parsers)
	
	def _parse(self,stream):
		for parser in self.children:
			result = parser(stream)
			if result is not None:
				return result

class And(Parser):
	def __init__(self,*parsers):
		self.children = tuple(parsers)
	
	def _parse(self,stream):
		results = []
		for parser in self.children:
			result = parser(stream)
			if result is None:
				return None
			results.append(result)
		return results

class Repeat(Parser):
	def __init__(self,parser,at_least=0,at_most=None):
		self.children = (parser,)
		self.parser = parser
		self.at_least = at_least
		self.at_most = at_most
	
	def _parse(self,stream):
		parser = self.parser
		at_least = self.at_least
		at_most = self.at_most
		results = []
		while at_most is None or len(results) <= at_most:
			result = parser(stream)
			if result is None:
				return results if len(results) >= at_least else None
			results.append(result)

ZeroOrMore = lambda parser    : Repeat(parser)
OneOrMore  = lambda parser    : Repeat(parser,1)
AtMost     = lambda parser, n : Repeat(parser,0,n)


