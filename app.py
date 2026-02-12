from flask import Flask, render_template, request, jsonify, session
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from groq import Groq
import os
from datetime import datetime
from dotenv import load_dotenv
import secrets
from urllib.parse import quote_plus

# Load environment variables from .env file (for local development only)
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(16))

# ============================================
# PRODUCTION SETTINGS FOR RENDER
# ============================================
PORT = int(os.environ.get('PORT', 5000))
HOST = '0.0.0.0'  # CRITICAL for Render!

# ============================================
# MONGODB CONNECTION - FROM ENVIRONMENT VARIABLES
# ============================================
# Get MongoDB URI from environment variable (set in Render dashboard)
MONGO_URI = os.environ.get('MONGO_URI')

# Fallback for local development only - NEVER hardcode in production!
if not MONGO_URI:
    print("⚠️  MONGO_URI not found in environment variables!")
    print("📝 Using hardcoded connection string for LOCAL DEVELOPMENT ONLY")
    username = "Vishal_Bhagat"
    password = "ABCD@123"  # ⚠️ Update this to your actual password
    cluster = "cluster0.w5azzla.mongodb.net"
    encoded_password = quote_plus(password)
    MONGO_URI = f"mongodb+srv://{username}:{encoded_password}@{cluster}/?retryWrites=true&w=majority&appName=Cluster0"

print("="*50)
print("🚀 Starting Groq Chatbot with MongoDB Atlas")
print("="*50)
print(f"📌 Environment: {'Production (Render)' if os.environ.get('RENDER') else 'Local Development'}")
print("="*50)

# MongoDB Connection with proper authentication
try:
    # Connect to MongoDB with explicit auth parameters
    client = MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=30000,
        socketTimeoutMS=30000,
        authSource='admin'  # Critical for Atlas authentication
    )
    
    # Test the connection
    client.admin.command('ping')
    print("✅ MongoDB Atlas connected successfully!")
    
    # Create/use database and collection
    db = client['chatbot_db']
    
    # Check if collection exists, if not create it
    if 'conversations' not in db.list_collection_names():
        conversations = db.create_collection('conversations')
        print("✅ Created new collection: conversations")
    else:
        conversations = db['conversations']
        print("✅ Using existing collection: conversations")
    
    # Create indexes for better performance
    conversations.create_index('session_id')
    conversations.create_index('updated_at')
    
    print("✅ Database indexes created")
    print("="*50)
    
except ServerSelectionTimeoutError as e:
    print(f"❌ MongoDB server selection timeout: {e}")
    print("🔧 Please check your network access in MongoDB Atlas")
    conversations = None
    
except ConnectionFailure as e:
    print(f"❌ MongoDB connection failed: {e}")
    print("🔧 Make sure your IP is whitelisted in MongoDB Atlas")
    conversations = None
    
except Exception as e:
    print(f"❌ MongoDB connection error: {e}")
    print("🔧 Check your username and password")
    conversations = None

# ============================================
# GROQ API CONNECTION
# ============================================
try:
    # Get Groq API key from environment variable
    groq_api_key = os.environ.get('GROQ_API_KEY')
    if not groq_api_key:
        print("⚠️  GROQ_API_KEY not found in environment variables!")
        print("📝 Please add your Groq API key to Render Dashboard → Environment Variables")
        groq_client = None
    else:
        groq_client = Groq(api_key=groq_api_key)
        print("✅ Groq API initialized successfully")
except Exception as e:
    print(f"❌ Groq API error: {e}")
    groq_client = None

print("="*50 + "\n")

