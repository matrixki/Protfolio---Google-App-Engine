import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'settings'
from google.appengine.dist import use_library
use_library('django', '1.2')

import logging
import wsgiref.handlers
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from util.sessions import Session
from google.appengine.ext import db

# A Model for a User
class User(db.Model):
	account = db.StringProperty()
	password = db.StringProperty()
	name = db.StringProperty()

# A Model for a ChatMessage
class ChatMessage(db.Model):
  user = db.ReferenceProperty()
  text = db.StringProperty()
  created = db.DateTimeProperty(auto_now=True)
 
# A Model for a Drink
class Drink(db.Model):
	title = db.StringProperty()
	color = db.StringProperty()
	publisher = db.StringProperty()
	price = db.StringProperty()
	caffine = db.StringProperty()

class DrinkAdded(db.Model):
	title = db.StringProperty()
	createdBy = db.StringProperty()
	created = db.DateTimeProperty(auto_now=True)
	
class DrinkRating(db.Model):
	drink = db.ReferenceProperty(Drink)
	ratedBy = db.ReferenceProperty(User)
	score = db.IntegerProperty()
	rated = db.DateTimeProperty(auto_now=True)
	
class AverageRating(db.Model):
	drink = db.ReferenceProperty(Drink)
	ave_score = db.FloatProperty()
	count = db.IntegerProperty()

# A helper to do the rendering and to add the necessary
# variables for the _base.htm template
def doRender(handler, tname = 'index.htm', values = { }):
	logging.info('doRender(' + tname + ')')
	temp = os.path.join(
		os.path.dirname(__file__),
		'templates/' + tname)
	logging.info(temp)
	if not os.path.isfile(temp):
		return False

	# Make a copy of the dictionary and add the path and session
	newval = dict(values)
	newval['path'] = handler.request.path
	handler.session = Session()
	if 'username' in handler.session:
		newval['username'] = handler.session['username']
	logging.info(newval)
	outstr = template.render(temp, newval)
	handler.response.out.write(outstr)
	return True

class DrinkHandler(webapp.RequestHandler):

	def get(self):
		logging.info('DrinkHandler.get()')
		self.session = Session()
		if 'username' not in self.session:
			doRender(self, 'noauth.htm')
			return
		sort = self.request.get('sort')
		order = self.request.get('order')
		logging.info('sort == ' + sort + ' order == ' + order)
		if(sort == None or sort == ''):
			sort = 'title'
		if(order == None or order == '' or order == 'asc'):
			order = 'asc'
			sortOrder = sort
		else:
			order = 'desc'
			sortOrder = '-' + sort
		
		que = db.Query(Drink)
		que = que.order(sortOrder)
		drinks = que.fetch(limit=20)
		logging.info(drinks)
		
		doRender(self, 'drinks.htm',{ 'drinks' : drinks, 'sort' : sort, 'order' : order })
class ChatHandler(webapp.RequestHandler):

  def get(self):
    que = db.Query(ChatMessage).order('-created');
    chat_list = que.fetch(limit=10)
    doRender(
          self,
          'chatscreen.htm',
          { 'chat_list': chat_list })

  def post(self):
    self.session = Session()
    if not 'userkey' in self.session:
      doRender(
          self,
          'chatscreen.htm',
          {'error' : 'Must be logged in'} )
      return

    msg = self.request.get('message')
    if msg == '':
      doRender(
          self,
          'chatscreen.htm',
          {'error' : 'Blank message ignored'} )
      return

    newchat = ChatMessage(user = self.session['userkey'], text=msg)
    newchat.put();
    self.get();
class RatingsHandler(webapp.RequestHandler):
	
	def get(self):
		logging.info('RatingsHandler.get()')
		self.session = Session()
		if 'user_key' not in self.session:
			logging.warn('User attempting to access ratings without logging in')
			return
		drink_id = self.request.get('drink_id')
		user_key = self.session.get('user_key')
		if(drink_id == ''):
			logging.warn('RatingsHandler called with no drink-id')
			return
		# get current user's rating of drink (if any)
		drink = Drink.get_by_id(int(drink_id))
		if drink is None:
			logging.warn("drink not found for id == " + drink_id)
			return
		else:
			logging.info(drink)
		query1 = db.Query(DrinkRating).filter('drink = ', drink.key()).filter('ratedBy = ', user_key)
		my_rating = query1.get()
		if my_rating is None:
			my_score = 0
		else:
			my_score = my_rating.score
		
		# get average rating
		query2 = db.Query(AverageRating).filter('drink = ',drink.key())
		ave_rating = query2.get()
		logging.info(ave_rating)
		if ave_rating is None:
			ave_score = 0.0
		else:
			ave_score = ave_rating.ave_score
		
		doRender(self,'ratings.html',{'drink_key':drink.key(), 'drink_id':drink.key().id(), 'ave_score':ave_score, 'my_score':my_score})
		
	def post(self):
		logging.info('RatingsHandler.post()')
		self.session = Session()
		if 'user_key' not in self.session:
			logging.warn('User attempting to post ratings without logging in')
			return
		user_key = self.session.get('user_key')
		
		drink_id = self.request.get('drink_id')
		score_str = self.request.get('score')
		if(drink_id == '' or score_str == ''):
			return
		logging.info('score == ' + score_str)
		logging.info('drink_id = ' + drink_id)
		logging.info('user_key = ' + str(user_key))
		num = int(score_str)
		drink = Drink.get_by_id(int(drink_id))
		logging.info(drink)
		query = db.Query(DrinkRating).filter('ratedBy = ',user_key).filter('drink = ',drink.key())
		ratings = query.fetch(limit=1)
		logging.info(len(ratings))
		
		if len(ratings) < 1:
			# put new entry in Datastore
			logging.info('saving rating')
			rating = DrinkRating(drink=drink.key(), ratedBy=user_key, score=num)
			rating.put()
			logging.info(rating.score)
			logging.info(rating.drink.title)
			logging.info(rating.ratedBy.name)
			logging.info(rating.key())
		else:
			# update existing entry
			rating = ratings[0]
			rating.score = num
			rating.put()
		# Next need to update the display
		logging.info(rating)
		self.calculateAverage(drink.key())
		self.get()
		
	def calculateAverage(self,bkey):
		ave_query = db.Query(AverageRating).filter('drink = ',bkey)
		ave_rating = ave_query.get()
		if ave_rating is None:
			ave_rating = AverageRating(drink=bkey, count=0, ave_score=0.0) 
		ratings_query = db.Query(DrinkRating).filter('drink = ',bkey)
		total = 0.0
		count = 0
		ratings = ratings_query.fetch(limit=1000)
		for item in ratings:
			total = total + float(item.score)
			count = count + 1
		ave_rating.ave_score = total / float(count)
		ave_rating.count = count
		ave_rating.put()
		logging.info('calculated average rating of ' + str(ave_rating.ave_score) + ' (n=' + str(ave_rating.count) + ')')
						
