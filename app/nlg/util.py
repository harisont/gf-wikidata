import pgf
from daison import *
from wordnet import *
from wordnet.semantics import *
from html import escape
import hashlib
import re
import json
import urllib.request

class ConcrHelper:
	def __init__(self,cnc,db,lang,edit):
		self.cnc  = cnc
		self.db   = db
		self.edit = edit
		self.links = {}
		self.name  = cnc.name
		self.lang  = lang
		self.exprs = []

	def addLink(self,lexeme,qid):
		if isinstance(lexeme,Lexeme):
			for lang,status in lexeme.status:
				if lang == self.cnc.name:
					break
			else:
				status = Status.Checked
			expr = pgf.ExprFun(lexeme.lex_fun)
			info = (qid,expr,status)
			self.links[expr] = info
			return info
		else:
			info = (qid,lexeme,Status.Checked)
			self.links[lexeme] = info

	def removeLink(self,lexeme):
		del self.links[lexeme]

	def linearize(self,e,title=False):
		if self.edit:
			self.exprs.append(e)
		text = ""
		bind = True
		info = None
		def flatten(xs):
			nonlocal text, bind, info
			for x in xs:
				if isinstance(x,str):
					if title:
						x = x.title();
					if bind:
						bind = False
					else:
						text += " "
					if info:
						if self.edit:
							text += '<span class="'+info[2].name.lower()+'" lang="'+self.lang+'" onclick="edit_lex(this,event,\''+escape(info[1].name)+'\',\''+self.lang+'\')">'
						else:
							text += '<a href="index.wsgi?id='+info[0]+'&lang='+self.lang+'">'
						info = None
					text += escape(x)
				elif isinstance(x,pgf.Bracket):
					if x.fun == "FullName" and len(x.children) == 2 and not self.edit:
						expr = w.FullName(pgf.ExprFun(x.children[0].fun),
						                  pgf.ExprFun(x.children[1].fun))
						info = self.links.get(expr)
						tmp  = info
						if info:
							text += ' <a href="index.wsgi?id='+info[0]+'&lang='+self.lang+'">'
							info = None
						bind = True
						flatten(x.children)
						if tmp:
							text += '</a>'
					elif x.fun == "GivenName" and len(x.children) == 1 and not self.edit:
						expr = w.GivenName(pgf.ExprFun(x.children[0].fun))
						info = self.links.get(expr)
						tmp  = info
						if info:
							text += ' <a href="index.wsgi?id='+info[0]+'&lang='+self.lang+'">'
							info = None
						bind = True
						flatten(x.children)
						if tmp:
							text += '</a>'
					elif x.fun == "MaleSurname" and len(x.children) == 1 and not self.edit:
						expr = w.MaleSurname(pgf.ExprFun(x.children[0].fun))
						info = self.links.get(expr)
						tmp  = info
						if info:
							text += ' <a href="index.wsgi?id='+info[0]+'&lang='+self.lang+'">'
							info = None
						bind = True
						flatten(x.children)
						if tmp:
							text += '</a>'
					elif x.fun == "FemaleSurname" and len(x.children) == 1 and not self.edit:
						expr = w.MaleSurname(pgf.ExprFun(x.children[0].fun))
						info = self.links.get(expr)
						tmp  = info
						if info:
							text += ' <a href="index.wsgi?id='+info[0]+'&lang='+self.lang+'">'
							info = None
						bind = True
						flatten(x.children)
						if tmp:
							text += '</a>'
					else:
						expr = pgf.ExprFun(x.fun)
						info = self.links.get(expr)
						if self.edit and info == None:
							self.links[expr] = False
							with self.db.run("r") as t:
								for lexeme_id in t.cursor(lexemes_fun, x.fun):
									for lexeme in t.cursor(lexemes, lexeme_id):
										info = self.addLink(lexeme, None)
						tmp  = info

						flatten(x.children)
						if tmp:
							if self.edit:
								text += '</span>'
							else:
								text += '</a>'
				elif isinstance(x,pgf.BIND):
					bind = True
		flatten(self.cnc.bracketedLinearize(e))
		if len(text) > 0:
			text = text[0].upper()+text[1:]
		return text

	lex_hacks = {
		"Q6452640": "southeast_1_N",
		"Q2381698": "southwest_1_N",
		"Q6497686": "northeast_1_N",
		"Q5491373": "northwest_3_N",
		"Q865":     "taiwan_2_PN",
		"Q869":     "thailand_PN",
		"Q801":     "israel_1_PN"
	}

	def get_lex_fun(self, qid, link=True):
		with self.db.run("r") as t:
			fun = self.lex_hacks.get(qid)
			if fun:
				for lexeme_id in t.cursor(lexemes_fun, fun):
					for lexeme in t.cursor(lexemes, lexeme_id):
						if link:
							self.addLink(lexeme, qid)
						return pgf.ExprFun(lexeme.lex_fun)
			else:
				for lexeme_id in t.cursor(lexemes_qid, qid):
					for lexeme in t.cursor(lexemes, lexeme_id):
						if link:
							self.addLink(lexeme, qid)
						return pgf.ExprFun(lexeme.lex_fun)
		return None

	def get_lexemes(self,prop,entity,qual=True,link=True):
		items = []
		if qual:
			for value in entity["claims"].get(prop,[]):
				try:
					qid = value["mainsnak"]["datavalue"]["value"]["id"]
				except KeyError:
					continue
				fun = self.get_lex_fun(qid,link)
				if fun:
					items.append((fun,value.get("qualifiers",{})))
		else:
			for value in entity["claims"].get(prop,[]):
				try:
					qid = value["mainsnak"]["datavalue"]["value"]["id"]
				except KeyError:
					continue
				fun = self.get_lex_fun(qid,link)
				if fun:
					items.append(fun)
		return items

	def get_lexeme_qualifiers(self,prop,quals,link=True):
		items = []
		for value in quals.get(prop,[]):
			try:
				qid = value["datavalue"]["value"]["id"]
			except KeyError:
				continue
			fun = self.get_lex_fun(qid,link)
			if fun:
				items.append(fun)
		return items

	def get_demonyms(self,prop,entity,link=True):
		adjs = set()
		pns  = set()
		all_adjs = True
		with self.db.run("r") as t:
			for value in entity["claims"].get(prop,[]):
				try:
					qid = value["mainsnak"]["datavalue"]["value"]["id"]
				except KeyError:
					continue

				for lexeme_id in t.cursor(lexemes_qid, qid):
					for lexeme in t.cursor(lexemes, lexeme_id):
						if link:
							self.addLink(lexeme, qid)
						pns.add(pgf.ExprFun(lexeme.lex_fun))
						for sym,target_id in lexeme.lex_pointers:
							if sym == Derived():
								for adj in t.cursor(lexemes, target_id):
									if link:
										self.addLink(adj, qid)
									adjs.add(pgf.ExprFun(adj.lex_fun))
							else:
								all_adjs = False

		return (all_adjs, adjs if all_adjs else pns)

	def get_person_name(self, entity):
		given_names  = self.get_lexemes("P735",entity,qual=False,link=False)
		family_names = self.get_lexemes("P734",entity,qual=False,link=False)
		if given_names:
			if family_names:
				expr = w.FullName(given_names[0],family_names[0])
				self.addLink(expr,entity["id"])
				return expr
			else:
				expr = w.GivenName(given_names[0])
				self.addLink(expr,entity["id"])
				return expr
		else:
			if family_names:
				if "Q6581072" in get_items("P21",entity):
					expr = w.FemaleSurname(family_names[0])
					self.addLink(expr,entity["id"])
					return expr
				else:
					expr = w.MaleSurname(family_names[0])
					self.addLink(expr,entity["id"])
					return expr

		return None

