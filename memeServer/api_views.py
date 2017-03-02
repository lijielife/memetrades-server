from flask import Flask, request, url_for, jsonify, redirect, Response, render_template
from flask_login import LoginManager, current_user, login_user, logout_user, login_required
from . import models, settings, app, utils, requires_roles, load_user
import time

#
# Private APIs
# 

@app.route('/api/me')
@login_required
def memes():
    return jsonify({
        "money": current_user.money,
        "stocks": current_user.get_holdings(),
        "api_key": current_user.api_key,
        "stock_value": current_user.stock_value,
        "referral_code": current_user.referral_code
    })

@app.route('/api/buy')
@login_required
def buy():
    meme = request.args.get("meme").strip()
    stock = models.Stock.objects.filter(name=meme).first()
    if not stock:
        stock = models.Stock(name=meme, creator=load_user(current_user.fb_id), price=0)
        stock.save()
    try:
        current_user.queue_buy(stock)
        return utils.success()
    except Exception as e:
        return utils.fail(reason=str(e))

@app.route('/api/sell')
@login_required
def sell():
    meme = request.args.get("meme")
    stock = models.Stock.objects.filter(name=meme).first()
    
    if stock:
        try:
            current_user.queue_sell(stock)
            return utils.success()
        except Exception as e:
            return utils.fail(reason=str(e))
    return utils.fail(reason="Stock does not exist")

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

#
# Admin endpoints
#

@app.route('/api/admin/stock/delete')
@login_required
@requires_roles('admin')
def admin_remove():
    meme = request.args.get("meme")
    if meme:
        stock = models.Stock.objects.filter(name=meme).first()
        if stock:
            if not stock.blacklisted:
                stock.blacklist()
                models.ban_meme(stock.id)
                return utils.success()
            return utils.fail(reason="stock already blacklisted...")
        return utils.fail(reason="the stock did not exist...")
    return utils.fail(reason="the stock did not exist...")

#
# Publically available APIS
#
trending_cache=""
trending_timestamp=-100000
@app.route('/api/trending')
def trends():    
    global trending_timestamp
    global trending_cache
    if time.time() < trending_timestamp + 90*settings.LAG_ALLOWED:
	print "cached"
	return trending_cache
    trending_timestamp = time.time() 
    results = models.get_trending()
    trending_cache = jsonify(results)
    
    return trending_cache

@app.route('/api/search')
def search():
    query=request.args.get("q")
    if query:
        stocks= models.Stock.objects.filter(
                name__icontains=query,
                blacklisted=False
            ).only('name','price','trend','id').limit(10)
        return Response(stocks.to_json(), mimetype="application/json")
    return jsonify([])

@app.route('/api/stock')
def stock():
    meme = request.args.get("meme")
    stock = models.Stock.objects.filter(
            name=meme,
            blacklisted=False
        ).only('name','price','trend','id').first()
    if stock:
        return Response(stock.to_json(), mimetype="application/json")
    else:
        return jsonify({})

@app.route('/api/leaders')
def leaders():
    return jsonify(models.get_leaders())

stocks_cache={}
stocks_timestamp={}
@app.route('/api/stocks')
def stocks():
    page = int(request.args.get('page')) if request.args.get('page') else 1

    # if the cache is fresh
    if (page in stocks_timestamp) and (stocks_timestamp[page]  > time.time() - settings.LAG_ALLOWED):    
        return stocks_cache[page]
    
    # if the cache is stale
    offset = (page - 1) * settings.STOCKS_PER_PAGE
    all_stocks = get_paged_stocks(page)
    stocks_cache[page] = Response(all_stocks.to_json(), mimetype="application/json")
    stocks_timestamp[page] = time.time()
    return stocks_cache[page]

history_cache = {}
history_timestamp = {}
@app.route('/api/history')
def history():
    meme = request.args.get("meme")

    if (meme in history_timestamp) and (history_timestamp[meme] > time.time() - settings.LAG_ALLOWED * 3):
        return history_cache[meme]

    stock = models.Stock.objects.filter(name=meme).first()
    if stock:
        history = models.StockHistoryEntry.objects.filter(stock=stock).order_by('-time').limit(400)
        history_cache[meme] = Response(history.to_json(), mimetype='application/json')
    else:
        history_cache[meme] = jsonify([])

    history_timestamp[meme] = time.time()
    return history_cache[meme]

recent_cache = ""
recent_timestamp = -10000
@app.route('/api/recent')
def recent():
    global recent_timestamp
    global recent_cache
    if time.time() < recent_timestamp + settings.LAG_ALLOWED:
	print "cached"
	return recent_cache
    
    # Get the 100 most recent transactions
    # return Response(models.get_recents().to_json(), mimetype='application/json')
    recent_cache = jsonify(models.get_recents())
    recent_timestamp = time.time()
    return recent_cache

#
# Some helpers
#

def get_paged_stocks(page):
    page = int(page)
    offset = (page - 1) * settings.STOCKS_PER_PAGE
    return models.Stock.objects(blacklisted=False).only('name','price','trend').skip(offset).limit(settings.STOCKS_PER_PAGE).order_by('-price')