class AddDrinkHandler(webapp.RequestHandler):
	
	def get(self):
		logging.info('AddDrinkHandler.get()')
		self.session = Session()
		if 'username' not in self.session:
			return
		doRender(self, 'adddrink.htm')

	def post(self):
		logging.info('AddDrinkHandler.post()')
		self.session = Session()
		if 'username' not in self.session:
			doRender(self, 'noauth.htm')
			return
		ti = self.request.get('title')
		co = self.request.get('color')
		pb = self.request.get('publisher')
		pr = self.request.get('price')
		ca = self.request.get('caffine')
		
		if ti == '' or co == '' or pb == '' or pr == '' or ca == '':
			doRender(self,'adddrink.htm',{'msg':'Please fill in the darn fields'})
		
		drink = Drink(title=ti, color=co, publisher=pb, price=pr, caffine=ca)
		drink.put()
		
		self.session = Session()
		drinkAdded = DrinkAdded(title = ti, createdBy=self.session['username'])
		drinkAdded.put()
		
		doRender(self,'adddrink.htm',{'msg':'Your drink has been added. Add another?'})

class ApplyHandler(webapp.RequestHandler):

  def get(self):
    self.session = Session()
    doRender(self, 'applyscreen.htm')

  def post(self):
    self.session = Session()
    name = self.request.get('name')
    acct = self.request.get('account')
    pw = self.request.get('password')
    logging.info('Adding account='+acct)

    if pw == '' or acct == '' or name == '':
      doRender(
          self,
          'applyscreen.htm',
           {'error' : 'Please fill in all fields'} )
      return

    # Check if the user already exists
    que = db.Query(User).filter('account =',acct)
    results = que.fetch(limit=1)

    if len(results) > 0 :
      doRender(
          self,
          'applyscreen.htm',
          {'error' : 'Account Already Exists'} )
      return

    # Create the User object and log the user in
    newuser = User(name=name, account=acct, password=pw);
    pkey = newuser.put();
    self.session['username'] = acct
    self.session['userkey'] = pkey
    self.session = Session()
    doRender(self,'index.htm',{ })
		
class LoginHandler(webapp.RequestHandler):

	def get(self):
		doRender(self, 'loginscreen.htm')

	def post(self):
		self.session = Session()
		acct = self.request.get('account')
		pw = self.request.get('password')
		logging.info('Checking account='+acct+' pw='+pw)

		self.session.delete_item('username')

		if pw == '' or acct == '':
			doRender(self,'loginscreen.htm',{'error' : 'Please specify Account and Password'} )
			return

		que = db.Query(User)
		que = que.filter('account =',acct)
		que = que.filter('password = ',pw)

		results = que.fetch(limit=1)

		if len(results) > 0 :
			user = results[0]
			self.session['username'] = user.account
			self.session['user_key'] = user.key()
			doRender(self,'index.htm',{ } )
		else:
			doRender(self,'loginscreen.htm',{'error' : 'Incorrect password'} )

class MembersHandler(webapp.RequestHandler):

  def get(self):
    logging.info('MambersHandler.get()')
    self.session = Session()
    if 'username' not in self.session:
       doRender(self, 'noauth.htm')
       return
    que = db.Query(User)
    user_list = que.fetch(limit=100)
    doRender(
        self, 
        'memberscreen.htm', 
        {'user_list': user_list})
class MessagesHandler(webapp.RequestHandler):

  def get(self):
    que = db.Query(ChatMessage).order('-created');
    chat_list = que.fetch(limit=10)
    doRender(self, 'messagelist.htm', {'chat_list': chat_list})

class LogoutHandler(webapp.RequestHandler):

	def get(self):
		self.session = Session()
		self.session.delete_item('username')
		self.session.delete_item('user_key')
		doRender(self, 'index.htm')

class MainHandler(webapp.RequestHandler):

	def get(self):
		if doRender(self,self.request.path) :
			return
		doRender(self,'index.htm')

def main():
	application = webapp.WSGIApplication([
		 ('/drinks', DrinkHandler), 
		 ('/ratings', RatingsHandler),
		 ('/chat', ChatHandler),
		 ('/messages', MessagesHandler),
		 ('/members', MembersHandler),
		 ('/add-drink', AddDrinkHandler),
		 ('/apply',ApplyHandler),
		 ('/login', LoginHandler),
		 ('/logout', LogoutHandler),
		 ('/.*', MainHandler)],
		 debug=True)
	wsgiref.handlers.CGIHandler().run(application)

if __name__ == '__main__':
	main()