def get_items(prop,entity,qual=True):
	items = []
	if qual:
		for value in entity["claims"].get(prop,[]):
			try:
				items.append((value["mainsnak"]["datavalue"]["value"]["id"],value.get("qualifiers",{})))
			except KeyError:
				continue
	else:
		for value in entity["claims"].get(prop,[]):
			try:
				items.append(value["mainsnak"]["datavalue"]["value"]["id"])
			except KeyError:
				continue
	return items

def get_entities(prop,entity,qual=True):
	if isinstance(prop,list):
		props = prop
	else:
		props = [prop]

	items = set()
	for prop in props:
		for value in entity["claims"].get(prop,[]):
			try:
				items.add(value["mainsnak"]["datavalue"]["value"]["id"])
			except KeyError:
				continue

	if not items:
		return []

	u2 = urllib.request.urlopen("https://www.wikidata.org/w/api.php?action=wbgetentities&ids="+"|".join(items)+"&languages=en&format=json")
	result = json.loads(u2.read())["entities"]

	entities = []
	if qual:
		for item in items:
			try:
				entities.append((result[item],value.get("qualifiers",{})))
			except KeyError:
				continue
	else:
		for item in items:
			try:
				entities.append(result[item])
			except KeyError:
				continue
	return entities

def get_quantities(prop,entity):
	quantities = []
	for value in entity["claims"].get(prop,[]):
		try:
			amount = float(value["mainsnak"]["datavalue"]["value"]["amount"])
		except:
			continue
		quantities.append((amount,value.get("qualifiers",{})))
	return quantities

