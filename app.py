from flask import Flask,session, render_template, request, redirect, url_for, flash , jsonify , make_response
from bson import ObjectId
from pymongo import MongoClient
from dotenv import load_dotenv
from functools import wraps

import os
import datetime
import pytz

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

@app.before_request
def check_login():
    if 'user' not in session and request.endpoint not in ['login', 'play_game', 'static', 'home' ,'add_user',"delete_all_users","set_gold_rate","delete_all_bank_requests"]:
        return redirect(url_for('login'))

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
            name = request.form.get('name')
            user_exists=db.Users.find_one({"name": name})
            if user_exists:
                flash('User already Exists with same Name', "danger")
                return redirect(url_for('add_user'))
            password = request.form.get('password')
            role = 'player'
            if name=='bilal':
                db.Users.insert_one({'name': name, 'password': password ,  'balance': 0 , 'gold' : 0 , 'role':role , 'goldrate': 1500 ,'loan': 0})
            elif name=='abdulrehman':
                db.Users.insert_one({'name': name, 'password': password ,  'balance': 0 , 'gold' : 0 , 'role':'banker' , 'requests_count': 0})
            else:
                db.Users.insert_one({'name': name, 'password': password ,  'balance': 0 , 'gold' : 0 , 'role':role, 'loan': 0})    
            flash('User Added!', 'success')  # Flash a success message
            return redirect(url_for('add_user'))
        except Exception as e:
            print("Error adding user:", e)
            return "Failed to add user.", 500
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
    # user_name = request.args.get('user')
    # if not user_name:
    #     return redirect(url_for('home'))
    
    try:
        user = db.Users.find_one({'name': session['user']})
        if not user:
            session.clear()
            flash('User not found.','danger')
            return redirect(url_for('login'))

        response = make_response(render_template('dashboard.html', user=user))
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
            buy_rate =  bank_gold_rate - (seller_rate*2)
            sell_rate = bank_gold_rate

        if request.method == 'POST':
            action = request.form.get('action')

            if action in ['buy', 'sell']:
                amount = float(request.form.get(f'{action}_amount', 0))
                user = db.Users.find_one({'name': current_user})
                
                if not user:
                    flash('User not found.', 'danger')
                    return redirect(url_for('gold_shop', user=current_user))

                if action == 'buy':
                    total_cost = buy_rate * amount
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
                                    flash('Gold purchased successfully!', 'success')
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
                                flash('Gold purchased successfully!' if result.modified_count > 0 else 'Failed to purchase gold.', 'success' if result.modified_count > 0 else 'danger')
                        except Exception as e:
                            app.logger.error(f"Error during gold purchase: {str(e)}")
                            flash('An error occurred during the purchase. Please try again.', 'danger')

                elif action == 'sell':
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
                                    flash('Gold sold successfully!', 'success')
                                else:
                                    # Rollback if one update succeeded but the other failed
                                    if seller_result.modified_count > 0:
                                        db.Users.update_one(
                                            {'name': current_user},
                                            {'$inc': {'balance': -total_money, 'gold': amount}}
                                        )
                                    flash('Failed to sell gold. Please try again.', 'danger')
                            else:  # Bilal selling gold
                                result = db.Users.update_one(
                                    {'name': current_user},
                                    {'$inc': {'balance': total_money, 'gold': -amount}}
                                )
                                flash('Gold sold successfully!' if result.modified_count > 0 else 'Failed to sell gold.', 'success' if result.modified_count > 0 else 'danger')
                        except Exception as e:
                            app.logger.error(f"Error during gold sale: {str(e)}")
                            flash('An error occurred during the sale. Please try again.', 'danger')
            else:
                flash('Invalid action.', 'danger')

            return redirect(url_for('gold_shop', user=current_user))

        return render_template('gold_shop.html', current_user=current_user, gold_buy_rate=buy_rate , gold_sell_rate=sell_rate)
    except Exception as e:
        app.logger.error(f"Error handling gold shop: {str(e)}")
        flash('An error occurred while processing your request.', 'danger')
        return redirect(url_for('gold_shop', user=current_user))
    try:
        current_user = request.args.get('user')
        if not current_user:
            flash('No current user found.', 'danger')
            return redirect(url_for('home'))

        gold_seller_user= db.Users.find_one({'name':'bilal'})
        bank_gold_rate=gold_seller_user["goldrate"]
        seller_rate=bank_gold_rate/100*20
        
        # Default rates for other users
        buy_rate = bank_gold_rate + seller_rate
        sell_rate = bank_gold_rate + seller_rate

        if current_user == 'bilal':
            # Bilal has different rates for buying and selling
            buy_rate = bank_gold_rate - seller_rate
            sell_rate = bank_gold_rate + seller_rate

        print("goldrate from bank", bank_gold_rate)


        if request.method == 'POST':
            action = request.form.get('action')

            if action in ['buy', 'sell']:
                amount = float(request.form.get(f'{action}_amount', 0))
                user = db.Users.find_one({'name': current_user})
                
                if not user:
                    flash('User not found.', 'danger')
                    return redirect(url_for('gold_shop', user=current_user))

                if action == 'buy' and current_user!='bilal':
                    total_cost = buy_rate * amount
                    if user['balance'] < total_cost:
                        flash('Insufficient balance to buy gold.', 'danger')
                    elif gold_seller_user["gold"]<amount:
                        flash('Insufficient Gold reserves in Seller Account!' , 'danger')
                    else:                       
                        buyer_result = db.Users.update_one(
                        {'name': current_user},
                        {'$inc': {'balance': -total_cost, 'gold': amount}},
                       
                    )

                    # Update seller
                    seller_result = db.Users.update_one(
                        {'name': gold_seller_user['name']},  # Assume gold_seller_user is a dictionary
                        {'$inc': {'balance': total_cost, 'gold': -amount}},
                        
                    )

                    if buyer_result.modified_count > 0 and seller_result.modified_count > 0:
                        flash('Gold purchased successfully!', 'success') 
                    else:
                        flash('Failed to Purchase Gold!','danger')
                elif action == 'buy' and current_user =='bilal':
                    total_cost = buy_rate * amount
                    if user['balance'] < total_cost:
                        flash('Insufficient balance to buy gold.', 'danger')
                    else:
                        result = db.Users.update_one(
                            {'name': current_user},
                            {'$inc': {'balance': -total_cost, 'gold': amount}}
                        )
                        flash('Gold purchased successfully!' if result.modified_count > 0 else 'Failed to purchase gold.', 'success' if result.modified_count > 0 else 'danger')
               
                else:  # sell
                    total_money = sell_rate * amount
                    if user['gold'] < amount:
                        flash('Insufficient gold to sell.', 'danger')
                    else:
                        result = db.Users.update_one(
                            {'name': current_user},
                            {'$inc': {'balance': total_money, 'gold': -amount}}
                        )
                        flash('Gold sold successfully!' if result.modified_count > 0 else 'Failed to sell gold.', 'success' if result.modified_count > 0 else 'danger')
            else:
                flash('Invalid action.', 'danger')

            return redirect(url_for('gold_shop', user=current_user))

        return render_template('gold_shop.html', current_user=current_user, gold_rate=buy_rate)
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

        banker = db.Users.find_one({'role': 'banker'})
        total_completed_requests = banker['requests_count']
        return render_template('bank_approval.html', pending_requests=pending_requests, total_requests=total_completed_requests)
    
    except Exception as e:
        app.logger.error(f"Error handling bank approval: {str(e)}")
        flash('An error occurred while processing your request.', 'danger')
        return redirect(url_for('bank_approval'))






















#pre-post game api's

@app.route('/set_gold_rate', methods=['POST'])
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



@app.route('/delete_all_users', methods=['DELETE'])
def delete_all_users():
    result = db.Users.delete_many({})
    return jsonify({"message": f"Deleted {result.deleted_count} users from the database"}), 200



@app.route('/delete_all_bank_requests', methods=['DELETE'])
def delete_all_bank_requests():
    result = db.BankRequests.delete_many({})
    return jsonify({"message": f"Deleted {result.deleted_count} bankrequests from the database"}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000 , debug=True)
