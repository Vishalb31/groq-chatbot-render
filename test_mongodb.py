from pymongo import MongoClient
import urllib.parse

# CORRECT credentials from your screenshot
username = "Vishal_Bhagat"  # Exactly as shown in your Database Access
password = "ABCD@123"  # Your password
cluster = "cluster0.w5azzla.mongodb.net"

# URL encode the password
encoded_password = urllib.parse.quote_plus(password)

# Construct the connection string
uri = f"mongodb+srv://{username}:{encoded_password}@{cluster}/?retryWrites=true&w=majority&appName=Cluster0"

print("="*50)
print("🔧 TESTING MONGODB CONNECTION")
print("="*50)
print(f"📌 Username: {username}")
print(f"📌 Cluster: {cluster}")
print("="*50)

try:
    # Try to connect
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    
    # Ping the database
    client.admin.command('ping')
    print("✅ SUCCESS! Connected to MongoDB Atlas!")
    print("✅ Authentication successful!")
    print("\n📊 Your database is ready to use.")
    
    # Create your database and collection
    db = client['chatbot_db']
    db.create_collection('conversations')
    print("✅ Created database: chatbot_db")
    print("✅ Created collection: conversations")
    
except Exception as e:
    print(f"❌ Connection failed: {e}")
    print("\n🔧 TROUBLESHOOTING STEPS:")
    print("1️⃣ Go to MongoDB Atlas → Network Access")
    print("2️⃣ Click 'Add IP Address' → 'Add Current IP Address' → Confirm")
    print("3️⃣ Wait 2 minutes")
    print("4️⃣ Run this test again")