def get_medias(prop,entity):
	medias = []
	for value in entity["claims"].get(prop,[]):
		try:
			img = value["mainsnak"]["datavalue"]["value"]
		except KeyError:
			continue
		img = img.replace(' ','_')
		h = hashlib.md5(img.encode("utf-8")).hexdigest()
		img = "https://upload.wikimedia.org/wikipedia/commons/"+h[0]+"/"+h[0:2]+"/"+img
		medias.append((img,value.get("qualifiers",{})))
	return medias

iso8601_regex = re.compile(r"^(?P<era>\+|-)?(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})(T| )(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})(?P<offset>(Z|(?P<offset_op>\+|-)?(?P<offset_hour>\d{2}):?(?P<offset_minute>\d{2})))?$")

def get_date(prop,entity):
	for value in entity["claims"].get(prop,[]):
		try:
			match = iso8601_regex.match(value["mainsnak"]["datavalue"]["value"]["time"])
			if match:
				break
		except KeyError:
			continue
	else:
		return None

	year = int(match.group("year"))
	if year == 0:
		return None

	match match.group("era"):
		case "-":
			year *= -1
		case _:
			year = year
	year = w.intYear(pgf.ExprLit(year))
	match int(match.group("month")):
		case 0:
			month = None
		case 1:
			month = w.january_Month
		case 2:
			month = w.february_Month
		case 3:
			month = w.march_Month
		case 4:
			month = w.april_Month
		case 5:
			month = w.may_Month
		case 6:
			month = w.june_Month
		case 7:
			month = w.july_Month
		case 8:
			month = w.august_Month
		case 9:
			month = w.september_Month
		case 10:
			month = w.october_Month
		case 11:
			month = w.november_Month
		case 12:
			month = w.december_Month

	match int(match.group("day")):
		case 0:
			day = None
		case d:
			day = w.intMonthday(pgf.ExprLit(d))

	if month:
		if day:
			return w.dayMonthYearAdv(day, month, year)
		else:
			return w.monthYearAdv(month, year)
	else:
		return w.yearAdv(year)

def get_item_qualifier(prop,quals):
	for value in quals.get(prop,[]):
		try:
			return value["datavalue"]["value"]["id"]
		except KeyError:
			continue
	return None

def get_time_qualifier(prop,quals):
	for value in quals.get(prop,[]):
		try:
			return value["datavalue"]["value"]["time"]
		except KeyError:
			continue
	return None

def get_quantity_qualifier(prop,quals):
	for value in quals.get(prop,[]):
		try:
			return float(value["datavalue"]["value"]["amount"])
		except KeyError:
			continue
	return None

def get_entity(qid):
	if isinstance(qid,str):
		u2 = urllib.request.urlopen('https://www.wikidata.org/wiki/Special:EntityData/'+qid+'.json')
		result = json.loads(u2.read())
		return result["entities"][qid]
	elif not qid:
		return []
	else:
		items = set(qid)
		items.discard(None)
		u2 = urllib.request.urlopen("https://www.wikidata.org/w/api.php?action=wbgetentities&ids="+"|".join(items)+"&languages=en&format=json")
		result = json.loads(u2.read())["entities"]
		return result