@app.route('/')
def home():
    """Home route - Initialize chat session"""
    try:
        if 'session_id' not in session:
            session['session_id'] = secrets.token_hex(16)
            
            # Save to MongoDB if available
            if conversations is not None:
                conversations.insert_one({
                    'session_id': session['session_id'],
                    'messages': [],
                    'created_at': datetime.now(),
                    'updated_at': datetime.now()
                })
                print(f"✅ New session created: {session['session_id'][:8]}...")
    except Exception as e:
        print(f"❌ Error creating session: {e}")
    
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    """Chat endpoint - Process messages and get AI responses"""
    try:
        user_message = request.json.get('message')
        session_id = session.get('session_id')
        
        if not session_id:
            session['session_id'] = secrets.token_hex(16)
            session_id = session['session_id']
        
        # Save user message to MongoDB if available
        if conversations is not None:
            try:
                conversations.update_one(
                    {'session_id': session_id},
                    {
                        '$push': {'messages': {
                            'role': 'user',
                            'content': user_message,
                            'timestamp': datetime.now()
                        }},
                        '$set': {'updated_at': datetime.now()}
                    },
                    upsert=True
                )
            except Exception as e:
                print(f"❌ Failed to save user message: {e}")
        
        # Check if Groq is available
        if groq_client is None:
            return jsonify({
                'response': '⚠️ Groq API is not configured. Please add GROQ_API_KEY to environment variables.',
                'status': 'error'
            })
        
        # Get chat history for context
        chat_history = None
        if conversations is not None:
            try:
                chat_history = conversations.find_one({'session_id': session_id})
            except Exception as e:
                print(f"❌ Failed to fetch chat history: {e}")
        
        # Prepare messages for Groq
        messages = []
        
        # Add system prompt
        messages.append({
            'role': 'system',
            'content': 'You are a helpful AI assistant. Provide clear, concise, and accurate responses.'
        })
        
        # Add chat history if available
        if chat_history and 'messages' in chat_history:
            for msg in chat_history['messages'][-10:]:  # Last 10 messages for context
                messages.append({
                    'role': msg['role'],
                    'content': msg['content']
                })
        else:
            # Add current user message if no history
            messages.append({
                'role': 'user',
                'content': user_message
            })
        
        try:
            # Call Groq API
            completion = groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",  # Currently active model
                messages=messages,
                temperature=0.7,
                max_tokens=1024,
                top_p=0.9,
                stream=False
            )
            
            ai_response = completion.choices[0].message.content
            
            # Save AI response to MongoDB if available
            if conversations is not None:
                try:
                    conversations.update_one(
                        {'session_id': session_id},
                        {'$push': {'messages': {
                            'role': 'assistant',
                            'content': ai_response,
                            'timestamp': datetime.now()
                        }}}
                    )
                except Exception as e:
                    print(f"❌ Failed to save AI response: {e}")
            
            return jsonify({'response': ai_response, 'status': 'success'})
            
        except Exception as e:
            print(f"❌ Groq API error: {e}")
            return jsonify({
                'response': 'I encountered an error with the AI service. Please try again.',
                'status': 'error'
            })
    
    except Exception as e:
        print(f"❌ Error in chat endpoint: {e}")
        return jsonify({
            'response': 'Sorry, something went wrong. Please try again.',
            'status': 'error'
        })

@app.route('/history', methods=['GET'])
def get_history():
    """Get chat history for current session"""
    try:
        session_id = session.get('session_id')
        if session_id and conversations is not None:
            chat_history = conversations.find_one({'session_id': session_id})
            if chat_history and 'messages' in chat_history:
                return jsonify({'messages': chat_history['messages']})
    except Exception as e:
        print(f"❌ Error fetching history: {e}")
    
    return jsonify({'messages': []})

@app.route('/clear', methods=['POST'])
def clear_chat():
    """Clear current chat session"""
    try:
        session_id = session.get('session_id')
        if session_id and conversations is not None:
            # Delete old conversation
            conversations.delete_one({'session_id': session_id})
            
            # Create new session
            session['session_id'] = secrets.token_hex(16)
            
            # Create new conversation
            conversations.insert_one({
                'session_id': session['session_id'],
                'messages': [],
                'created_at': datetime.now(),
                'updated_at': datetime.now()
            })
            
            print(f"✅ Chat cleared, new session created")
            return jsonify({'status': 'success', 'message': 'Chat cleared successfully'})
    except Exception as e:
        print(f"❌ Error clearing chat: {e}")
        return jsonify({'status': 'error', 'message': 'Failed to clear chat'})
    
    return jsonify({'status': 'success'})

@app.route('/status', methods=['GET'])
def get_status():
    """Check the status of all services"""
    status = {
        'mongodb': 'connected' if conversations is not None else 'disconnected',
        'groq': 'connected' if groq_client is not None else 'disconnected',
        'session': session.get('session_id', 'none'),
        'database': 'chatbot_db',
        'collection': 'conversations' if conversations is not None else 'none',
        'environment': 'production' if os.environ.get('RENDER') else 'development'
    }
    return jsonify(status)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Render"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/test-mongodb', methods=['GET'])
def test_mongodb():
    """Test MongoDB connection"""
    if conversations is not None:
        try:
            # Try to insert a test document
            test_id = conversations.insert_one({
                'test': True,
                'timestamp': datetime.now(),
                'message': 'Test connection'
            }).inserted_id
            
            # Delete the test document
            conversations.delete_one({'_id': test_id})
            
            return jsonify({
                'status': 'success',
                'message': 'MongoDB connection is working!'
            })
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': f'MongoDB test failed: {str(e)}'
            })
    else:
        return jsonify({
            'status': 'error',
            'message': 'MongoDB is not connected'
        })

if __name__ == '__main__':
    print("\n" + "="*50)
    print("✅ Application is ready!")
    if os.environ.get('RENDER'):
        print(f"🌐 Running on Render - http://{HOST}:{PORT}")
    else:
        print("🌐 Open http://127.0.0.1:5000 in your browser")
    print("="*50 + "\n")
    
    # IMPORTANT: Use HOST and PORT for Render, debug=False for production
    app.run(host=HOST, port=PORT, debug=False)