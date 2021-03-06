import urllib
import random
import hmac
from hashlib import sha1
import datetime

import web
import helpers, forms
from settings import db, render
import config

def get_hexdigest(key, s):
    return hmac.new(key, s, sha1).hexdigest()

def encrypt_password(password):
    key = str(random.random())[2:]
    return '@'.join([key, get_hexdigest(key, password)])

def check_password(user, password):
    key, enc_password = user.password.split('@')
    return enc_password == get_hexdigest(key, password)

def _login(useremail, password):
    user = helpers.get_user_by_email(useremail)
    if user and check_password(user, password):
        helpers.set_login_cookie(useremail)
        return user
    else:
        return None

class login:
    def GET(self):
        referer = web.ctx.env.get('HTTP_REFERER', '/')
        i = web.input(redirect=referer)
        form = forms.loginform()
        form['redirect'].value = i.redirect
        msg, msg_type = helpers.get_delete_msg()
        return render.login(form, msg)
    
    def POST(self):
        i = web.input(redirect='/')
        user = _login(i.useremail, i.password)
        if not user:
            f = forms.loginform()
            f.fill(i)
            f.note = 'Invalid email or password.'
            return render.login(f)
        raise web.seeother(i.redirect)
        
class logout:
    def POST(self):
        helpers.del_login_cookie()
        referer = web.ctx.env.get('HTTP_REFERER', '/')
        raise web.seeother(referer)

def get_secret_token(email, validity=7):
    valid_till = (datetime.date.today() + datetime.timedelta(validity)).isoformat()
    return '@'.join([valid_till, helpers.encrypt(email + valid_till)])

def check_secret_token(email, token):
    valid_till, enc_email_ts = token.split('@')
    tampered = helpers.encrypt(email + valid_till) != enc_email_ts
    def expired():
        today = datetime.date.today()
        valid_date = datetime.date(*[int(t) for t in valid_till.split('-')])
        return today > valid_date

    return not(tampered or expired())
                
def set_password_url(email, token):
    query = urllib.urlencode(dict(email=email, token=token))
    url = 'http://watchdog.net/set_password?%s' % (query)
    return url
        
class forgot_password:
    def GET(self, form=None):
        form = form or forms.forgot_password()
        msg, msg_type = helpers.get_delete_msg()
        return render.forgot_password(form, msg)
    
    def POST(self):
        i = web.input()
        form = forms.forgot_password()
        if form.validates(i):
            token = get_secret_token(i.email)
            reset_url = set_password_url(i.email, token)
            subject = 'Reset your watchdog.net password'
            msg = """\
You asked to reset your password on watchdog.net.
You can do so at:

%s

but you have to do it within the next 7 days.

Thanks,
watchdog.net
""" % (reset_url)
            web.sendmail(config.from_address, i.email, subject, msg )
            helpers.set_msg('Check your email to reset your password.')
            raise web.seeother('/forgot_password')
        else:
            return self.GET(form)

class set_password:
    def GET(self, form=None):
        i = web.input()
        if check_secret_token(i.email, i.token):
            form = form or forms.passwordform()
            return render.set_password(form, i.email)
        else:
            helpers.set_msg('Invalid token', msg_type='error')
            raise web.seeother('/forgot_password')
    
    def POST(self):
        i = web.input()
        form = forms.passwordform()
        if form.validates(i):
            password = encrypt_password(i.password)        
            db.update('users', password=password, verified=True, where='email=$i.email', vars=locals())
            helpers.set_msg('Login with your new password.')
            raise web.seeother('/login')
        else:
            return self.GET(form)
        
def send_mail_to_set_password(email):
    token = get_secret_token(email, validity=365)
    url = set_password_url(email, token)
    subject = 'Set your watchdog.net password'
    msg = """\
Thanks for using watchdog.net. We've created an account 
for you with this email address -- but we don't have 
a password for it. So that you can log in later, please 
set your password at:

%s

If you've already set a password, then don't worry about 
it and sorry for the interruption. If you think you received 
this email in error, please hit reply and let us know.

Thanks,
watchdog.net
""" % (url)
    web.sendmail(config.from_address, email, subject, msg)
        
def assert_verified(email):
    if helpers.get_loggedin_email():
        pass
    elif helpers.no_verified_activity(email):
        helpers.set_login_cookie(email)
        send_mail_to_set_password(email)
    else:
        query = urllib.urlencode(dict(redirect=web.ctx.fullpath))
        raise web.seeother("/login?%s" % query)
            
