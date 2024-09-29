from flask import Flask,session, render_template, request, redirect, url_for, flash , jsonify , make_response
from bson import ObjectId , json_util
from pymongo import MongoClient , ASCENDING , errors
from dotenv import load_dotenv
from functools import wraps
from apscheduler.schedulers.background import BackgroundScheduler
import random
from datetime import timedelta
from pymongo.errors import DuplicateKeyError
from flask_socketio import SocketIO, emit, join_room, leave_room
import threading
import os
import datetime
import pytz
import json
from bson.json_util import dumps




# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = 'hellothisismysecretkey'
# Load MongoDB URI from environment variables
mongo_uri = os.getenv('MONGODB_URI')
if not mongo_uri:
    raise ValueError("MONGODB_URI not found in environment variables.")

# Initialize MongoDB client
client = MongoClient(mongo_uri)
db_name = 'monopoly'  # Replace with your desired database name
db = client[db_name]

GO_AMOUNT = 200000  # Set the amount to be added for GO functionality
GO_COOLDOWN = timedelta(minutes=3)  # Set the cooldown period

socketio = SocketIO(app)






@app.before_request
def check_login():
    if 'user' not in session and request.endpoint not in ["create_deed",'get_active_auctions','login', 'play_game', 'static', 'home', 'add_user', "delete_all_users", "set_gold_rate", "update_gold_rate", "delete_all_bank_requests"]:
        return redirect(url_for('login'))
    # elif 'user' in session and 'role' in session:
    #     if session['role'] == 'banker' and request.endpoint not in ['bank_approval', 'logout']:
    #         return redirect(url_for('bank_approval'))
    #     elif session['role'] == 'player' and request.endpoint == 'bank_approval':
    #         return redirect(url_for('dashboard'))

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash('Please log in to access this page.', 'danger')
            return redirect(url_for('play_game'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/')
def home():
    try:
        users = db.Users.find()
        return render_template('index.html', users=users)
    except Exception as e:
        print("Error fetching users:", e)
        return "Failed to load users.", 500

@app.route('/add_user', methods=['GET', 'POST'])
def add_user():
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').lower().strip()  # Convert to lowercase and remove whitespace
            password = request.form.get('password')

            # Prepare the new user document
            new_user = {
                'name': name,
                'password': password,
                'balance': 0,
                'gold': 0,
                'role': 'player',
                'loan': 0
            }

            # Customize new user based on the name
            if name == 'bilal':
                new_user['goldrate'] = 1500
            elif name == 'abdulrehman':
                new_user['role'] = 'banker'
                new_user['requests_count'] = 0

            # Try to insert the new user, will raise DuplicateKeyError if name already exists
            result = db.Users.insert_one(new_user)

            if result.inserted_id:
                flash('User Added!', 'success')
            else:
                flash('Failed to add user. Please try again.', 'danger')

            return redirect(url_for('add_user'))

        # Handle duplicate key error if the user name already exists
        except DuplicateKeyError:
            flash('User already exists with the same name', "danger")
            return redirect(url_for('add_user'))

        # Handle any other general exceptions
        except Exception as e:
            print("Error adding user:", e)
            flash('An error occurred while adding the user.', 'danger')
            return redirect(url_for('add_user'))

    # Render the add user form if GET request
    return render_template('add_user.html')


@app.route('/play_game')
def play_game():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    try:
        users = db.Users.find()
        return render_template('login.html', users=users)
    except Exception as e:
        print("Error fetching users for login:", e)
        return "Failed to load users.", 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            password = request.form.get('password')
            
            user = db.Users.find_one({'name': name, 'password': password})
            if user:
                session['user'] = name
                session['role'] = user['role']
                flash('Logged in successfully.', 'success')
                if user['role'] == 'player':
                    return redirect(url_for('dashboard'))
                elif user['role'] == 'banker':
                    return redirect(url_for('bank_approval'))
            else:
                flash('Invalid username or password', 'danger')
                return redirect(url_for('login'))
        except Exception as e:
            print("Error during login:", e)
            flash("An error occurred during login.", 'danger')
            return redirect(url_for('login'))
    
    # For GET requests, just render the login template
    try:
        users = db.Users.find()
        return render_template('login.html', users=users)
    except Exception as e:
        print("Error fetching users for login:", e)
        return "Failed to load users.", 500

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    response = make_response(redirect(url_for('play_game')))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/dashboard')
@login_required
def dashboard():
    try:
        user = db.Users.find_one({'name': session['user']})
        deeds= db.Deeds.find({'owner':user['name']})
        if not user:
            session.clear()
            flash('User not found.','danger')
            return redirect(url_for('login'))

        response = make_response(render_template('dashboard.html', user=user , deeds=deeds))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        print("Error loading dashboard:", e)
        flash('Failed to load dashboard.', 'danger')
        return redirect(url_for('login'))


@app.route('/gold_shop', methods=['GET', 'POST'])
@login_required
def gold_shop():
    try:
        current_user = session['user']
        if not current_user:
            flash('No current user found.', 'danger')
            return redirect(url_for('home'))

        gold_seller_user = db.Users.find_one({'name': 'bilal'})
        if not gold_seller_user:
            flash('Gold seller not found.', 'danger')
            return redirect(url_for('home'))

        bank_gold_rate = gold_seller_user["goldrate"]
        seller_rate = bank_gold_rate * 0.20  # 20% of bank_gold_rate

        # Default rates for other users
        buy_rate = bank_gold_rate
        sell_rate = bank_gold_rate

        if current_user == 'bilal':
            # Bilal has different rates for buying and selling
            buy_rate = bank_gold_rate - (seller_rate*1)
            sell_rate = bank_gold_rate

        if request.method == 'POST':
            action = request.form.get('action')

            if action in ['buy', 'sell']:
                user = db.Users.find_one({'name': current_user})
                
                if not user:
                    flash('User not found.', 'danger')
                    return redirect(url_for('gold_shop', user=current_user))

                if action == 'buy':
                    cash_amount = float(request.form.get('buy_cash', 0))
                    amount = cash_amount / buy_rate  # Calculate gold quantity based on cash input
                    total_cost = cash_amount

                    if user['balance'] < total_cost:
                        flash('Insufficient balance to buy gold.', 'danger')
                    elif current_user != 'bilal' and gold_seller_user["gold"] < amount:
                        flash('Insufficient Gold reserves in Seller Account!', 'danger')
                    else:
                        try:
                            if current_user != 'bilal':
                                # Update buyer
                                buyer_result = db.Users.update_one(
                                    {'name': current_user},
                                    {'$inc': {'balance': -total_cost, 'gold': amount}}
                                )

                                # Update seller (Bilal)
                                seller_result = db.Users.update_one(
                                    {'name': 'bilal'},
                                    {'$inc': {'balance': total_cost, 'gold': -amount}}
                                )

                                if buyer_result.modified_count > 0 and seller_result.modified_count > 0:
                                    flash(f'Gold purchased successfully! You bought {amount:.4f} units of gold for {total_cost:.2f} PKR.', 'success')
                                else:
                                    # Rollback if one update succeeded but the other failed
                                    if buyer_result.modified_count > 0:
                                        db.Users.update_one(
                                            {'name': current_user},
                                            {'$inc': {'balance': total_cost, 'gold': -amount}}
                                        )
                                    if seller_result.modified_count > 0:
                                        db.Users.update_one(
                                            {'name': 'bilal'},
                                            {'$inc': {'balance': -total_cost, 'gold': amount}}
                                        )
                                    flash('Failed to purchase gold. Please try again.', 'danger')
                            else:  # Bilal buying gold
                                result = db.Users.update_one(
                                    {'name': current_user},
                                    {'$inc': {'balance': -total_cost, 'gold': amount}}
                                )
                                flash(f'Gold purchased successfully! You bought {amount:.4f} units of gold for {total_cost:.2f} PKR.' if result.modified_count > 0 else 'Failed to purchase gold.', 'success' if result.modified_count > 0 else 'danger')
                        except Exception as e:
                            app.logger.error(f"Error during gold purchase: {str(e)}")
                            flash('An error occurred during the purchase. Please try again.', 'danger')

                elif action == 'sell':
                    amount = float(request.form.get('sell_amount', 0))
                    total_money = sell_rate * amount
                    if user['gold'] < amount:
                        flash('Insufficient gold to sell.', 'danger')
                    else:
                        try:
                            if current_user != 'bilal':
                                # Update seller (user)
                                seller_result = db.Users.update_one(
                                    {'name': current_user},
                                    {'$inc': {'balance': total_money, 'gold': -amount}}
                                )

                                if seller_result.modified_count > 0:
                                    flash(f'Gold sold successfully! You sold {amount:.4f} units of gold for {total_money:.2f} PKR.', 'success')
                                else:
                                    flash('Failed to sell gold. Please try again.', 'danger')
                            else:  # Bilal selling gold
                                result = db.Users.update_one(
                                    {'name': current_user},
                                    {'$inc': {'balance': total_money, 'gold': -amount}}
                                )
                                flash(f'Gold sold successfully! You sold {amount:.4f} units of gold for {total_money:.2f} PKR.' if result.modified_count > 0 else 'Failed to sell gold.', 'success' if result.modified_count > 0 else 'danger')
                        except Exception as e:
                            app.logger.error(f"Error during gold sale: {str(e)}")
                            flash('An error occurred during the sale. Please try again.', 'danger')
            else:
                flash('Invalid action.', 'danger')

            return redirect(url_for('gold_shop', user=current_user))

        return render_template('gold_shop.html', current_user=current_user, gold_buy_rate=buy_rate, gold_sell_rate=sell_rate)
    except Exception as e:
        app.logger.error(f"Error handling gold shop: {str(e)}")
        flash('An error occurred while processing your request.', 'danger')
        return redirect(url_for('gold_shop', user=current_user))

@app.route('/transfers', methods=['GET', 'POST'])
@login_required
def transfers():
    if request.method == 'POST':
        current_user = session['user']  # Use form data for current_user, assuming sender_name is the logged-in user
        if not current_user:
            flash('No current user found.', 'danger')
            return redirect(url_for('home'))
        
        try:
            sender_name = session['user']
            receiver_name = request.form.get('receiver_name')
            amount = float(request.form.get('amount'))
            
            sender = db.Users.find_one({'name': sender_name})
            receiver = db.Users.find_one({'name': receiver_name})
            
            if not sender or not receiver:
                flash('Sender or receiver does not exist.', 'danger')
                return redirect(url_for('transfers', user=current_user))

            if sender['balance'] < amount:
                flash('Insufficient balance.', 'danger')
                return redirect(url_for('transfers', user=current_user))

            # Update balances
            db.Users.update_one({'name': sender_name}, {'$inc': {'balance': -amount}})
            db.Users.update_one({'name': receiver_name}, {'$inc': {'balance': amount}})
            
            flash('Transfer successful!', 'success')
            return redirect(url_for('transfers', user=current_user))
        except Exception as e:
            print("Error processing transfer:", e)
            flash('Failed to process transfer.', 'danger')
            return redirect(url_for('transfers', user=current_user))
    
    # For GET request, display the transfer form
    try:
        current_user = request.args.get('user')
        if not current_user:
            flash('No current user found.', 'danger')
            return redirect(url_for('home'))

        users = db.Users.find({
        '$and': [
        {'name': {'$ne': current_user}},  # Exclude current user
        {'role': {'$ne': 'banker'}}       # Exclude users with the role of banker
        ]
        }, {'name': 1})  # Only return the 'name' field

        return render_template('transfers.html', users=users, current_user=current_user)
    except Exception as e:
        print("Error fetching users for transfer:", e)
        return "Failed to load users.", 500


@app.route('/banking', methods=['GET', 'POST'])
@login_required
def banking():
    try:
        current_user = session['user']
        if not current_user:
            flash('No current user found.', 'danger')
            return redirect(url_for('home'))

        if request.method == 'POST':
            action = request.form.get('action')
            amount = float(request.form.get('amount', 0))
            user = db.Users.find_one({'name': current_user})

            if not user:
                flash('User not found.', 'danger')
                return redirect(url_for('banking', user=current_user))
            utc_time = datetime.datetime.now(pytz.utc)
            # Convert to Pakistan Standard Time (PST)
            pst_time = utc_time.astimezone(pytz.timezone('Asia/Karachi'))
            formatted_time = pst_time.strftime('%Y-%m-%d %I:%M:%S %p')
            # Insert request into a "bank_requests" collection for banker approval
            request_id = db.BankRequests.insert_one({
                'user': current_user,
                'action': action,
                'amount': amount,
                'status': 'pending',
                'timestamp': formatted_time
            }).inserted_id

            flash(f'{action.capitalize()} request submitted successfully. Awaiting approval.', 'success')
            return redirect(url_for('banking', user=current_user))

        return render_template('banking.html', current_user=current_user)
    except Exception as e:
        app.logger.error(f"Error handling banking: {str(e)}")
        flash('An error occurred while processing your request.', 'danger')
        return redirect(url_for('banking', user=current_user))


@app.route('/bank_approval', methods=['GET', 'POST'])
def bank_approval():
    try:
        # Retrieve all pending requests
        pending_requests = list(db.BankRequests.find({'status': 'pending'}))

        if request.method == 'POST':
            request_id = request.form.get('request_id')
            decision = request.form.get('decision')  # 'approve' or 'reject'
            request_data = db.BankRequests.find_one({'_id': ObjectId(request_id)})
            ac=request_data['action']
            print(ac)

            if not request_data:
                flash('Request not found.', 'danger')
                return redirect(url_for('bank_approval'))

            if decision == 'approve':
                user = db.Users.find_one({'name': request_data['user']})
                if request_data['action'] == 'deposit':
                    db.Users.update_one(
                        {'name': request_data['user']},
                        {'$inc': {'balance': request_data['amount']}}
                    )
                elif request_data['action'] == 'loan':
                    db.Users.update_one(
                        {'name': request_data['user']},
                        {'$inc': {'balance': request_data['amount'], 'loan': request_data['amount']}}
                    )
                elif request_data['action'] == 'loan-repayment':
                    if user['balance']>=request_data['amount']:
                        db.Users.update_one(
                            {'name': request_data['user']},
                            {'$inc': {'balance': -request_data['amount'], 'loan': -request_data['amount']}}
                        )
                    else:
                        flash(f"Insufficient balance for Loan-Repayment {request_data['amount']} PKR.", 'danger')
                        return redirect(url_for('bank_approval'))
                elif request_data['action'] == 'withdraw':
                    if user['balance'] >= request_data['amount']:
                        db.Users.update_one(
                            {'name': request_data['user']},
                            {'$inc': {'balance': -request_data['amount']}}
                        )
                    else:
                        flash(f"Insufficient balance to withdraw {request_data['amount']} PKR.", 'danger')
                        return redirect(url_for('bank_approval'))

            # Update the request status to 'approved' or 'rejected'
            db.BankRequests.update_one(
                {'_id': ObjectId(request_id)},
                {'$set': {'status': decision}}
            )

            # Increment the banker's request count
            db.Users.update_one(
                {'role': 'banker'},
                {"$inc": {'requests_count': +1}}
            )

            flash(f'Request {decision} successfully.', 'success')
            return redirect(url_for('bank_approval'))
        deeds= db.Deeds.find({"owner":None})
        users = list(db.Users.find({'role': 'player'}))
        banker = db.Users.find_one({'role': 'banker'})
        total_completed_requests = banker['requests_count']
        return render_template('bank_approval.html',deeds=deeds, users=users, pending_requests=pending_requests, total_requests=total_completed_requests)
    
    except Exception as e:
        app.logger.error(f"Error handling bank approval: {str(e)}")
        flash('An error occurred while processing your request.', 'danger')
        return redirect(url_for('bank_approval'))


#GO
@app.route('/go', methods=['POST'])
def go():
    try:
        user_id = request.json.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'message': 'User ID not provided.'}), 400

        user = db.Users.find_one({'_id': ObjectId(user_id)})

        if not user:
            return jsonify({'success': False, 'message': 'User not found.'}), 404

        last_go_time = user.get('last_go_time')
        current_time = datetime.datetime.now()

        if last_go_time and current_time - last_go_time < GO_COOLDOWN:
            time_left = GO_COOLDOWN - (current_time - last_go_time)
            return jsonify({'success': False, 'message': f'GO is not available yet. Please wait {time_left.seconds} seconds.'}), 429

        # Update user's balance and last_go_time
        result = db.Users.update_one(
            {'_id': ObjectId(user_id)},
            {
                '$inc': {'balance': GO_AMOUNT},
                '$set': {'last_go_time': current_time}
            }
        )

        if result.modified_count > 0:
            return jsonify({
                'success': True,
                'message': f'Successfully added {GO_AMOUNT} to {user["name"]}\'s balance.'
            }), 200
        else:
            return jsonify({'success': False, 'message': 'Failed to update user balance.'}), 500

    except Exception as e:
        app.logger.error(f"Error handling GO functionality: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred while processing your request.'}), 500




#assign deed

@app.route('/assign-deed', methods=['POST'])
def assign_deed():
    try:
        data = request.json
        deed_id = data.get('deed_id')
        user_id = data.get('user_id')

        if not deed_id or not user_id:
            return jsonify({'success': False, 'message': 'Deed ID and User ID are required.'}), 400

        # Find the deed and user
        deed = db.Deeds.find_one({'_id': ObjectId(deed_id)})
        user = db.Users.find_one({'_id': ObjectId(user_id)})

        if not deed or not user:
            return jsonify({'success': False, 'message': 'Deed or User not found.'}), 404

        # Check if the deed is already assigned
        if deed.get('owner'):
            return jsonify({'success': False, 'message': 'This deed is already assigned to a user.'}), 400

        # Assign the deed to the user
        result = db.Deeds.update_one(
            {'_id': ObjectId(deed_id)},
            {'$set': {'owner': user['name']}}
        )

        if result.modified_count > 0:
            # Update user's deeds list (assuming you have a 'deeds' field in the Users collection)
            db.Users.update_one(
                {'_id': ObjectId(user_id)},
                {'$push': {'deeds': deed['name']}}
            )

            return jsonify({
                'success': True,
                'message': f"Deed '{deed['name']}' successfully assigned to {user['name']}."
            }), 200
        else:
            return jsonify({'success': False, 'message': 'Failed to assign deed. Please try again.'}), 500

    except Exception as e:
        app.logger.error(f"Error assigning deed: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred while assigning the deed.'}), 500


@app.route('/createdeeds', methods=['POST'])
def create_deed():
    try:
        # Fetch the goldrate from the user 'bilal'
        bilal = db.Users.find_one({'name': 'bilal'})
        goldrate = bilal.get('goldrate', 1)  # Default goldrate to 1 if not found

        # Define base prices for the deeds
        deeds_data = [
            {"name": "Mediter-Ranean Avenue", "color": "Brown", "baseprice": 60},
            {"name": "Baltic Avenue", "color": "Brown", "baseprice": 60},
            {"name": "Reading RailRoad", "color": "black", "baseprice": 200},
            {"name": "Oriental Avenue", "color": "skyblue", "baseprice": 100},
            {"name": "Vermont Avenue", "color": "skyblue", "baseprice": 100},
            {"name": "Connecticut Avenue", "color": "sky-blue", "baseprice": 120},
            {"name": "ST. Charles Place", "color": "Pink", "baseprice": 140},
            {"name": "States Avenue", "color": "Pink", "baseprice": 140},
            {"name": "Virginia  Avenue", "color": "Pink", "baseprice": 160},
            {"name": "Pennsylvania RailRoad", "color": "Black", "baseprice": 200},
            {"name": "ST. James Place", "color": "Orange", "baseprice": 180},
            {"name": "Tennessee Avenue", "color": "Orange", "baseprice": 180},
            {"name": "NewYork Avenue", "color": "Orange", "baseprice": 200},
            {"name": "Kentucky Avenue", "color": "Red", "baseprice": 220},
            {"name": "Indiana Avenue", "color": "Red", "baseprice": 220},
            {"name": "Illinois Avenue", "color": "Red", "baseprice": 240},
            {"name": "Atlantic Avenue", "color": "Yellow", "baseprice": 260},
            {"name": "Ventnor Avenue", "color": "Yellow", "baseprice": 260},
            {"name": "Marvin Gardens Avenue", "color": "Yellow", "baseprice": 280},
            {"name": "Pacific Avenue", "color": "Green", "baseprice": 300},
            {"name": "North Carolina Avenue", "color": "Green", "baseprice": 300},
            {"name": "Pennsylvania Avenue", "color": "Green", "baseprice": 320},
            {"name": "Short Line RailwayRoad", "color": "Black", "baseprice": 200},
            {"name": "Papk Place", "color": "Blue", "baseprice": 350},
            {"name": "BoardWalk", "color": "Blue", "baseprice": 400},
            {"name": "B&O RailRoad", "color": "black", "baseprice": 200}
        ]

        # Calculate price and rent dynamically based on the goldrate
        deeds = []
        for deed in deeds_data:
            baseprice=deed['baseprice']
            price = deed['baseprice'] * goldrate
            rent = price / 2
            deeds.append({
                "name": deed["name"],
                "color": deed["color"],
                "baseprice": baseprice,
                "price":price,
                "rent": rent
            })

        # Insert deeds into the Deeds collection in MongoDB
        result = db.Deeds.insert_many(deeds)

        if result.inserted_ids:
            return jsonify({
                'success': True,
                'message': '6 deeds successfully created.',
                'deeds_created': [str(deed_id) for deed_id in result.inserted_ids]
            }), 201
        else:
            return jsonify({'success': False, 'message': 'Failed to create deeds. Please try again.'}), 500

    except Exception as e:
        app.logger.error(f"Error creating deeds: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred while creating deeds.'}), 500





#pre-post game api's

def update_gold_rate():
    # Fetch the current gold rate from the database
    user = db.Users.find_one({'name': 'bilal'})
    if not user:
        print("User not found")
        return
    
    current_rate = user.get('goldrate')

    # Weighted choice: 2/3 chance to increase, 1/3 chance to decrease
    if random.choices(['increase', 'decrease'], weights=[2, 1])[0] == 'increase':
        new_rate = current_rate + 500
    else:
        new_rate = max(0, current_rate - 500)  # Ensure the rate doesn't go below 0

    # Use your existing set_gold_rate logic to update the gold rate for user 'Bilal'
    request_data = {'rate': new_rate}
    with app.test_request_context(json=request_data):  # Simulate a request context
        response = set_gold_rate()
        update_deeds_prices(new_rate)

def update_deeds_prices(goldrate):
    # Fetch all deeds from the Deeds collection
    deeds = db.Deeds.find()
    
    # Update each deed's price and rent based on the new gold rate
    for deed in deeds:
        base_price = deed['baseprice'] / (goldrate / (goldrate + 500))  # Reverse calculation to get base price
        new_price = base_price * goldrate
        new_rent = new_price / 2
        
        db.Deeds.update_one(
            {'_id': deed['_id']},
            {'$set': {'price': new_price, 'rent': new_rent}}
        )



# Existing function to manually set the gold rate
@app.route('/set-gold-rate', methods=['POST'])
def set_gold_rate():
    data = request.get_json()
    rate = data.get('rate')

    if rate is None:
        return jsonify({"error": "Rate not provided"}), 400

    user = db.Users.find_one({'name': 'bilal'})
    if not user:
        return jsonify({"error": "User not found"}), 404

    db.Users.update_one({'name': 'bilal'}, {'$set': {'goldrate': rate}})

    return jsonify({"message": "Gold rate updated successfully"}), 200

# Scheduler to update the gold rate every 60 seconds
scheduler = BackgroundScheduler()
scheduler.add_job(func=update_gold_rate, trigger="interval", seconds=300)
scheduler.start()

@app.route('/delete_all_users', methods=['DELETE'])
def delete_all_users():
    result = db.Users.delete_many({})
    return jsonify({"message": f"Deleted {result.deleted_count} users from the database"}), 200



@app.route('/delete_all_bank_requests', methods=['DELETE'])
def delete_all_bank_requests():
    result = db.BankRequests.delete_many({})
    return jsonify({"message": f"Deleted {result.deleted_count} bankrequests from the database"}), 200

















#auction system

auctions = {}
@app.route('/create_auction', methods=['POST'])
def create_auction():
    try:
        deed_id = request.form.get('deed_id')
        starting_bid = request.form.get('starting_bid')
        increment = request.form.get('increment')

        # Validate input
        if not all([deed_id, starting_bid, increment]):
            return jsonify({'success': False, 'message': 'All fields are required.'})

        try:
            starting_bid = float(starting_bid)
            increment = float(increment)
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid numeric values provided.'})

        deed = db.Deeds.find_one({'_id': ObjectId(deed_id)})
        if not deed:
            return jsonify({'success': False, 'message': 'Deed not found.'})

        
        auction = {
            '_id': ObjectId(),
            'deed_id': ObjectId(deed_id),
            'deed_name': deed['name'],
            'deed_color': deed['color'],
            'deed_price': deed['price'],
            'deed_rent': deed['rent'],
            'starting_bid': starting_bid,
            'current_bid': starting_bid,
            'increment': increment,
            'highest_bidder': None,
            'participants': [],
            'status': 'active',
        }
        result = db.Auctions.insert_one(auction)
        auction_id = str(result.inserted_id)

        return jsonify({'success': True, 'auction_id': auction_id})

    except Exception as e:
        app.logger.error(f"Error in create_auction: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred while creating the auction.'})



@socketio.on('create_auction')
def handle_create_auction(data):
    try:
        deed_id = data['deed_id']
        starting_bid = float(data['starting_bid'])
        user = data['user']

        if not all([deed_id, starting_bid, user]):
            return emit('auction_created', {'success': False, 'message': 'All fields are required.'})

        deed = db.Deeds.find_one({'_id': ObjectId(deed_id)})
        if not deed:
            return emit('auction_created', {'success': False, 'message': 'Deed not found.'})

        auction = {
            '_id': ObjectId(),
            'deed_id': ObjectId(deed_id),
            'creator': user,
            'deed_name': deed['name'],
            'deed_color': deed['color'],
            'deed_price': deed['price'],
            'deed_rent': deed['rent'],
            'starting_bid': starting_bid,
            'current_bid': starting_bid,
            'increment': starting_bid * 0.1,
            'highest_bidder': None,
            'participants': [],
            'status': 'active',
        }
        
        result = db.Auctions.insert_one(auction)
        auction_id = str(result.inserted_id)

        serializable_auction = json.loads(json_util.dumps(auction))
        serializable_auction['_id'] = str(serializable_auction['_id'])
        serializable_auction['deed_id'] = str(serializable_auction['deed_id'])

        emit('auction_created', {
            'success': True,
            'auction_id': auction_id,
            'auction': serializable_auction
        }, broadcast=True)

    except Exception as e:
        app.logger.error(f"Error in create_auction: {str(e)}")
        emit('auction_created', {'success': False, 'message': f'An error occurred while creating the auction: {str(e)}'})




@socketio.on('get_active_auctions')
def handle_get_active_auctions():
    active_auctions = list(db.Auctions.find({'status': 'active'}))
    for auction in active_auctions:
        auction['_id'] = str(auction['_id'])
        auction['deed_id'] = str(auction['deed_id'])
    
    active_auctions_json = json.loads(dumps(active_auctions))
    emit('active_auctions', active_auctions_json)



@socketio.on('join_auction')
def on_join_auction(data):
    auction_id = data['auction_id']
    user = data['user']
    auction = db.Auctions.find_one({'_id': ObjectId(auction_id), 'status': 'active'})
    if auction:
        join_room(auction_id)
        db.Auctions.update_one(
            {'_id': ObjectId(auction_id)},
            {'$addToSet': {'participants': user}}
        )
        auction = db.Auctions.find_one({'_id': ObjectId(auction_id)})
        emit('auction_update', auction, room=auction_id)

@socketio.on('leave_auction')
def on_leave_auction(data):
    auction_id = data['auction_id']
    user = data['user']
    if auction_id in auctions:
        leave_room(auction_id)
        auctions[auction_id]['participants'].remove(user)
        emit('auction_update', auctions[auction_id], room=auction_id)




@socketio.on('place_bid')
def on_place_bid(data):
    auction_id = data['auction_id']
    user = data['user']
    bid_amount = float(data['bid_amount'])

    print(f"Received bid: auction_id={auction_id}, user={user}, bid_amount={bid_amount}")  # Debug print

    auction = db.Auctions.find_one({'_id': ObjectId(auction_id), 'status': 'active'})
    if not auction:
        emit('bid_error', {'message': 'Auction not found or not active'})
        return

    user_doc = db.Users.find_one({'name': user})
    if not user_doc:
        emit('bid_error', {'message': 'User not found'})
        return

    user_balance = user_doc['balance']

    if bid_amount > user_balance:
        emit('bid_error', {'message': 'Insufficient balance'})
    elif bid_amount <= auction['current_bid']:
        emit('bid_error', {'message': 'Bid must be higher than current bid'})
    else:
        # Update the auction
        db.Auctions.update_one(
            {'_id': ObjectId(auction_id)},
            {'$set': {'current_bid': bid_amount, 'highest_bidder': user}}
        )
        
        # Emit update to all clients
        updated_auction = db.Auctions.find_one({'_id': ObjectId(auction_id)})
        updated_auction['_id'] = str(updated_auction['_id'])
        updated_auction['deed_id'] = str(updated_auction['deed_id'])
        if 'end_time' in updated_auction:
            updated_auction['end_time'] = updated_auction['end_time'].isoformat()
        
        socketio.emit('auction_update', updated_auction, to="broadcast")
        
        # Emit success to the bidder
        emit('bid_placed', {
            'auction_id': auction_id,
            'new_bid': bid_amount,
            'bidder': user
        })

        print(f"Bid placed successfully: auction_id={auction_id}, user={user}, bid_amount={bid_amount}")  # Debug print


def end_auction(auction_id):
    auction = db.Auctions.find_one({'_id': ObjectId(auction_id)})
    if not auction or auction['status'] != 'active':
        return

    db.Auctions.update_one(
        {'_id': ObjectId(auction_id)},
        {'$set': {'status': 'ended'}}
    )

    if auction['highest_bidder']:
        winner = auction['highest_bidder']
        winning_bid = auction['current_bid']
        
        # Update user balance and assign deed
        db.Users.update_one(
            {'name': winner},
            {'$inc': {'balance': -winning_bid}}
        )
        db.Deeds.update_one(
            {'_id': ObjectId(auction['deed_id'])},
            {'$set': {'owner': winner}}
        )
        
        end_data = {
            'auction_id': str(auction_id),
            'deed_name': auction['deed_name'],
            'winner': winner,
            'winning_bid': winning_bid
        }
    else:
        end_data = {
            'auction_id': str(auction_id),
            'deed_name': auction['deed_name'],
            'message': 'No bids were placed'
        }

    socketio.emit('auction_ended', end_data, broadcast=True)
    print(f"Auction ended: {end_data}")

#cancel and sold auction

@app.route('/cancel_auction/<auction_id>', methods=['POST'])
def cancel_auction(auction_id):
    try:
        # Find the auction in the database
        auction = db.Auctions.find_one({'_id': ObjectId(auction_id), 'status': 'active'})
        if not auction:
            return jsonify({'success': False, 'message': 'Auction not found or already completed.'})

        # Mark the auction as canceled
        db.Auctions.update_one({'_id': ObjectId(auction_id)}, {'$set': {'status': 'canceled'}})

        # Broadcast the cancellation
        socketio.emit('auction_canceled', {'auction_id': auction_id}, to="broadcast")
        
        return jsonify({'success': True, 'message': 'Auction canceled successfully.'})
    except Exception as e:
        app.logger.error(f"Error in cancel_auction: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred while canceling the auction.'})


@app.route('/sell_auction/<auction_id>', methods=['POST'])
def sell_auction(auction_id):
    try:
        auction = db.Auctions.find_one({'_id': ObjectId(auction_id), 'status': 'active'})
        if not auction:
            return jsonify({'success': False, 'message': 'Auction not found or already completed.'})

        if not auction['highest_bidder']:
            return jsonify({'success': False, 'message': 'No bids placed on this auction.'})

        highest_bidder = auction['highest_bidder']
        bid_amount = auction['current_bid']
        deed_id = auction['deed_id']

        # Update deed ownership and deduct amount from the highest bidder
        db.Users.update_one({'name': highest_bidder}, {'$inc': {'balance': -bid_amount}})
        db.Users.update_one({'name': auction['creator']}, {'$inc': {'balance': bid_amount}})
        db.Deeds.update_one({'_id': ObjectId(deed_id)}, {'$set': {'owner': highest_bidder}})

        # Mark the auction as completed
        db.Auctions.update_one({'_id': ObjectId(auction_id)}, {'$set': {'status': 'completed'}})

        # Broadcast the auction as sold
        socketio.emit('auction_sold', {'auction_id': auction_id, 'highest_bidder': highest_bidder, 'bid_amount': bid_amount}, to="broadcast")

        return jsonify({'success': True, 'message': 'Auction sold successfully.'})
    except Exception as e:
        app.logger.error(f"Error in sell_auction: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred while selling the auction.'})



if __name__ == '__main__':
    try:
       socketio.run(app, host='0.0.0.0', port=5000 , debug=True)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
